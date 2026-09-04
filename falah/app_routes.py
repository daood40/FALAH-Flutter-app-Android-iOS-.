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

from falah import audit as AUD, auth, authz as AZ, billing
from falah import jobs as JB, projects as P, ratelimit as RL
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
    AUD.from_request(rq, "account.created", actor_id=uid, actor_role="user",
                     resource_type="user", resource_id=uid,
                     metadata={"invited": bool(S.INVITE)})
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
    uid = auth.reset_password(rq.c, rq.body.get("token"), rq.body.get("password"))
    AUD.from_request(rq, "password.reset", actor_id=uid, actor_role=None,
                     resource_type="user", resource_id=uid)
    return Response({"ok": True}, 200, cookie=("clear",))

def verify_confirm(rq):
    auth.verify_email(rq.c, rq.body.get("token"))
    return Response({"ok": True})

def login(rq):
    """الدخول. والفشلُ يُسجَّل كالنجاح — فمحاولاتُ التخمين تُرى في السجلّ.

    ولا يُسجَّل البريدُ المحاوَل به: تسجيلُه يبني قائمةَ عناوينَ في جدولٍ
    يقرؤه المشرف. يكفي العنوانُ والوكيلُ لمعرفة مَن يحاول.
    """
    try:
        tok, u = auth.login(rq.c, rq.body.get("email"), rq.body.get("password"),
                            rq.get_header("User-Agent", ""))
    except auth.AuthError:
        AUD.from_request(rq, "login.failure", result="failure",
                         actor_id=None, actor_role="anonymous")
        raise
    AUD.from_request(rq, "login.success", actor_id=u["id"], actor_role=u.get("role"),
                     resource_type="user", resource_id=u["id"])
    return Response({"user": u}, 200, cookie=("set", tok, auth.SESSION_TTL))

def logout(rq):
    auth.logout(rq.c, rq.session_token)
    if rq.subject.authenticated:
        AUD.from_request(rq, "logout")
    return Response({"ok": True}, 200, cookie=("clear",))

def account_delete(rq):
    # يُشترط التصريح بكلمة «حذف» حتى لا يقع الحذف بنقرةٍ عابرة
    if (rq.body.get("confirm") or "").strip() != "حذف":
        return Response({"error": "اكتب «حذف» للتأكيد"}, 400)
    uid = rq.uid
    # يُسجَّل **قبل** الحذف: بعده لا جلسةَ ولا صفَّ يُقرأ منه شيء. والسجلُّ
    # يبقى — لا مفتاحَ أجنبيًّا على `actor_id`، ولا `audit_logs` في جداول
    # الحذف. أثرُ ما جرى لا يُمحى بمحو فاعله.
    AUD.from_request(rq, "account.deleted", resource_type="user", resource_id=uid)
    gone = auth.delete_account(rq.c, uid, export_dir=rq.root)
    return Response({"ok": True, **gone}, 200, cookie=("clear",))

def verify_request(rq):
    r = auth.request_verify(rq.c, rq.uid)
    return Response({"ok": True, "already": r.get("already", False),
                     "mail_sent": bool((r.get("mail") or {}).get("sent"))})

def profile(rq):
    # **حقولٌ ثلاثة لا رابع.** ما عداها في الجسم يُتجاهَل: `role` و`status`
    # و`id` وأيُّ حقلٍ آخر لا يبلغ القاعدة من هنا بحال — وهذا هو الحارس
    # البنيويّ ضدّ الإسناد الجماعيّ: لا نمرّر `**body` في موضعٍ واحد.
    auth.update_profile(rq.c, rq.uid, rq.body.get("name"), rq.body.get("watermark"))
    AUD.from_request(rq, "account.updated", resource_type="user", resource_id=rq.uid)
    return Response({"user": auth.session_user(rq.c, rq.session_token)})

def password_change(rq):
    auth.change_password(rq.c, rq.uid, rq.body.get("old"), rq.body.get("new"))
    AUD.from_request(rq, "password.changed", resource_type="user", resource_id=rq.uid)
    return Response({"ok": True, "note": "أُنهيت كل الجلسات"}, 200, cookie=("clear",))

# ═══════════════════ الاشتراك ═══════════════════

def subscription_cancel(rq):
    AUD.from_request(rq, "subscription.canceled",
                     resource_type="subscription", resource_id=rq.uid)
    return Response({"subscription": billing.cancel(rq.c, rq.uid),
                     "entitlements": billing.entitlements(rq.c, rq.uid)})

