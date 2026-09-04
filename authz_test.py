#!/usr/bin/env python3
"""طبقةُ الإذن — وحدةً وحيًّا.

    python3 authz_test.py

ثلاثةُ أقسام:

  ١. **`can()` وحدها** — بلا خادمٍ ولا قاعدة. القرارُ دالّةٌ صافية، فيُختبر
     كما تُختبر دالّة: كلُّ شرطٍ في `POLICY`، والمنعُ بحكم الأصل، والمالكُ
     المختلف، والمورِدُ المفقود، والمجهول.

  ٢. **اكتمالُ الجدول** — أن كلَّ مسارٍ أعلن مورِدَه وفعله، وأن لكلِّ زوجٍ
     منهما سياسةً. مسارٌ يُضاف غدًا بلا سياسةٍ يسقط هنا، لا في الإنتاج.

  ٣. **أ ← موردُ ب حيًّا** — عبر HTTP على خادمٍ يعمل. لكلِّ مورِدٍ: رقمٌ
     مباشر، ورقمٌ مخمَّن، وترقيمٌ متسلسل، وطلبٌ مُحوَّر، وبلا وثيقةٍ أصلًا،
     وبوثيقةٍ انتهت. والنتيجةُ المقبولة واحدة: لا يصل.

وما يميّز هذا عن `isolation_test.py` أنه يختبر **القرار** لا أثرَه فقط:
هناك نسأل «هل وصل؟»، وهنا نسأل أيضًا «هل قال النظامُ لماذا مَنَع، وهل
يقولها في كل مورِدٍ بالطريقة نفسها؟».
"""
import json, os, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from falah import authz as AZ, routing as RT

OK = FAIL = 0; FAILURES = []
PW = "Str0ng-Pass!x9"

def check(n, c, d=""):
    global OK, FAIL
    if c: OK += 1; print(f"  ✓ {n}" + (f"  ({d})" if d else ""))
    else: FAIL += 1; FAILURES.append((n, d)); print(f"  ✗ {n}" + (f"  ← {d}" if d else ""))

def head(t): print(f"\n▸ {t}")

# ═══════════════════ ١ · القرارُ وحده ═══════════════════

def unit():
    head("can() — قرارٌ صافٍ بلا خادم")
    anon = AZ.ANON
    a = AZ.Subject(1)
    b = AZ.Subject(2)
    admin = AZ.subject_for(1, admin_key_ok=True)

    mine    = AZ.Resource("project", 7, owner_id=1)
    theirs  = AZ.Resource("project", 8, owner_id=2)
    missing = AZ.Resource("project", 9, owner_id=None, exists=False)

    check("صاحبُ المورِد يُسمح له", bool(AZ.can(a, "read", mine)))
    check("وغيرُه يُمنع", not AZ.can(b, "read", mine))
    check("والمنعُ سببُه «غيرُ موجود» لا «ممنوع» — فلا يُكشف وجودُ مورِدِ غيرك",
          AZ.can(b, "read", mine).reason == AZ.NOT_FOUND)
    check("والمجهولُ يُمنع بسبب الوثيقة لا الملكية",
          AZ.can(anon, "read", mine).reason == AZ.UNAUTHENTICATED)
    check("ومورِدٌ لا وجود له يُمنع كما يُمنع مورِدُ غيرك — الردُّ واحد",
          AZ.can(a, "read", missing).reason == AZ.NOT_FOUND
          and AZ.can(a, "read", theirs).reason == AZ.NOT_FOUND)
    check("ومورِدٌ بلا مالكٍ مقروءٍ يُمنع — لا يُفترض أنه لك",
          not AZ.can(a, "read", AZ.Resource("project", 7, owner_id=None)))

    check("المنعُ أصلٌ: فعلٌ لا سياسةَ له يُمنع",
          AZ.can(a, "delete", AZ.Resource("job", 1, owner_id=1)).reason == AZ.NO_POLICY)
    check("ومورِدٌ لا سياسةَ له يُمنع",
          AZ.can(a, "read", AZ.Resource("secrets", 1, owner_id=1)).reason == AZ.NO_POLICY)
    check("وفعلٌ خارج القائمة المغلقة خطأُ برمجةٍ يُرفع لا منعٌ صامت",
          _raises(lambda: AZ.can(a, "teleport", mine), ValueError))

    check("المحتوى العامّ يُقرأ بلا جلسة", bool(AZ.can(anon, "read", AZ.public())))
    check("والسردُ يشترط جلسةً", not AZ.can(anon, "list", AZ.own("project", anon)))

    check("المنحةُ الإدارية تشترط صلاحيةً مسمّاة",
          AZ.can(a, "grant", AZ.own("subscription", a)).reason == AZ.FORBIDDEN)
    check("ومن يملكها يُسمح له", bool(AZ.can(admin, "grant", AZ.own("subscription", admin))))
    check("والصلاحيةُ تُشتقّ من الدور لا تُكتب في المسار",
          admin.has("manage_billing") and not a.has("manage_billing"))
    check("والمجهولُ لا يبلغ المنحة ولو لم يكن ثمّة دور",
          AZ.can(anon, "grant", AZ.own("subscription", anon)).reason == AZ.UNAUTHENTICATED)

    check("مورِدُ الذات لا يُطلب لغيرك",
          not AZ.can(a, "read", AZ.Resource("account", 2, owner_id=2)))
    check("ويُسمح لصاحبه", bool(AZ.can(a, "read", AZ.Resource("account", 1, owner_id=1))))

    # ملفُّ التصدير: المالكُ يُشتقّ من موضع الملفّ، ويُختبر بلا جلسة
    d = tempfile.mkdtemp(prefix="falah-authz-")
    os.makedirs(os.path.join(d, "exports", "2"), exist_ok=True)
    open(os.path.join(d, "exports", "2", "x.png"), "wb").write(b"x")
    open(os.path.join(d, "secret.txt"), "w").write("s")
    r = AZ.export_file(d, "exports/2/x.png")
    check("ملفُّ الصادرات مالكُه مقروءٌ من موضعه", r.owner_id == 2 and r.exists)
    check("وصاحبُه يُسمح له", bool(AZ.can(AZ.Subject(2), "download", r)))
    check("وغيرُه يُمنع", not AZ.can(AZ.Subject(3), "download", r))
    for esc in ("../secret.txt", "exports/../secret.txt", "/etc/passwd",
                "exports/2/../../secret.txt", "exports", "exports/2"):
        rr = AZ.export_file(d, esc)
        check(f"وما خرج من الصادرات فلا مالكَ له: {esc}",
              not AZ.can(AZ.Subject(2), "download", rr), str(rr.owner_id))

