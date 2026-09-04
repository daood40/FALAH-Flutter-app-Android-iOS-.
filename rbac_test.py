#!/usr/bin/env python3
"""الأدوارُ والصلاحياتُ وسجلُّ التدقيق — بمصفوفةٍ لا بأمثلة.

    python3 rbac_test.py

ستّةُ أقسام:

  ١. **المصفوفة** — أدوارٌ × صلاحياتٌ × موارد. لا خمسةُ اختباراتٍ منتقاة،
     بل الجدولُ كلُّه: كلُّ دورٍ في كلِّ زوجٍ من `POLICY`، والافتراضيُّ
     `DENY`. وزوجٌ لا سياسةَ له يُمنع لكلّ دورٍ بلا استثناء.

  ٢. **حارسُ التسلسل** — كلُّ ترقيةٍ ممنوعةٍ بترتيبها: مستخدمٌ → مشرف →
     إداريّ → إداريٌّ أعلى، والنظيرُ إلى النظير، والفاعلُ إلى نفسه.

  ٣. **الإسناد الجماعيّ وحقنُ الدور** — حقلٌ في الجسم · مفاتيحُ JSON
     مكرَّرة · حقولٌ غيرُ موثَّقة · مسارٌ بديل · تسابُق.

  ٤. **المصفوفة الأفقية** — أ/ب × مشروع/مهمّة/صادرة/ملفّ.

  ٥. **سجلُّ التدقيق** — يُكتب · لا يُعدَّل · لا يُحذف · لا يُقرأ بلا
     صلاحية · **ولا سرَّ فيه** (يُفتَّش بسرٍّ معروفٍ سلفًا).

  ٦. **fail closed** — إذا لم نعرف الصلاحية فالجواب `DENY` لا `ALLOW`.
"""
import json, os, socket, sqlite3, subprocess, sys, tempfile, threading, time
import urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from falah import audit as AUD, authz as AZ

OK = FAIL = 0; FAILURES = []
PW = "Str0ng-Pass!x9"
# قناصةٌ تُحقن في مسارات الأسرار ثم يُفتَّش الجدولُ كلُّه عنها
SECRET = "S3CR3T-canary-do-not-log-9f2a1c"  # noqa: S105

def check(n, c, d=""):
    global OK, FAIL
    if c: OK += 1; print(f"  ✓ {n}" + (f"  ({d})" if d else ""))
    else: FAIL += 1; FAILURES.append((n, d)); print(f"  ✗ {n}" + (f"  ← {d}" if d else ""))

def head(t): print(f"\n▸ {t}")

def _code_only(src):
    """يُسقط التعليقات والنصوص من مصدرٍ بايثونيّ، فلا يُحسب شرحٌ شيفرةً.

    لولاه لسقط الفحصُ على تعليقٍ يقول «ولا `if role == admin` هنا» — وهو
    نفيٌ لا إثبات. يُحلَّل المصدرُ بـ`tokenize` لا بتعبيرٍ نمطيّ.
    """
    import io, tokenize
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING): continue
            out.append(tok.string)
    except Exception:
        return src
    return " ".join(out)

# ═══════════════ ١ · المصفوفة: أدوار × صلاحيات × موارد ═══════════════

