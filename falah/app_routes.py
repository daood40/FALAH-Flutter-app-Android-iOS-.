"""معالِجاتُ مسارات التطبيق — واحدةٌ لكلِّ مسار.

كانت هذه كلُّها في `app_post` (١٩٨ سطرًا) و`app_get`: سلسلةُ `if p == …`
تخلط الاختيارَ بالعمل، ويشترك فيها إذنٌ ووثيقةٌ وحصّةٌ وحدُّ معدّلٍ بلا
حدودٍ ظاهرة بينها. وكان كلُّ فحصِ ملكيةٍ مكتوبًا في موضعه: `AND user_id=?`
هنا و`owned()` هناك — يُنسى في موضعٍ فيصير ثغرة.

هنا صار كلُّ معالِجٍ دالّةً واحدة:

    handler(rq) → Response

ولا فحصَ إذنٍ في أيٍّ منها. الإذنُ قُرِّر قبلها كلِّها في `falah/authz.py`،
والمسارُ يُعلن في `falah/routing.py` أيَّ مورِدٍ يمسّ وبأيّ فعل. فالمعالِجُ
يصل وقد ثبت أن صاحبَه يملك ما يمسّه — ولا يعيد السؤال ولا ينساه.

**والمنطقُ نُقل كما هو.** الترتيبُ والرسائلُ والرموزُ كما كانت حرفًا بحرف،
حتى ترتيبُ تقييم الحقول (`int(b["project"])` قبل `b["kind"]`) محفوظٌ في
`routing.py` — لأن اختلافَه يغيّر أيَّ خطأٍ يظهر أوّلًا.
"""
import json, os

from falah import auth, billing, jobs as JB, projects as P, ratelimit as RL
from falah import referrals as REF, settings as S, store
from falah.web import Response

# ═══════════════════ القراءة ═══════════════════

def config(rq):
    return Response({"invite_required": bool(S.INVITE), "origin": S.ORIGIN or None})

def plans(rq):
    return Response(billing.catalogue())

def me(rq):
    return Response({"user": rq.user} if rq.user else {"user": None}, 200)

def entitlements(rq):
    return Response(billing.entitlements(rq.c, rq.uid))

def referrals(rq):
    return Response(REF.summary(rq.c, rq.uid))

def projects(rq):
    return Response({"projects": P.listing(rq.c, rq.uid)})

def project_open(rq):
    return Response(P.open_project(rq.c, rq.content, rq.uid, rq.params["project"]))

def limits(rq):
    return Response(JB.limits())

def jobs(rq):
    return Response({"jobs": JB.listing(rq.c, rq.uid),
                     "queue": JB.stats(rq.c), "limits": JB.limits()})

def job_get(rq):
    return Response({"job": JB.get(rq.c, rq.uid, rq.params["job"])})

def exports(rq):
    rows = rq.c.execute("""SELECT * FROM exports WHERE user_id=?
                           ORDER BY created_at DESC LIMIT 50""", (rq.uid,)).fetchall()
    return Response({"exports": [dict(r) for r in rows]})

TYPES = {".png": "image/png", ".mp4": "video/mp4",
         ".txt": "text/plain; charset=utf-8"}

def file_get(rq):
    """الملفُّ نفسه. ملكيّتُه ثبتت في طبقة الإذن — انظر `authz.export_file`."""
    full = rq.params["export_file"]
    return Response.sends_file(full, TYPES.get(os.path.splitext(full)[1],
                                               "application/octet-stream"))

def unknown(rq):
    return Response({"error": "مسار غير معروف"}, 404)

# ═══════════════════ الحساب ═══════════════════

def register(rq):
    b = rq.body
    if S.INVITE and (b.get("invite") or "").strip() != S.INVITE:
        store.log(rq.c, None, "invite_rejected", (b.get("email") or "")[:80])
        rq.c.commit()
        return Response({"error": "رمز الدعوة غير صحيح"}, 403)
    uid = auth.register(rq.c, b.get("email"), b.get("password"),
                        b.get("name"), b.get("watermark"))
    ref_note = None
    if (b.get("ref") or "").strip():
        try:    REF.attach(rq.c, uid, b["ref"])
        except REF.ReferralError as e: ref_note = str(e)
    try:    auth.request_verify(rq.c, uid)
    except Exception: pass
    tok, u = auth.login(rq.c, b.get("email"), b.get("password"),
                        rq.get_header("User-Agent", ""))
    return Response({"user": u, "referral_note": ref_note,
                     "entitlements": billing.entitlements(rq.c, uid)},
                    201, cookie=("set", tok, auth.SESSION_TTL))