def _raises(fn, exc):
    try: fn()
    except exc: return True
    except Exception: return False
    return False

# ═══════════════════ ٢ · اكتمالُ الجدول ═══════════════════

def table():
    head("جدولُ المسارات — لا مسارَ بلا سياسة")
    routes = [r for rs in RT.TABLE.values() for r in rs] + [RT.FALLBACK]
    check("كلُّ مسارٍ أعلن مورِدَه وفعله",
          all(r.resource and r.action for r in routes), f"{len(routes)} مسارًا")
    missing = sorted({(r.resource, r.action) for r in routes} - set(AZ.POLICY))
    check("ولكلِّ زوجٍ (مورِد، فعل) سياسةٌ في POLICY", not missing, str(missing))
    check("وكلُّ فعلٍ من القائمة المغلقة",
          all(r.action in AZ.ACTIONS for r in routes),
          str(sorted({r.action for r in routes} - AZ.ACTIONS)))
    check("وكلُّ معالِجٍ قابلٌ للنداء", all(callable(r.handler) for r in routes))

    ownerful = [r for r in routes if r.owner_field]
    check("وكلُّ مسارٍ يأخذ رقمَ مورِدٍ من الطلب يُحمَّل مورِدُه ويُقارَن مالكُه",
          all(AZ.POLICY[(r.resource, r.action)] is AZ.OWNER for r in ownerful),
          f"{len(ownerful)} مسارًا")

    # مسارٌ لم يُعلَن يقع على القاعدة العامّة — لا يُخترع له إذن
    r, _ = RT.resolve("POST", "/app/does-not-exist")
    check("ومسارٌ غير معلَنٍ يقع على القاعدة العامّة", r is RT.FALLBACK)
    r, _ = RT.resolve("DELETE", "/app/projects")
    check("وطريقةٌ غير معلَنةٍ كذلك", r is RT.FALLBACK)

    check("والمنعُ أصلٌ حتى في القاعدة العامّة — تُشترط وثيقةٌ ثم ٤٠٤",
          AZ.POLICY[(RT.FALLBACK.resource, RT.FALLBACK.action)] is AZ.AUTHENTICATED)

    check("ولا مسارَ يُقرَّر إذنُه باسمه",
          all("/app/" not in str(v) for v in AZ.POLICY.values()))

    exact = [r for rs in RT.TABLE.values() for r in rs if r.kind == "exact"]
    check("ولا مسارَ مكرَّرٌ في الجدول",
          len({(r.method, r.path) for r in exact}) == len(exact))

# ═══════════════════ ٣ · أ ← موردُ ب، حيًّا ═══════════════════

def free_port():
    s = socket.socket(); s.bind(("", 0)); p = s.getsockname()[1]; s.close(); return p