def subscription_store_event(rq):
    # الجهاز يرسل رمز الشراء فقط، والخادم يسأل المتجر عنه ويشتقّ الحقّ من
    # ردّه — فلا يُمنح شيءٌ بحمولةٍ قادمةٍ من جهاز.
    # الثقةُ من دورٍ حقيقيّ لا من مفتاحٍ مشترك — هذا ما تغيّر في P1.2.
    trusted = rq.subject.has("subscription.grant")
    AUD.from_request(rq, "subscription.store_event",
                     resource_type="subscription", resource_id=rq.uid,
                     metadata={"provider": rq.body.get("provider"), "trusted": trusted})
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
    target = int(b.get("user") or rq.uid)
    sub = billing.grant(rq.c, target, b.get("plan"),
                        days=int(b.get("days") or 30), provider="grant",
                        note=b.get("note"))
    AUD.from_request(rq, "subscription.granted",
                     resource_type="user", resource_id=target,
                     metadata={"plan": b.get("plan"), "days": b.get("days")})
    return Response({"subscription": sub})

# ═══════════════════ المشاريع والعناصر ═══════════════════

def project_create(rq):
    b = rq.body
    billing.check(rq.c, rq.uid, "projects")
    pid = P.create(rq.c, rq.uid, b.get("title"), b.get("kind", "series"),
                   b.get("skin", "parch"), b.get("ratio", "square"),
                   b.get("watermark") or rq.user["watermark"])
    AUD.from_request(rq, "project.created", resource_type="project", resource_id=pid)
    return Response({"id": pid}, 201)

def project_update(rq):
    P.update(rq.c, rq.uid, rq.params["project"],
             **{k: rq.body.get(k) for k in
                ("title", "kind", "skin", "ratio", "watermark", "note", "archived")})
    return Response({"ok": True})

def project_delete(rq):
    P.delete(rq.c, rq.uid, rq.params["project"])
    AUD.from_request(rq, "project.deleted", resource_type="project",
                     resource_id=rq.params["project"])
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
    store.log(c, u["id"], "export_queued", f"{pid}:{job['id']}")
    AUD.from_request(rq, "export.created", resource_type="job", resource_id=job["id"],
                     metadata={"project": pid, "cards": n}, commit=False)
    c.commit()
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

# ═══════════════════ الإدارة ═══════════════════
# ولا `if role == "admin"` في سطرٍ منها. الصلاحيةُ فُحصت في طبقة الإذن قبل
# أن يصل المعالِج، وحارسُ التسلسل في `authz.may_manage` و`may_grant` —
# فمن أضاف مسارَ إدارةٍ غدًا ونسيهما سقط في `rbac_test.py`.

USER_FIELDS = ("id", "email", "name", "role", "status", "created_at",
               "last_login", "verified_at", "role_changed_at")

def _user_row(c, uid):
    r = c.execute(f"SELECT {','.join(USER_FIELDS)} FROM users WHERE id=?",
                  (uid,)).fetchone()
    return dict(r) if r else None

def admin_users(rq):
    """سردُ الحسابات. لا كلمةَ مرورٍ ولا ملحَ ولا اشتقاق — الأعمدةُ مسمّاةٌ
    واحدًا واحدًا، فلا يتسرّب عمودٌ جديدٌ يومًا بـ`SELECT *`."""
    q = rq.query
    lim = max(1, min(int((q.get("limit") or ["50"])[0] or 50), 200))
    off = max(0, int((q.get("offset") or ["0"])[0] or 0))
    role = (q.get("role") or [None])[0]
    where, args = ["1=1"], []
    if role: where.append("role=?"); args.append(role)
    sql = "FROM users WHERE " + " AND ".join(where)
    total = rq.c.execute("SELECT COUNT(*) " + sql, args).fetchone()[0]
    rows = rq.c.execute(f"SELECT {','.join(USER_FIELDS)} " + sql
                        + " ORDER BY id LIMIT ? OFFSET ?", args + [lim, off]).fetchall()
    return Response({"total": total, "limit": lim, "offset": off,
                     "users": [dict(r) for r in rows]})

def admin_user_get(rq):
    u = _user_row(rq.c, rq.params["user"])
    if not u: return Response({"error": "الحساب غير موجود"}, 404)
    return Response({"user": u})

def admin_roles(rq):
    """الأدوار وصلاحياتُها — تُقرأ ولا تُخمَّن. ومنها يُبنى عرضُ الإدارة."""
    return Response({"roles": {r: sorted(AZ.perms_of(r)) for r in AZ.ASSIGNABLE},
                     "assignable": list(AZ.ASSIGNABLE),
                     "permissions": sorted(AZ.PERMISSIONS)})