def password_forgot(rq):
    # الردّ واحدٌ سواءٌ وُجد البريد أو لم يوجد
    r = auth.request_reset(rq.c, rq.body.get("email"))
    sent = (r.get("mail") or {}).get("sent")
    return Response({"ok": True, "mail_sent": bool(sent),
                     "note": None if sent else
                     "إن كان البريد مسجَّلًا فالرسالة في طريقها"})

def password_reset(rq):
    auth.reset_password(rq.c, rq.body.get("token"), rq.body.get("password"))
    return Response({"ok": True}, 200, cookie=("clear",))

def verify_confirm(rq):
    auth.verify_email(rq.c, rq.body.get("token"))
    return Response({"ok": True})

def login(rq):
    tok, u = auth.login(rq.c, rq.body.get("email"), rq.body.get("password"),
                        rq.get_header("User-Agent", ""))
    return Response({"user": u}, 200, cookie=("set", tok, auth.SESSION_TTL))

def logout(rq):
    auth.logout(rq.c, rq.session_token)
    return Response({"ok": True}, 200, cookie=("clear",))

def account_delete(rq):
    # يُشترط التصريح بكلمة «حذف» حتى لا يقع الحذف بنقرةٍ عابرة
    if (rq.body.get("confirm") or "").strip() != "حذف":
        return Response({"error": "اكتب «حذف» للتأكيد"}, 400)
    gone = auth.delete_account(rq.c, rq.uid, export_dir=rq.root)
    return Response({"ok": True, **gone}, 200, cookie=("clear",))

def verify_request(rq):
    r = auth.request_verify(rq.c, rq.uid)
    return Response({"ok": True, "already": r.get("already", False),
                     "mail_sent": bool((r.get("mail") or {}).get("sent"))})

def profile(rq):
    auth.update_profile(rq.c, rq.uid, rq.body.get("name"), rq.body.get("watermark"))
    return Response({"user": auth.session_user(rq.c, rq.session_token)})

def password_change(rq):
    auth.change_password(rq.c, rq.uid, rq.body.get("old"), rq.body.get("new"))
    return Response({"ok": True, "note": "أُنهيت كل الجلسات"}, 200, cookie=("clear",))

# ═══════════════════ الاشتراك ═══════════════════

def subscription_cancel(rq):
    return Response({"subscription": billing.cancel(rq.c, rq.uid),
                     "entitlements": billing.entitlements(rq.c, rq.uid)})

def subscription_store_event(rq):
    # الجهاز يرسل رمز الشراء فقط، والخادم يسأل المتجر عنه ويشتقّ الحقّ من
    # ردّه — فلا يُمنح شيءٌ بحمولةٍ قادمةٍ من جهاز.
    trusted = rq.subject.has("manage_billing")
    try:
        sub = billing.apply_store_event(rq.c, rq.uid, rq.body.get("provider"),
                                        rq.body.get("event") or {}, verified=trusted)
    except billing.BillingError as e:
        return Response({"error": str(e)}, 402)
    return Response({"subscription": sub,
                     "entitlements": billing.entitlements(rq.c, rq.uid)})

def subscription_grant(rq):
    # منحةٌ إدارية: تجارب، تعويضات، دعوات. الإذنُ فُحص في طبقته.
    b = rq.body
    sub = billing.grant(rq.c, int(b.get("user") or rq.uid), b.get("plan"),
                        days=int(b.get("days") or 30), provider="grant",
                        note=b.get("note"))
    return Response({"subscription": sub})

# ═══════════════════ المشاريع والعناصر ═══════════════════

def project_create(rq):
    b = rq.body
    billing.check(rq.c, rq.uid, "projects")
    pid = P.create(rq.c, rq.uid, b.get("title"), b.get("kind", "series"),
                   b.get("skin", "parch"), b.get("ratio", "square"),
                   b.get("watermark") or rq.user["watermark"])
    return Response({"id": pid}, 201)