def req(base, path, body=None, cookie=None, hdr=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if data is not None: h["X-FALAH"] = "1"
    if cookie: h["Cookie"] = cookie
    h.update(hdr or {})
    r = urllib.request.Request(base + path, data=data, headers=h,
                               method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            b = x.read()
            try:    return x.status, json.loads(b), x.headers.get_all("Set-Cookie") or []
            except Exception: return x.status, {"bytes": len(b)}, []
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read()), []
        except Exception: return e.code, None, []
    except Exception as e:
        return 0, {"error": type(e).__name__}, []

def live():
    d = tempfile.mkdtemp(prefix="falah-authz-live-")
    port = free_port(); base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, FALAH_APP_DB=os.path.join(d, "app.db"), PORT=str(port),
               FALAH_INLINE_WORKER="0", FALAH_RATE_REGISTER="10000")
    p = subprocess.Popen([sys.executable, "app.py"], cwd=HERE, env=env,
                         stdout=open(os.path.join(d, "app.log"), "w"),
                         stderr=subprocess.STDOUT, start_new_session=True)
    try:
        for _ in range(80):
            if req(base, "/healthz", timeout=2)[0] == 200: break
            time.sleep(0.5)

        def account(tag):
            m = f"{tag}{int(time.time()*1000)%10**9}@authz.test"
            s, dd, ck = req(base, "/app/register",
                            {"email": m, "password": PW, "name": tag, "watermark": tag})
            ck = ck[0].split(";")[0] if ck else None
            uid = req(base, "/app/me", cookie=ck)[1]["user"]["id"]
            return ck, uid

        A, uidA = account("A")
        B, uidB = account("B")
        head("أ ← موردُ ب — رقمٌ مباشر")
        check("حسابان مستقلّان", A and B and uidA != uidB, f"{uidA} · {uidB}")

        pidB = req(base, "/app/projects/create",
                   {"title": "لبٍ وحده", "kind": "series"}, B)[1]["id"]
        req(base, "/app/items/add",
            {"project": pidB, "kind": "quran", "ref": {"surah": 94, "ayah": 5}}, B)
        jobB = req(base, "/app/export", {"project": pidB}, B)[1].get("job", {}).get("id")

        # ــ المشروع: قراءةً وتعديلًا وحذفًا وتصييرًا وعناصرَ ــ
        cases = [
            ("GET  /app/projects/{B}",  ("GET", f"/app/projects/{pidB}", None)),
            ("POST /app/projects/update", ("POST", "/app/projects/update",
                                           {"id": pidB, "title": "استُولي عليه"})),
            ("POST /app/projects/delete", ("POST", "/app/projects/delete", {"id": pidB})),
            ("POST /app/items/add",     ("POST", "/app/items/add",
                                         {"project": pidB, "kind": "quran",
                                          "ref": {"surah": 1, "ayah": 1}})),
            ("POST /app/items/remove",  ("POST", "/app/items/remove",
                                         {"project": pidB, "id": 1})),
            ("POST /app/items/reorder", ("POST", "/app/items/reorder",
                                         {"project": pidB, "order": [1]})),
            ("POST /app/items/accept-drift", ("POST", "/app/items/accept-drift",
                                              {"project": pidB, "id": 1})),
            ("POST /app/export",        ("POST", "/app/export", {"project": pidB})),
            ("POST /app/video",         ("POST", "/app/video",
                                         {"project": pidB, "item": 1})),
        ]
        for name, (m, path, body) in cases:
            s, dd, _ = req(base, path, body, A)
            check(f"أ لا يبلغ مشروع ب — {name}",
                  s == 400 and (dd or {}).get("error") == "المشروع غير موجود",
                  f"{s} {dd}")

        head("أ ← مهمّةُ ب وصادراتُها")
        s, dd, _ = req(base, f"/app/jobs/{jobB}", cookie=A)
        check("أ لا يقرأ مهمّة ب",
              s == 400 and (dd or {}).get("error") == "المهمّة غير موجودة", f"{s} {dd}")
        s, dd, _ = req(base, "/app/jobs/cancel", {"id": jobB}, A)
        check("ولا يلغيها", s == 400 and (dd or {}).get("error") == "المهمّة غير موجودة",
              f"{s} {dd}")
        s, dd, _ = req(base, f"/app/file?p=exports/{uidB}/x.png", cookie=A)
        check("ولا ينزّل ملفًّا من مجلّد ب", s == 404, f"{s} {dd}")
        s, dd, _ = req(base, "/app/exports", cookie=A)
        check("وسردُ الصادرات لا يعدو صاحبَه", s == 200 and dd["exports"] == [],
              str(dd)[:80])

        head("رقمٌ مخمَّن وترقيمٌ متسلسل")
        seen = []
        for pid in range(1, 12):
            s, dd, _ = req(base, f"/app/projects/{pid}", cookie=A)
            if s == 200: seen.append(pid)
        check("مسحُ الأرقام ١..١١ لا يُظهر لأ إلا ما يملكه", not seen, str(seen))
        codes = {req(base, f"/app/jobs/{j}", cookie=A)[0] for j in range(1, 12)}
        check("ومسحُ أرقام المهامّ كذلك — رمزٌ واحدٌ لا يفرّق بين موجودٍ ومملوك",
              codes == {400}, str(codes))
        # الردُّ نفسُه لرقمٍ لا وجود له ولرقمٍ يملكه ب: لا فرقَ يُستدلّ به
        s1 = req(base, f"/app/projects/{pidB}", cookie=A)[1]
        s2 = req(base, "/app/projects/999999", cookie=A)[1]
        check("و«ليس لك» و«غير موجود» ردٌّ واحدٌ حرفًا بحرف", s1 == s2, f"{s1} · {s2}")

        head("طلبٌ مُحوَّر — حقولٌ تُضاف لعلّها تُصدَّق")
        s, dd, _ = req(base, "/app/projects/update",
                       {"id": pidB, "user_id": uidA, "user": uidA, "owner": uidA,
                        "title": "منتحَل"}, A)
        check("حقلُ مالكٍ في الجسم لا يُغيّر شيئًا", s == 400
              and (dd or {}).get("error") == "المشروع غير موجود", f"{s} {dd}")
        s, dd, _ = req(base, "/app/subscription/grant",
                       {"user": uidA, "plan": "studio", "days": 999}, A)
        check("ومنحةٌ لنفسه بلا مفتاحٍ تُمنع", s == 403
              and (dd or {}).get("error") == "غير مصرَّح", f"{s} {dd}")
        s, dd, _ = req(base, "/app/subscription/grant",
                       {"user": uidB, "plan": "studio"}, A,
                       hdr={"X-FALAH-ADMIN": "guess"})
        check("ومفتاحٌ مخمَّنٌ لا يمنح شيئًا", s == 403, f"{s} {dd}")
        s, dd, _ = req(base, "/app/profile", {"name": "ب الجديد", "user": uidB}, A)
        ent = req(base, "/app/me", cookie=B)[1]["user"]["name"]
        check("وتعديلُ الملفّ الشخصيّ لا يمسّ غيرَ صاحب الجلسة",
              s == 200 and ent != "ب الجديد", f"{s} · اسمُ ب = {ent}")

        head("بلا وثيقةٍ، وبوثيقةٍ انتهت")
        for path in ("/app/projects", "/app/jobs", "/app/exports", "/app/limits",
                     "/app/entitlements", "/app/referrals",
                     f"/app/projects/{pidB}", f"/app/jobs/{jobB}",
                     f"/app/file?p=exports/{uidB}/x.png", "/app/not-a-route"):
            s, dd, _ = req(base, path)
            check(f"بلا جلسةٍ: {path}",
                  s == 401 and (dd or {}).get("error") == "يلزم تسجيل الدخول", f"{s} {dd}")
        for path, body in (("/app/projects/update", {"id": pidB}),
                           ("/app/export", {"project": pidB}),
                           ("/app/jobs/cancel", {"id": jobB}),
                           ("/app/subscription/grant", {"plan": "studio"}),
                           ("/app/not-a-route", {})):
            s, dd, _ = req(base, path, body)
            check(f"وبلا جلسةٍ كتابةً: {path}", s == 401, f"{s} {dd}")

        req(base, "/app/logout", {}, A)
        for path in ("/app/projects", f"/app/projects/{pidB}", "/app/entitlements"):
            s, dd, _ = req(base, path, cookie=A)
            check(f"وبعد الخروج لا تنفع الكعكةُ القديمة: {path}", s == 401, f"{s} {dd}")
        s, dd, _ = req(base, "/app/export", {"project": pidB}, A)
        check("ولا في الكتابة", s == 401, f"{s} {dd}")

        head("والعامُّ يبقى عامًّا — المنعُ ليس إغلاقًا للباب")
        for path in ("/app/config", "/app/plans", "/app/me",
                     "/card?kind=quran&surah=94&ayah=5", "/templates?limit=1",
                     "/topics", "/healthz"):
            s, _, _ = req(base, path)
            check(f"يُقرأ بلا حساب: {path}", s == 200, str(s))
    finally:
        p.terminate()
        try: p.wait(timeout=10)
        except Exception: p.kill()

if __name__ == "__main__":
    print("═" * 46)
    print("  فحصُ الإذن — طبقةٌ واحدةٌ تُسأل")
    print("═" * 46)
    unit(); table(); live()
    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: سقط {FAIL} من {OK + FAIL}")
        for n, d in FAILURES: print(f"  ✗ {n}  ← {d}")
        sys.exit(1)
    print(f"النتيجة: الإذن متماسك ✓  ({OK} بندًا)")