def _guard(rq, target, *, new_role=None):
    """حارسُ التسلسل. يعيد `Response` عند المنع، أو `None` إن جاز.

    والردُّ عند المنع **٤٠٣ برسالةٍ واحدة** لكل الأسباب: لا يُقال «لا تملك
    هذا الدور» ولا «هذا الحساب أعلى منك»، فذلك يرسم للمهاجم خريطةَ الأدوار.
    والسببُ الدقيق يُكتب في سجلّ التدقيق حيث يُقرأ ولا يُسرَّب.
    """
    why = AZ.may_manage(rq.subject, target["role"], target["id"])
    if why == AZ.ALLOWED and new_role is not None:
        why = AZ.may_grant(rq.subject, new_role)
    if why == AZ.ALLOWED: return None
    AUD.from_request(rq, "security.denied", result="denied",
                     resource_type="user", resource_id=target["id"],
                     metadata={"reason": why, "requested_role": new_role})
    return Response({"error": "غير مصرَّح"}, 403)

def admin_set_role(rq):
    """تغييرُ دورِ حساب. أخطرُ مسارٍ في النظام، فحرّاسُه ثلاثة:

      ق١ لا أحدَ يمسّ نفسَه · ق٢ لا يمنح دورًا أقوى منه ·
      ق٣ لا يُدير حسابًا ليس دونه.

    وكلُّها في `falah/authz.py` لا هنا — فلا تُنسخ ولا تُنسى.
    """
    target = _user_row(rq.c, rq.params["user"])
    if not target: return Response({"error": "الحساب غير موجود"}, 404)
    new_role = str(rq.body.get("role") or "")
    if new_role not in AZ.ASSIGNABLE:
        return Response({"error": "دورٌ غير معروف — المتاح: "
                                  + " · ".join(AZ.ASSIGNABLE)}, 400)
    blocked = _guard(rq, target, new_role=new_role)
    if blocked: return blocked
    old = target["role"]
    rq.c.execute("UPDATE users SET role=?, role_changed_at=? WHERE id=?",
                 (new_role, store.now(), target["id"]))
    # الجلساتُ القائمة تحمل دورًا صار قديمًا — تُنهى كلُّها. وإلا بقي مَن
    # خُفِّض دورُه يعمل بصلاحياتٍ نُزعت منه حتى تنتهي كعكتُه بعد شهر.
    rq.c.execute("DELETE FROM sessions WHERE user_id=?", (target["id"],))
    AUD.from_request(rq, "role.changed", resource_type="user",
                     resource_id=target["id"],
                     metadata={"from": old, "to": new_role,
                               "reason": rq.body.get("reason")}, commit=False)
    rq.c.commit()
    return Response({"user": _user_row(rq.c, target["id"])})

def admin_set_status(rq):
    """إيقافُ حسابٍ وإعادةُ تفعيله. الموقوفُ لا تُقبل له جلسةٌ ولا دخول."""
    target = _user_row(rq.c, rq.params["user"])
    if not target: return Response({"error": "الحساب غير موجود"}, 404)
    status = str(rq.body.get("status") or "")
    if status not in ("active", "suspended"):
        return Response({"error": "حالةٌ غير معروفة — المتاح: active · suspended"}, 400)
    blocked = _guard(rq, target)
    if blocked: return blocked
    rq.c.execute("UPDATE users SET status=? WHERE id=?", (status, target["id"]))
    if status == "suspended":
        rq.c.execute("DELETE FROM sessions WHERE user_id=?", (target["id"],))
    AUD.from_request(rq, "user.suspended" if status == "suspended"
                     else "user.reactivated",
                     resource_type="user", resource_id=target["id"],
                     metadata={"reason": rq.body.get("reason")}, commit=False)
    rq.c.commit()
    return Response({"user": _user_row(rq.c, target["id"])})

def admin_audit(rq):
    """قراءةُ سجلّ التدقيق — **وقراءتُه نفسُها تُسجَّل**."""
    q = rq.query
    out = AUD.listing(rq.c,
                      limit=(q.get("limit") or [50])[0],
                      offset=(q.get("offset") or [0])[0],
                      action=(q.get("action") or [None])[0],
                      actor_id=(q.get("actor") or [None])[0],
                      result=(q.get("result") or [None])[0])
    AUD.from_request(rq, "audit.read", resource_type="audit_logs",
                     metadata={"returned": len(out["events"])})
    return Response(out)