def project_update(rq):
    P.update(rq.c, rq.uid, rq.params["project"],
             **{k: rq.body.get(k) for k in
                ("title", "kind", "skin", "ratio", "watermark", "note", "archived")})
    return Response({"ok": True})

def project_delete(rq):
    P.delete(rq.c, rq.uid, rq.params["project"])
    return Response({"ok": True})

def item_add(rq):
    iid = P.add_item(rq.c, rq.content, rq.uid, rq.params["project"],
                     rq.params["kind"], rq.params["ref"])
    return Response({"id": iid}, 201)

def item_remove(rq):
    P.remove_item(rq.c, rq.uid, rq.params["project"], rq.params["item"])
    return Response({"ok": True})

def item_reorder(rq):
    P.reorder(rq.c, rq.uid, rq.params["project"], rq.params["order"])
    return Response({"ok": True})

def item_accept_drift(rq):
    P.accept_drift(rq.c, rq.content, rq.uid, rq.params["project"], rq.params["item"])
    return Response({"ok": True})

# ═══════════════════ الوكيل ═══════════════════

def agent_ask(rq):
    from falah import agent as AG
    ans = rq.body.get("answers") or {}
    ans = AG.sanitize(ans, rq.content_db)
    q = AG.next_question(ans, rq.content_db, rq.user["watermark"])
    prog = AG.progress(ans, rq.content_db)
    if q:
        return Response({"done": False, "question": q, "answers": ans, "progress": prog,
                         "preview": AG.plan(ans, rq.content_db)
                         if ans.get("source_kind") and AG.selection(ans, rq.content_db)
                         else None})
    try:
        return Response({"done": True, "plan": AG.plan(ans, rq.content_db),
                         "answers": ans, "progress": prog})
    except SystemExit as e:
        return Response({"error": str(e)}, 404)

def agent_build(rq):
    from falah import agent as AG
    ans = rq.body.get("answers") or {}
    if AG.next_question(ans, rq.content_db, rq.user["watermark"]):
        return Response({"error": "الإجابات غير مكتملة"}, 400)
    pl = AG.plan(ans, rq.content_db)
    st = pl["style"]
    pid = P.create(rq.c, rq.uid, pl["title"], "series", st["skin"], st["ratio"],
                   st["watermark"] or rq.user["watermark"])
    added = 0
    for card in pl["cards"]:
        try:
            P.add_item(rq.c, rq.content, rq.uid, pid, card["kind"], card["ref"]); added += 1
        except P.ProjectError:
            pass          # ما لم يجتز الفحص لحظة الإضافة يُترك، ولا يُستبدل
    store.log(rq.c, rq.uid, "agent_project", f"{pid}:{added}")
    rq.c.commit()
    return Response({"project": pid, "added": added}, 201)

# ═══════════════════ التصيير — يوضع في الطابور ═══════════════════