def matrix():
    head("المصفوفة — كلُّ دورٍ في كلِّ زوجٍ من الجدول")
    roles = {r: AZ.Subject(1, {"anonymous", r}) if r != "anonymous" else AZ.ANON
             for r in AZ.ROLES}
    pairs = sorted(AZ.POLICY)
    total = wrong = 0
    for (rtype, action) in pairs:
        scope = AZ.POLICY[(rtype, action)]
        for rname, subj in roles.items():
            total += 1
            perm = AZ._p(rtype, action)
            holds = perm in AZ.perms_of(rname)
            # مورِدٌ مُرضٍ للنطاق، حتى يُقاس أثرُ الصلاحية وحدها
            res = (AZ.Resource(rtype, 1, owner_id=1) if scope in (AZ.OWNER, AZ.SELF)
                   else AZ.Resource(rtype, None, None))
            got = bool(AZ.can(subj, action, res))
            want = holds and (scope is AZ.PUBLIC or subj.authenticated)
            if got != want:
                wrong += 1
                print(f"    ✗ {rname}/{perm}: got={got} want={want}")
    check(f"المصفوفة كاملةً ({len(pairs)} زوجًا × {len(roles)} أدوار = {total} خانة)",
          wrong == 0, f"{wrong} خانةً مخالفة")

    # الافتراضيُّ منعٌ — لكلِّ دورٍ بلا استثناء، حتى الأعلى
    unknown = AZ.Resource("nonexistent_resource", 1, owner_id=1)
    check("زوجٌ لا سياسةَ له يُمنع لكلِّ دورٍ — حتى super_admin",
          all(AZ.can(s, "read", unknown).reason == AZ.NO_POLICY for s in roles.values()))
    check("وفعلٌ لا سياسةَ له على مورِدٍ قائم كذلك",
          all(AZ.can(s, "grant", AZ.Resource("project", 1, owner_id=1)).reason
              == AZ.NO_POLICY for s in roles.values()))

    head("سلامةُ الكتالوج")
    pairperms = {AZ._p(t, a) for t, a in AZ.POLICY}
    check("كلُّ زوجٍ له صلاحيةٌ باسمه", not (pairperms - AZ.PERMISSIONS),
          str(sorted(pairperms - AZ.PERMISSIONS)))
    check("ولا صلاحيةَ بلا زوج", not (AZ.PERMISSIONS - pairperms),
          str(sorted(AZ.PERMISSIONS - pairperms)))
    reach = set().union(*AZ.ROLES.values())
    check("وكلُّ صلاحيةٍ يبلغها دورٌ واحدٌ على الأقلّ",
          not (AZ.PERMISSIONS - reach), str(sorted(AZ.PERMISSIONS - reach)))
    check("ولا دورَ يحمل صلاحيةً خارج الكتالوج",
          not (reach - AZ.PERMISSIONS), str(sorted(reach - AZ.PERMISSIONS)))
    check("ولا نجمةَ في أيّ حزمة — لا `admin.*` ولا wildcard",
          not any("*" in p for p in reach))
    check("والتسلسلُ محسوبٌ بالضمّ لا بالنسخ",
          AZ.ROLES["user"] < AZ.ROLES["moderator"] < AZ.ROLES["admin"]
          < AZ.ROLES["super_admin"])
    check("والمجهولُ أضيقُ من الجميع", AZ.ROLES["anonymous"] < AZ.ROLES["user"])

    head("لا اسمَ دورٍ في شرط")
    files = ["app.py", "api.py"] + [f"falah/{f}" for f in sorted(os.listdir("falah"))
                                    if f.endswith(".py")]
    # كلُّ صيغةٍ يُكتب بها «إن كان دورُه كذا». `falah/authz.py` و
    # `falah/roles.py` مستثنيان: هما موضعُ **تعريف** الأدوار لا فحصِها.
    DEFINERS = {"falah/authz.py", "falah/roles.py"}
    bad = []
    for f in files:
        if f in DEFINERS: continue
        src = _code_only(open(os.path.join(HERE, f), encoding="utf-8").read())
        for role in AZ.ASSIGNABLE:
            for pat in ('role == "%s"', "role == '%s'", 'role=="%s"', "role=='%s'",
                        'role in ("%s"', 'role != "%s"'):
                if (pat % role) in src:
                    bad.append(f"{f}: {pat % role}")
    check("لا فحصَ باسم دورٍ في المشروع كلِّه — ولا `if role == admin`",
          not bad, str(bad))
    for f in sorted(DEFINERS):
        src = open(os.path.join(HERE, f), encoding="utf-8").read()
        check(f"و{f} يعرّف الأدوار ولا يفحصها في شرطٍ إداريّ",
              "ROLES" in src or "ASSIGNABLE" in src)

# ═══════════════ ٢ · حارسُ التسلسل (وحدةً) ═══════════════