def export(rq):
    """يضع تصديرَ المشروع في الطابور ويردّ فورًا. الشروط تُفحص هنا —
    قبل الوضع — حتى يعرف المستخدمُ الخطأَ في طلبه لا بعد دقيقة."""
    c, u, pid = rq.c, rq.user, rq.params["project"]
    st = P.open_project(c, rq.content, u["id"], pid)
    if not st["items"]:   return Response({"error": "المشروع فارغ"}, 400)
    if not st["exportable"]:
        return Response({"error": "فيه عناصر محجوبة أو منحرفة — راجعها أولًا",
                         "blocked": st["blocked"], "drift": st["drift"]}, 409)
    proj = st["project"]
    n = len(st["items"])
    # الحصّة تُفحص ثم تُحجز عند الوضع — وإلا أغرق أحدٌ الطابورَ بما يتجاوز
    # خطّته قبل أن يُصيَّر منه شيء. وتُردّ كاملةً إن فشل العمل.
    billing.check(c, u["id"], "cards", n)
    billing.require(c, u["id"], "ratios", proj["ratio"], what="هذا المقاس")
    billing.require(c, u["id"], "designs", proj["skin"], what="هذا التصميم")
    # التفرّد يُفحص قبل حجز الحصّة: نقرتان لا تستهلكان بطاقاتٍ مرّتين
    dup = JB.live_for(c, JB.idem_key(u["id"], "export", {"project": pid}))
    if dup:
        return Response({"job": JB.view(dup), "duplicate": True,
                         "note": "هذا التصدير في الطابور بالفعل"}, 202)
    if not RL.ok(c, "export", u["id"]):
        body, hdr = RL.exceeded("export")
        return Response(body, 429, headers=hdr)
    billing.consume(c, u["id"], "cards", n)
    try:
        job = JB.enqueue(c, u["id"], "export", {"project": pid}, {"cards": n})
    except JB.JobConflict as e:
        # سباقٌ بين الفحص أعلاه والإدراج: طلبان متزامنان بالبصمة نفسها.
        # الفهرس الفريد حسمه، فيُردّ الثاني بالمهمّة القائمة — لا بخطأ.
        billing.release(c, u["id"], "cards", n)
        return Response({**json.loads(str(e)),
                         "note": "هذا التصدير في الطابور بالفعل"}, 202)
    except JB.JobError:
        billing.release(c, u["id"], "cards", n)     # لم تدخل الطابور فلا تُحاسَب
        raise
    RL.bump(c, "export", u["id"])      # عند القبول لا عند الطلب
    store.log(c, u["id"], "export_queued", f"{pid}:{job['id']}"); c.commit()
    return Response({"job": job, "cards": n,
                     "note": "التصدير في الطابور — تابِع حالته"}, 202)

def video(rq):
    """مقطعٌ من عنصرٍ قرآنيّ في المشروع: البطاقة نفسها + تلاوة قارئٍ مسجَّل.
    التلاوة رواية، فلا تُركَّب على نصٍّ لم يجتز الفحص، ولا على غير القرآن.
    يوضع في الطابور — ٢٦ ثانية لا تُنتظر داخل طلب."""
    c, u = rq.c, rq.user
    pid, item_id = rq.params["project"], rq.params["item"]
    reciter = rq.body.get("reciter", "alafasy")
    st = P.open_project(c, rq.content, u["id"], pid)
    it = next((x for x in st["items"] if x["id"] == item_id), None)
    if not it:                 return Response({"error": "العنصر غير موجود"}, 404)
    if it["kind"] != "quran":  return Response({"error": "المقطع للآيات فقط"}, 400)
    if it["state"] != "ok":
        return Response({"error": "العنصر يحتاج مراجعة: " + (it.get("why") or "")}, 409)
    r = rq.content.execute("SELECT code FROM reciters WHERE code=?", (reciter,)).fetchone()
    if not r:                  return Response({"error": "القارئ غير مسجَّل"}, 400)
    billing.check(c, u["id"], "videos")
    billing.require(c, u["id"], "ratios", st["project"]["ratio"], what="هذا المقاس")
    pay = {"project": pid, "item": item_id, "reciter": reciter}
    dup = JB.live_for(c, JB.idem_key(u["id"], "video", pay))
    if dup:
        return Response({"job": JB.view(dup), "duplicate": True,
                         "note": "هذا المقطع في الطابور بالفعل"}, 202)
    if not RL.ok(c, "video", u["id"]):
        body, hdr = RL.exceeded("video")
        return Response(body, 429, headers=hdr)
    billing.consume(c, u["id"], "videos")
    try:
        job = JB.enqueue(c, u["id"], "video", pay, {"videos": 1})
    except JB.JobConflict as e:
        billing.release(c, u["id"], "videos", 1)
        return Response({**json.loads(str(e)),
                         "note": "هذا المقطع في الطابور بالفعل"}, 202)
    except JB.JobError:
        billing.release(c, u["id"], "videos", 1)
        raise
    RL.bump(c, "video", u["id"])
    store.log(c, u["id"], "video_queued", f"{pid}:{item_id}:{job['id']}"); c.commit()  # noqa
    return Response({"job": job, "note": "المقطع في الطابور — تابِع حالته"}, 202)

def job_cancel(rq):
    return Response({"job": JB.cancel(rq.c, rq.uid, rq.params["job"])})