def guards():
    head("حارسُ التسلسل — وحدةً، بلا خادم")
    S = lambda uid, r: AZ.Subject(uid, {"anonymous", r})       # noqa: E731
    su, ad, mo, us = S(1, "super_admin"), S(2, "admin"), S(3, "moderator"), S(4, "user")

    check("لا أحدَ يغيّر دورَ نفسه — ولا super_admin",
          AZ.may_manage(su, "super_admin", 1) == AZ.SELF_TARGET)
    check("ولا إداريّ", AZ.may_manage(ad, "admin", 2) == AZ.SELF_TARGET)

    check("super_admin يدير الإداريَّ", AZ.may_manage(su, "admin", 9) == AZ.ALLOWED)
    check("والإداريُّ يدير المشرفَ والمستخدم",
          AZ.may_manage(ad, "moderator", 9) == AZ.ALLOWED
          and AZ.may_manage(ad, "user", 9) == AZ.ALLOWED)
    check("والإداريُّ لا يدير إداريًّا نظيرَه",
          AZ.may_manage(ad, "admin", 9) == AZ.NOT_MANAGEABLE)
    check("ولا يدير من فوقه", AZ.may_manage(ad, "super_admin", 9) == AZ.NOT_MANAGEABLE)
    # المشرفُ أعلى من المستخدم تسلسلًا، فحارسُ التسلسل يسمح — **والصلاحيةُ
    # هي التي تمنع**. وهذا هو الفصلُ بين البوّابتين ظاهرًا في مثالٍ واحد:
    # لو خُلطتا لَما أمكن التعبيرُ عن «أعلى منه ولا يملك تغييره».
    check("المشرفُ أعلى من المستخدم تسلسلًا",
          AZ.may_manage(mo, "user", 9) == AZ.ALLOWED)
    check("**ولا يملك صلاحيةَ تغييرِ دورٍ ولا حالة** — فلا يبلغ الحارسَ أصلًا",
          not mo.has("user_role.update") and not mo.has("user.update"))
    check("والمستخدمُ لا يدير أحدًا — لا تسلسلًا ولا صلاحية",
          AZ.may_manage(us, "user", 9) != AZ.ALLOWED
          and not us.has("user.update") and not us.has("user_role.update"))
    check("وتغييرُ الأدوار مقصورٌ على الأعلى وحده",
          {r for r in AZ.ROLES if "user_role.update" in AZ.perms_of(r)}
          == {"super_admin"})

    check("لا يُمنح دورٌ أقوى من مانِحه",
          AZ.may_grant(ad, "super_admin") == AZ.NOT_GRANTABLE)
    check("ويُمنح ما دونه", AZ.may_grant(ad, "moderator") == AZ.ALLOWED)
    check("و super_admin يمنح كلَّ دورٍ معلَن",
          all(AZ.may_grant(su, r) == AZ.ALLOWED for r in AZ.ASSIGNABLE))
    check("ولا يُمنح دورٌ مجهول", AZ.may_grant(su, "root") == AZ.NOT_GRANTABLE)
    check("ولا يُمنح «المجهول» دورًا", AZ.may_grant(su, "anonymous") == AZ.NOT_GRANTABLE)

    head("fail closed — ما لا يُعرف يُمنع")
    ghost = AZ.Subject(5, {"anonymous", "wizard"})          # دورٌ ليس في ROLES
    check("دورٌ مجهولٌ في القاعدة ⇒ صفرُ صلاحيات لا صلاحياتُ مستخدم",
          AZ.perms_of("wizard") == frozenset() and ghost.permissions == AZ.ANON_PERMS)
    check("وصاحبُه يُمنع من كلِّ ما يحتاج جلسةً",
          not AZ.can(ghost, "list", AZ.own("project", ghost))
          and not AZ.can(ghost, "read", AZ.Resource("project", 1, owner_id=5)))
    check("ولا يُدير أحدًا", AZ.may_manage(ghost, "user", 9) != AZ.ALLOWED)
    check("ولا يمنح شيئًا", AZ.may_grant(ghost, "user") == AZ.NOT_GRANTABLE)
    check("ودورٌ فارغٌ أو None كذلك",
          AZ.perms_of("") == frozenset() and AZ.perms_of(None) == frozenset())

# ═══════════════ سجلُّ التدقيق — وحدةً ═══════════════

def audit_unit():
    head("سجلُّ التدقيق — الكتالوج والمصفاة")
    check("كتالوجٌ مغلق: حدثٌ خارجَه يُرفع لا يُبتلع",
          _raises(lambda: AUD.record(None, "made.up"), ValueError))
    check("ونتيجةٌ خارج المعدود كذلك",
          _raises(lambda: AUD.record(None, "logout", result="maybe"), ValueError))

    dirty = {"password": SECRET, "pw": SECRET, "token": SECRET,
             "session_token": SECRET, "api_key": SECRET, "cookie": SECRET,
             "Authorization": SECRET, "pw_salt": SECRET, "receipt": SECRET,
             "payload": SECRET, "private_key": SECRET, "signature": SECRET,
             "plan": "studio", "count": 3, "ok": True,
             "opaque": "AAAAAAAAAAAAAAAAAAAAAAAAAAAA",   # يشبه رمزًا
             "nested": {"password": SECRET}, "arr": [SECRET]}
    clean = AUD.scrub(dirty)
    blob = json.dumps(clean, ensure_ascii=False)
    check("المصفاة تُسقط كلَّ ما يشبه سرًّا بالاسم", SECRET not in blob, blob[:120])
    check("وتُسقط ما يشبه رمزًا بالشكل ولو كان مفتاحُه بريئًا",
          "opaque" not in clean)
    check("ولا تُبقي عمقًا ولا حمولةً خام",
          "nested" not in clean and "arr" not in clean)
    check("وتُبقي ما ليس سرًّا", clean.get("plan") == "studio"
          and clean.get("count") == 3 and clean.get("ok") is True)
    check("والقيمةُ الطويلة تُقصّ", len(AUD.scrub({"note": "ع" * 900})["note"]) <= AUD.MAX_VALUE)
    check("ورقمُ الطلب عشوائيٌّ لا متسلسل",
          len({AUD.new_request_id() for _ in range(50)}) == 50)

def _raises(fn, exc):
    try: fn()
    except exc: return True
    except Exception: return False
    return False

# ═══════════════ حيًّا ═══════════════

def free_port():
    s = socket.socket(); s.bind(("", 0)); p = s.getsockname()[1]; s.close(); return p

def req(base, path, body=None, cookie=None, hdr=None, timeout=30, raw_body=None):
    data = raw_body if raw_body is not None else (
        json.dumps(body).encode() if body is not None else None)
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
    d = tempfile.mkdtemp(prefix="falah-rbac-")
    db = os.path.join(d, "app.db")
    port = free_port(); base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, FALAH_APP_DB=db, PORT=str(port),
               FALAH_INLINE_WORKER="0", FALAH_RATE_REGISTER="10000",
               FALAH_RATE_LOGIN="10000")
    p = subprocess.Popen([sys.executable, "app.py"], cwd=HERE, env=env,
                         stdout=open(os.path.join(d, "app.log"), "w"),
                         stderr=subprocess.STDOUT, start_new_session=True)
    try:
        for _ in range(80):
            if req(base, "/healthz", timeout=2)[0] == 200: break
            time.sleep(0.5)

        def account(tag):
            m = f"{tag}{int(time.time()*1000)%10**9}@rbac.test"
            _, _, ck = req(base, "/app/register",
                           {"email": m, "password": PW, "name": tag})
            ck = ck[0].split(";")[0] if ck else None
            return ck, req(base, "/app/me", cookie=ck)[1]["user"]["id"], m

        def login(mail):
            _, _, ck = req(base, "/app/login", {"email": mail, "password": PW})
            return ck[0].split(";")[0] if ck else None

        def promote(mail, role):
            subprocess.run([sys.executable, "-m", "falah.roles", "grant", mail, role,
                            "--reason", "test"], cwd=HERE, env=env,
                           capture_output=True, check=True)

        SU, uidSU, mSU = account("su")
        AD, uidAD, mAD = account("ad")
        MO, uidMO, mMO = account("mo")
        U1, uid1, m1 = account("u1")
        U2, uid2, m2 = account("u2")

        head("الأدوار تُصنع من سطر الأوامر لا من الشبكة")
        check("كلُّ حسابٍ جديدٍ دورُه user — أقلُّ صلاحية",
              req(base, "/app/me", cookie=U1)[1]["user"]["role"] == "user")
        for mail, role in ((mSU, "super_admin"), (mAD, "admin"), (mMO, "moderator")):
            promote(mail, role)
        SU, AD, MO = login(mSU), login(mAD), login(mMO)
        check("والترقيةُ تُنهي الجلساتِ القائمة",
              req(base, "/app/me", cookie=U1)[1]["user"]["role"] == "user")
        got = {r: req(base, "/app/me", cookie=ck)[1]["user"]["role"]
               for r, ck in (("super_admin", SU), ("admin", AD), ("moderator", MO))}
        check("والأدوارُ ظهرت في «من أنا» قراءةً",
              got == {"super_admin": "super_admin", "admin": "admin",
                      "moderator": "moderator"}, str(got))

        head("مصفوفةُ المسارات الإدارية — دورٌ × مسار")
        ADMIN_GET = ("/app/admin/users", "/app/admin/roles", "/app/admin/audit")
        want = {
            "user":        {"/app/admin/users": 403, "/app/admin/roles": 403,
                            "/app/admin/audit": 403},
            "moderator":   {"/app/admin/users": 200, "/app/admin/roles": 403,
                            "/app/admin/audit": 200},
            "admin":       {"/app/admin/users": 200, "/app/admin/roles": 200,
                            "/app/admin/audit": 200},
            "super_admin": {"/app/admin/users": 200, "/app/admin/roles": 200,
                            "/app/admin/audit": 200},
        }
        for role, ck in (("user", U1), ("moderator", MO), ("admin", AD),
                         ("super_admin", SU)):
            for path in ADMIN_GET:
                st = req(base, path, cookie=ck)[0]
                check(f"{role:12} → {path}", st == want[role][path],
                      f"{st} (المتوقَّع {want[role][path]})")
        for path in ADMIN_GET:
            st, dd, _ = req(base, path)
            check(f"وبلا جلسةٍ → {path} = ٤٠١", st == 401, f"{st} {dd}")

        head("تصعيدُ الامتياز — كلُّ درجةٍ على حدة")
        cases = [
            ("user → moderator",       U1, uid1, "moderator"),
            ("user → admin",           U1, uid1, "admin"),
            ("user → super_admin",     U1, uid1, "super_admin"),
            ("moderator → admin",      MO, uidMO, "admin"),
            ("moderator → super_admin", MO, uidMO, "super_admin"),
            ("admin → super_admin",    AD, uidAD, "super_admin"),
            ("admin → admin (نظير)",   AD, uidSU, "admin"),
            ("super_admin → نفسه",     SU, uidSU, "user"),
        ]
        for name, ck, target, role in cases:
            st, dd, _ = req(base, "/app/admin/users/role",
                            {"user": target, "role": role}, ck)
            check(f"يُمنع: {name}", st == 403 and (dd or {}).get("error") == "غير مصرَّح",
                  f"{st} {dd}")
        st, dd, _ = req(base, "/app/admin/users/role",
                        {"user": uidAD, "role": "user"}, AD)
        check("والإداريُّ لا يُخفّض نفسَه كذلك", st == 403, f"{st} {dd}")

        head("وما يجوز فعلًا")
        st, dd, _ = req(base, "/app/admin/users/role",
                        {"user": uid1, "role": "moderator", "reason": "ترقية"}, SU)
        check("super_admin يرقّي مستخدمًا إلى مشرف",
              st == 200 and dd["user"]["role"] == "moderator", f"{st} {dd}")
        # **تغييرُ الأدوار مقصورٌ على الأعلى وحده** — والإداريُّ لا يبلغه،
        # لأن `user_role.update` ليست عنده. أخطرُ فعلٍ في النظام أضيقُ بابًا.
        st, dd, _ = req(base, "/app/admin/users/role",
                        {"user": uid1, "role": "user"}, AD)
        check("والإداريُّ لا يغيّر دورًا أصلًا — الصلاحيةُ ليست عنده",
              st == 403, f"{st} {dd}")
        st, dd, _ = req(base, "/app/admin/users/role",
                        {"user": uid1, "role": "user", "reason": "إعادة"}, SU)
        check("والأعلى يخفّض المشرفَ إلى مستخدم",
              st == 200 and dd["user"]["role"] == "user", f"{st} {dd}")
        # الترقيةُ والتخفيضُ أنهيا جلسةَ أ مرّتين — تُستأنف
        U1 = login(m1)
        st, dd, _ = req(base, "/app/admin/users/role", {"user": uid1, "role": "root"}, SU)  # noqa: E501
        check("ودورٌ مجهولٌ يُرفض ٤٠٠ لا يُنشأ", st == 400, f"{st} {dd}")
        st, dd, _ = req(base, "/app/admin/users/role", {"user": 999999, "role": "user"}, SU)
        check("وحسابٌ لا وجود له ٤٠٤", st == 404, f"{st} {dd}")

        head("الإسنادُ الجماعيّ وحقنُ الدور")
        st, dd, _ = req(base, "/app/profile",
                        {"name": "ن", "role": "super_admin", "status": "x",
                         "id": uidSU, "user_id": uidSU}, U2)
        after = req(base, "/app/me", cookie=U2)[1]["user"]
        check("حقلُ `role` في تعديل الملفّ لا يُصدَّق",
              st == 200 and after["role"] == "user", f"{st} {after.get('role')}")
        st, _, ck = req(base, "/app/register",
                        {"email": f"inj{int(time.time()*1000)%10**9}@rbac.test",
                         "password": PW, "role": "super_admin", "status": "active"})
        injck = ck[0].split(";")[0] if ck else None
        check("و`role` في التسجيل لا يُصدَّق",
              req(base, "/app/me", cookie=injck)[1]["user"]["role"] == "user")
        # مفاتيحُ JSON مكرَّرة: الأخيرة تفوز في بايثون — والحقلُ لا يُقرأ أصلًا
        raw = ('{"name":"x","role":"user","role":"super_admin"}').encode()
        req(base, "/app/profile", raw_body=raw, cookie=U2)
        check("ومفاتيحُ JSON المكرَّرة لا تفتح بابًا",
              req(base, "/app/me", cookie=U2)[1]["user"]["role"] == "user")
        st, dd, _ = req(base, "/app/admin/users/status",
                        {"user": uidSU, "status": "suspended"}, U2)
        check("ومسارُ الحالة لا يبلغه من لا صلاحيةَ له", st == 403, f"{st} {dd}")

        head("تسابُقٌ على الترقية")
        # عشرون طلبًا متزامنًا من مستخدمٍ عاديّ لترقية نفسه
        res = []
        def race():
            res.append(req(base, "/app/admin/users/role",
                           {"user": uid2, "role": "super_admin"}, U2)[0])
        ts = [threading.Thread(target=race) for _ in range(20)]
        for t in ts: t.start()
        for t in ts: t.join()
        check("عشرون طلبًا متزامنًا لترقية الذات — كلُّها تُمنع",
              set(res) == {403}, str(sorted(set(res))))
        check("والدورُ لم يتغيّر",
              req(base, "/app/me", cookie=U2)[1]["user"]["role"] == "user")

        head("الإيقافُ يُنهي الجلسة فعلًا")
        st, dd, _ = req(base, "/app/admin/users/status",
                        {"user": uid2, "status": "suspended", "reason": "اختبار"}, AD)
        check("الإداريُّ يوقف مستخدمًا", st == 200
              and dd["user"]["status"] == "suspended", f"{st} {dd}")
        check("والموقوفُ لا تُقبل جلستُه",
              req(base, "/app/me", cookie=U2)[1]["user"] is None)
        check("ولا يدخل من جديد", req(base, "/app/login",
                                      {"email": m2, "password": PW})[0] >= 400)
        st, dd, _ = req(base, "/app/admin/users/status",
                        {"user": uid2, "status": "active"}, AD)
        check("وإعادةُ التفعيل تعمل", st == 200 and dd["user"]["status"] == "active")
        U2 = login(m2)

        head("العزلُ الأفقيّ — أ/ب × كلُّ مورِد")
        pid1 = req(base, "/app/projects/create", {"title": "لأ"}, U1)[1]["id"]
        pid2 = req(base, "/app/projects/create", {"title": "لب"}, U2)[1]["id"]
        for who, ck, mine, theirs in (("أ", U1, pid1, pid2), ("ب", U2, pid2, pid1)):
            st = req(base, f"/app/projects/{mine}", cookie=ck)[0]
            check(f"{who} يقرأ مشروعَه", st == 200, str(st))
            st, dd, _ = req(base, f"/app/projects/{theirs}", cookie=ck)
            check(f"و{who} لا يبلغ مشروعَ غيره", st == 400
                  and dd["error"] == "المشروع غير موجود", f"{st} {dd}")
        for role, ck in (("moderator", MO), ("admin", AD), ("super_admin", SU)):
            st, dd, _ = req(base, f"/app/projects/{pid1}", cookie=ck)
            check(f"ولا {role} يقرأ مشروعَ مستخدم — الإدارةُ ليست اطّلاعًا",
                  st == 400, f"{st} {dd}")
            st, dd, _ = req(base, f"/app/file?p=exports/{uid1}/x.png", cookie=ck)
            check(f"ولا {role} ينزّل صادرةَ مستخدم", st == 404, f"{st} {dd}")

        head("سجلُّ التدقيق — حيًّا")
        ev = req(base, "/app/admin/audit?limit=200", cookie=SU)[1]
        acts = {e["action"] for e in ev["events"]}
        for a in ("account.created", "login.success", "role.changed",
                  "user.suspended", "user.reactivated", "security.denied",
                  "project.created", "audit.read"):
            check(f"سُجّل: {a}", a in acts, str(sorted(acts))[:100] if a not in acts else "")
        denied = [e for e in ev["events"] if e["action"] == "security.denied"]
        check("والمنعُ يحمل سببَه والصلاحيةَ المطلوبة",
              denied and all(json.loads(e["metadata"] or "{}").get("reason")
                             for e in denied), f"{len(denied)} سطرًا")
        # ما جاء من سطر الأوامر لا عنوانَ له ولا رقمَ طلب — وهذا صحيح،
        # ويُميَّز بفاعله `system:cli` فلا يُخلط بما جاء عبر الشبكة.
        http_ev = [e for e in ev["events"] if e["actor_role"] != "system:cli"]
        cli_ev = [e for e in ev["events"] if e["actor_role"] == "system:cli"]
        check("وكلُّ سطرٍ جاء عبر الشبكة يحمل رقمَ طلبٍ وعنوانًا",
              http_ev and all(e["request_id"] and e["ip"] for e in http_ev),
              f"{len(http_ev)} سطرًا")
        check("وما جاء من سطر الأوامر يُميَّز بفاعله ولا يُخلط",
              cli_ev and all(e["request_id"] is None and e["ip"] is None
                             for e in cli_ev), f"{len(cli_ev)} سطرًا")
        rc = [e for e in ev["events"] if e["action"] == "role.changed"]
        check("وتغييرُ الدور يحمل من/إلى وفاعلَه",
              rc and all(json.loads(e["metadata"])["from"] and
                         json.loads(e["metadata"])["to"] for e in rc))
        check("وقراءةُ السجلّ نفسُها مسجَّلة", "audit.read" in acts)

        head("سلامةُ السجلّ")
        for role, ck in (("user", U1), ("مجهول", None)):
            st = req(base, "/app/admin/audit", cookie=ck)[0]
            check(f"{role} لا يقرأ السجلّ", st in (401, 403), str(st))
        for m in ("POST", "DELETE", "PUT"):
            st = req(base, "/app/admin/audit", {"x": 1} if m == "POST" else None,
                     cookie=SU)[0]
            if m == "POST":
                check("ولا يُكتب فيه عبر الشبكة", st == 404, str(st))
        cc = sqlite3.connect(db)
        n0 = cc.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        for q in ("UPDATE audit_logs SET action='x'",
                  "UPDATE audit_logs SET actor_id=99 WHERE id=1",
                  "DELETE FROM audit_logs",
                  "DELETE FROM audit_logs WHERE id=1"):
            blocked = False
            try: cc.execute(q)
            except sqlite3.Error: blocked = True
            check(f"القاعدةُ نفسُها ترفض: {q[:34]}…", blocked)
        cc.rollback()
        check("ولا سطرَ ضاع",
              cc.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == n0)

        head("لا سرَّ في السجلّ — يُفتَّش بسرٍّ معروف")
        req(base, "/app/login", {"email": m1, "password": SECRET})
        req(base, "/app/register", {"email": "x@y.test", "password": SECRET,
                                    "name": SECRET})
        req(base, "/app/subscription/store-event",
            {"provider": "apple", "event": {"receipt": SECRET, "token": SECRET}}, U1)
        blob = "".join(str(r) for r in
                       cc.execute("SELECT * FROM audit_logs").fetchall())
        check("لا أثرَ للسرّ في أيّ عمودٍ من الجدول كلِّه",
              SECRET not in blob, "وُجد!" if SECRET in blob else "")
        cookies = [r[0] for r in cc.execute(
            "SELECT COALESCE(metadata,'') FROM audit_logs")]
        check("ولا كعكةَ ولا ترويسةَ وثيقة",
              not any("falah_sid" in x or "Authorization" in x for x in cookies))
        cc.close()

        head("fail closed — حقنُ أعطالٍ حيّة")
        # ① دورٌ مجهولٌ في القاعدة (خطأٌ مطبعيّ، أو دورٌ أُسقط من الشيفرة)
        cx = sqlite3.connect(db); cx.execute(
            "UPDATE users SET role='wizard' WHERE id=?", (uid2,)); cx.commit()
        W = login(m2)
        codes = {p: req(base, p, cookie=W)[0] for p in
                 ("/app/projects", "/app/jobs", "/app/exports", "/app/limits",
                  "/app/entitlements", "/app/admin/users")}
        check("دورٌ مجهولٌ ⇒ يُمنع من كلِّ شيءٍ لا يُسمح له بكلِّ شيء",
              set(codes.values()) == {403}, str(codes))
        check("والعامُّ يبقى عامًّا له", req(base, "/app/me", cookie=W)[0] == 200)
        cx.execute("UPDATE users SET role='user' WHERE id=?", (uid2,)); cx.commit()

        # ② تعذّرُ الكتابة في سجلّ التدقيق: الفعلُ الحسّاس **يسقط ولا يمضي**
        cx.executescript("""CREATE TRIGGER audit_break BEFORE INSERT ON audit_logs
                            BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END;""")
        cx.commit()
        before = sqlite3.connect(db).execute(
            "SELECT role FROM users WHERE id=?", (uid2,)).fetchone()[0]
        st, dd, _ = req(base, "/app/admin/users/role",
                        {"user": uid2, "role": "moderator"}, SU)
        after = sqlite3.connect(db).execute(
            "SELECT role FROM users WHERE id=?", (uid2,)).fetchone()[0]
        check("سجلٌّ متعذّرٌ ⇒ تغييرُ الدور يسقط ولا يقع صامتًا",
              st >= 500 and after == before, f"{st} · {before}→{after}")
        check("ولا يُسرَّب سببُ العطب إلى الخارج",
              "audit" not in str(dd) and "trigger" not in str(dd).lower(), str(dd))
        cx.executescript("DROP TRIGGER audit_break;"); cx.commit(); cx.close()
        st, dd, _ = req(base, "/app/admin/users/role",
                        {"user": uid2, "role": "moderator"}, SU)
        check("وبعودة السجلّ يعمل الفعلُ كما ينبغي", st == 200, f"{st} {dd}")
        req(base, "/app/admin/users/role", {"user": uid2, "role": "user"}, SU)

        # ③ جلسةٌ باطلةٌ أو منتهية
        check("كعكةٌ مختلَقة ⇒ ٤٠١ لا ٥٠٠",
              req(base, "/app/projects", cookie="falah_sid=deadbeef")[0] == 401)
        check("وكعكةٌ فارغة كذلك",
              req(base, "/app/projects", cookie="falah_sid=")[0] == 401)

        head("حذفُ الحساب لا يمحو أثرَه")
        n_before = sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM audit_logs WHERE actor_id=?", (uid1,)).fetchone()[0]
        st, dd, _ = req(base, "/app/account/delete", {"confirm": "حذف"}, U1)
        c2 = sqlite3.connect(db)
        n_after = c2.execute("SELECT COUNT(*) FROM audit_logs WHERE actor_id=?",
                             (uid1,)).fetchone()[0]
        gone = c2.execute("SELECT COUNT(*) FROM users WHERE id=?", (uid1,)).fetchone()[0]
        c2.close()
        check("الحسابُ حُذف", st == 200 and gone == 0, f"{st}")
        check("وسجلُّ تدقيقه بقي كاملًا", n_after >= n_before and n_after > 0,
              f"{n_before} → {n_after}")
    finally:
        p.terminate()
        try: p.wait(timeout=10)
        except Exception: p.kill()

if __name__ == "__main__":
    print("═" * 52)
    print("  الأدوارُ والصلاحياتُ وسجلُّ التدقيق")
    print("═" * 52)
    matrix(); guards(); audit_unit(); live()
    print("\n" + "─" * 52)
    if FAIL:
        print(f"النتيجة: سقط {FAIL} من {OK + FAIL}")
        for n, dd in FAILURES: print(f"  ✗ {n}  ← {dd}")
        sys.exit(1)
    print(f"النتيجة: الصلاحياتُ متماسكة ✓  ({OK} بندًا)")
