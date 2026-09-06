#!/usr/bin/env python3
"""الثوابتُ الأمنية — بأسمائها، في بوّابةٍ مستقلّة.

    python3 invariants.py            # يطبع الجدول ويسقط عند أول خرق
    python3 invariants.py --list     # يعرض الأسماء وما يعنيه كلٌّ منها

**ولماذا ملفٌّ مستقلٌّ وحزمُ الاختبار موجودة؟** لأن الحزمَ تختبر
*السلوك*، وهذه تُثبّت *الشكل*. الفرقُ عمليّ: اختبارُ سلوكٍ يقول «هذا
الطلبُ مُنع»، وثابتُ شكلٍ يقول «**لا يمكن** أن يُسمح، لأن البنيةَ لا
تحتمله». الأولُ يمرّ اليوم وقد يسقط غدًا بمسارٍ جديد؛ والثاني يسقط
**لحظةَ يُكتب المسارُ الجديد** لا لحظةَ يُستغَلّ.

وأهمُّها `NEW_OPERATION_WITHOUT_PERMISSION`: مسارٌ يُضاف بلا صلاحيةٍ
**يُسقط البوّابة**. هذا هو المقصود بـsecure by construction — لا انتباهُ
مراجعٍ بعد ستّة أشهر.

كلُّ ثابتٍ هنا **دائم**. ولا يُحذف ولا يُخفَّف إلا بقرارٍ صريحٍ مكتوب،
ومَن أراد توسيعَ نطاقٍ (أن يقرأ إداريٌّ محتوى الناس مثلًا) فليضف صلاحيةً
باسمها ونطاقًا ويحدّث الثابتَ صراحةً — لا أثرًا جانبيًّا.
"""
import io, os, sys, tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from falah import audit as AUD, authz as AZ, routing as RT  # noqa: E402

INV = []

def invariant(name, what):
    def deco(fn):
        INV.append((name, what, fn)); return fn
    return deco

def _roles(*names):
    return [AZ.Subject(1, {"anonymous", n}) for n in names]

ALL_ROLES = tuple(AZ.ROLES)

# ═══════════════════ ١ · قرارُ الإذن ═══════════════════

@invariant("AUTHZ_DEFAULT_DENY",
           "زوجٌ (مورِد، فعل) لا سياسةَ له يُمنع — لكلِّ دورٍ بلا استثناء")
def _default_deny():
    bad = []
    for r in ALL_ROLES:
        s = AZ.Subject(1, {"anonymous", r})
        for res, act in (("nonexistent_resource", "read"), ("project", "grant"),
                         ("audit", "delete"), ("user", "download")):
            d = AZ.can(s, act, AZ.Resource(res, 1, owner_id=1))
            if d or d.reason != AZ.NO_POLICY: bad.append((r, res, act, d.reason))
    return not bad, str(bad)

@invariant("UNKNOWN_PERMISSION_DENY",
           "صلاحيةٌ ليست في الكتالوج لا يملكها دورٌ، ولا تُشتقّ من زوجٍ غير معلَن")
def _unknown_perm():
    reach = set().union(*AZ.ROLES.values())
    extra = sorted(reach - AZ.PERMISSIONS)
    ghost = AZ.Subject(1, {"anonymous", "super_admin"})
    leaks = [p for p in ("system.manage", "admin.all", "*", "project.*")
             if ghost.has(p)]
    return not extra and not leaks, f"خارج الكتالوج={extra} · مُخترَعة={leaks}"

@invariant("UNKNOWN_ROLE_DENY",
           "دورٌ لا تعرفه ROLES يُعطي صفرَ صلاحيات — fail closed لا fail open")
def _unknown_role():
    cases = ["wizard", "", None, "ADMIN", "super_admin ", "root"]
    bad = [c for c in cases if AZ.perms_of(c) != frozenset()]
    ghost = AZ.Subject(9, {"anonymous", "wizard"})
    ok_deny = (not AZ.can(ghost, "list", AZ.own("project", ghost))
               and not AZ.can(ghost, "read", AZ.Resource("project", 1, owner_id=9))
               and AZ.may_grant(ghost, "user") != AZ.ALLOWED
               and AZ.may_manage(ghost, "user", 5) != AZ.ALLOWED)
    return not bad and ok_deny, f"أدوارٌ أعطت صلاحيات={bad}"

@invariant("UNAUTHENTICATED_DENY",
           "كلُّ نطاقٍ غير PUBLIC يشترط جلسةً — والسببُ «لا وثيقة» لا «ممنوع»")
def _unauth():
    bad = []
    for (t, a), scope in AZ.POLICY.items():
        if scope is AZ.PUBLIC: continue
        d = AZ.can(AZ.ANON, a, AZ.Resource(t, 1, owner_id=1))
        if d or d.reason != AZ.UNAUTHENTICATED: bad.append((t, a, d.reason))
    pub = [(t, a) for (t, a), s in AZ.POLICY.items() if s is AZ.PUBLIC]
    return not bad, f"{len(pub)} زوجًا عامًّا · خروق={bad}"

@invariant("OWNER_SCOPE_ENFORCED",
           "نطاقُ OWNER يقارن مالكًا **محمَّلًا من القاعدة** — ولا يُفترض ولا يُصدَّق")
def _owner_scope():
    owned = [(t, a) for (t, a), s in AZ.POLICY.items() if s is AZ.OWNER]
    bad = []
    for t, a in owned:
        for r in ALL_ROLES:
            if r == "anonymous": continue
            s = AZ.Subject(1, {"anonymous", r})
            for res, why in ((AZ.Resource(t, 5, owner_id=2), "مالكٌ آخر"),
                             (AZ.Resource(t, 5, owner_id=None), "بلا مالكٍ مقروء"),
                             (AZ.Resource(t, 5, owner_id=None, exists=False), "غيرُ موجود")):
                d = AZ.can(s, a, res)
                if d or d.reason != AZ.NOT_FOUND: bad.append((r, t, a, why, d.reason))
    # المجموعةُ **مثبَّتةٌ بالاسم** لا بعددٍ أدنى: تضييقُها يعني مورِدًا خرج
    # من حراسة الملكية، وتوسيعُها يعني نطاقًا تغيّر. وكلاهما قرارٌ يجب أن
    # يظهر في الفرق لا أن يمرّ صامتًا.
    # المجموعةُ مثبَّتةٌ بالاسم لا بالعدد: إضافةُ زوجٍ بنطاق OWNER **يجب**
    # أن تُسقط هذا الثابتَ حتى يُحدَّث هنا بوعي. وقد سقط فعلًا حين أُضيفت
    # الجدولةُ — وهذا هو المقصود: تغييرٌ في حدود الملكيّة يظهر في الفرق
    # ولا يمرّ صامتًا.
    EXPECTED = {("project", "read"), ("project", "update"), ("project", "delete"),
                ("project", "render"), ("project_item", "create"),
                ("project_item", "update"), ("project_item", "delete"),
                ("job", "read"), ("job", "cancel"), ("export_file", "download"),
                # الجدولة: القراءةُ والتعديلُ والحذفُ ملكيّةٌ صريحة.
                # و`schedule.create` ليست هنا عمدًا — نطاقُها المشروعُ لا
                # الجدول: لا جدولَ بعدُ ليُملَك، والمحروسُ أن يكون المشروعُ لك.
                ("schedule", "read"), ("schedule", "update"),
                ("schedule", "delete")}
    drift = sorted(set(owned) ^ EXPECTED)
    return not bad and not drift, \
        f"{len(owned)} زوجًا بنطاق OWNER · انحراف={drift} · خروق={bad[:4]}"

@invariant("SUPER_ADMIN_DOES_NOT_BYPASS_RESOURCE_SCOPE",
           "أعلى دورٍ لا يبلغ مورِدًا يملكه غيره — والإدارةُ ليست اطّلاعًا على المحتوى")
def _super_no_bypass():
    """**عقدٌ أمنيٌّ دائم.**

    `super_admin ≠ read every user's project` و`admin ≠ content visibility`.
    الإدارةُ تُدير الحسابات والأدوار والفوترة، **ولا تحصل تلقائيًّا على
    محتوى المستخدمين**.

    وتوسيعُ هذا مستقبلًا لا يكون أثرًا جانبيًّا: من أراده فليُنشئ صلاحيةً
    باسمها ونطاقًا صريحًا، ويحدّث هذا الثابتَ في الشيفرة — فيظهر التغييرُ
    في الفرق ولا يمرّ صامتًا.
    """
    CONTENT = ("project", "project_item", "job", "export_file", "export")
    bad = []
    for role in ("moderator", "admin", "super_admin"):
        s = AZ.Subject(1, {"anonymous", role})
        for (t, a), scope in AZ.POLICY.items():
            if t not in CONTENT: continue
            if scope is not AZ.OWNER:
                if scope not in (AZ.AUTHENTICATED,):
                    bad.append(("نطاقٌ أوسعُ من OWNER", t, a, role))
                continue
            d = AZ.can(s, a, AZ.Resource(t, 7, owner_id=999))
            if d: bad.append(("بلغ مورِدَ غيره", t, a, role))
    # ولا دورَ إداريٍّ يحمل صلاحيةَ محتوًى لا يحملها المستخدم العاديّ
    extra = sorted((AZ.ROLES["super_admin"] - AZ.ROLES["user"]))
    content_extra = [p for p in extra if p.split(".")[0] in CONTENT]
    return not bad and not content_extra, \
        f"خروق={bad[:4]} · صلاحياتُ محتوًى إداريةٌ زائدة={content_extra}"

@invariant("ROLE_ESCALATION_GUARDED",
           "لا أحدَ يمسّ نفسَه · ولا يمنح ما لا يملك · ولا يُدير من ليس دونه")
def _escalation():
    S = {r: AZ.Subject(i + 1, {"anonymous", r}) for i, r in enumerate(AZ.ASSIGNABLE)}
    bad = []
    for r, s in S.items():                       # ق١ — ولا استثناءَ لأحد
        if AZ.may_manage(s, r, s.user_id) != AZ.SELF_TARGET:
            bad.append(("ق١", r))
    for r, s in S.items():                       # ق٢
        for tgt in AZ.ASSIGNABLE:
            allowed = AZ.perms_of(tgt) <= s.permissions
            if (AZ.may_grant(s, tgt) == AZ.ALLOWED) != allowed:
                bad.append(("ق٢", r, tgt))
    for r, s in S.items():                       # ق٣
        for tgt in AZ.ASSIGNABLE:
            allowed = AZ.perms_of(tgt) < s.permissions
            if (AZ.may_manage(s, tgt, 9999) == AZ.ALLOWED) != allowed:
                bad.append(("ق٣", r, tgt))
    # ولا دورَ يُمنح خارج المعلَن
    for junk in ("root", "anonymous", "SUPER_ADMIN", ""):
        if AZ.may_grant(S["super_admin"], junk) == AZ.ALLOWED:
            bad.append(("دورٌ مجهولٌ مُنح", junk))
    # وتغييرُ الأدوار مقصورٌ على من يملك صلاحيتَه
    holders = {r for r in AZ.ROLES if "user_role.update" in AZ.perms_of(r)}
    if holders != {"super_admin"}: bad.append(("حَمَلةُ user_role.update", holders))
    return not bad, str(bad[:6])

@invariant("NEW_OPERATION_WITHOUT_PERMISSION",
           "**كلُّ مسارٍ معلَنٍ له صلاحيةٌ باسمه وسياسةٌ — ومسارٌ جديدٌ بلا ذلك يُسقط البوّابة**")
def _no_op_without_perm():
    routes = [r for rs in RT.TABLE.values() for r in rs] + [RT.FALLBACK]
    no_policy = sorted({(r.resource, r.action) for r in routes} - set(AZ.POLICY))
    no_perm = sorted({AZ._p(r.resource, r.action) for r in routes} - AZ.PERMISSIONS)
    bad_action = sorted({r.action for r in routes} - AZ.ACTIONS)
    undeclared = [f"{r.method} {r.path}" for r in routes if not (r.resource and r.action)]
    # وتقابلٌ تامٌّ في الاتجاهين: لا صلاحيةَ ميتة، ولا زوجَ بلا صلاحية
    pair_perms = {AZ._p(t, a) for t, a in AZ.POLICY}
    dead = sorted(AZ.PERMISSIONS - pair_perms)
    orphan = sorted(pair_perms - AZ.PERMISSIONS)
    unreachable = sorted(AZ.PERMISSIONS - set().union(*AZ.ROLES.values()))
    ok = not (no_policy or no_perm or bad_action or undeclared or dead
              or orphan or unreachable)
    return ok, (f"{len(routes)} مسارًا · {len(AZ.PERMISSIONS)} صلاحية · "
                f"بلا سياسة={no_policy} · بلا صلاحية={no_perm} · "
                f"ميتة={dead} · يتيمة={orphan} · لا يبلغها دور={unreachable}")

@invariant("NO_ROLE_NAME_IN_CONDITION",
           "لا `if role == \"admin\"` في المشروع — القرارُ على الصلاحية لا على الاسم")
def _no_role_names():
    DEFINERS = {"falah/authz.py", "falah/roles.py"}
    files = ["app.py", "api.py"] + [f"falah/{f}" for f in sorted(os.listdir("falah"))
                                    if f.endswith(".py")]
    bad = []
    for f in files:
        if f in DEFINERS: continue
        src = _code_only(open(os.path.join(HERE, f), encoding="utf-8").read())
        for role in AZ.ASSIGNABLE:
            for pat in ('role == "%s"', "role == '%s'", 'role=="%s"', "role=='%s'",
                        'role != "%s"', 'role in ("%s"'):
                if (pat % role) in src: bad.append(f"{f}: {pat % role}")
    # ولا مسارَ مذكورٌ في جدول السياسة
    named = [str(v) for v in AZ.POLICY.values() if "/app/" in str(v)]
    return not bad and not named, str(bad or named)

def _code_only(src):
    """يُسقط التعليقات والنصوص، فلا يُحسب شرحٌ شيفرةً."""
    try:
        return " ".join(t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
                        if t.type not in (tokenize.COMMENT, tokenize.STRING))
    except Exception:
        return src

# ═══════════════════ ٢ · سجلُّ التدقيق ═══════════════════

@invariant("AUDIT_APPEND_ONLY",
           "لا مسارَ ولا دالّةَ تعدّل سجلَّ التدقيق أو تحذف منه — والقاعدةُ تمنع فوق ذلك")
def _append_only():
    src = open(os.path.join(HERE, "falah", "audit.py"), encoding="utf-8").read()
    code = _code_only(src).upper()
    bad = [k for k in ("UPDATE AUDIT_LOGS", "DELETE FROM AUDIT_LOGS") if k in code]
    st = open(os.path.join(HERE, "falah", "store.py"), encoding="utf-8").read()
    mg = open(os.path.join(HERE, "falah", "migrate.py"), encoding="utf-8").read()
    triggers = all(x in st and x in mg for x in
                   ("audit_logs_no_update", "audit_logs_no_delete"))
    # ولا يُحذف السجلُّ مع الحساب
    au = _code_only(open(os.path.join(HERE, "falah", "auth.py"), encoding="utf-8").read())
    in_delete = "audit_logs" in au
    # ولا مسارَ كتابةٍ أو حذفٍ في الجدول
    routes = [f"{r.method} {r.path}" for rs in RT.TABLE.values() for r in rs
              if r.resource == "audit" and r.action != "list"]
    return not bad and triggers and not in_delete and not routes, \
        f"عباراتٌ هادمة={bad} · مُشغِّلان={triggers} · في الحذف={in_delete} · مسارات={routes}"

@invariant("AUDIT_NO_SECRETS",
           "مصفاةُ السجلّ تُسقط كلَّ ما يشبه سرًّا — بالاسم وبالشكل، حذفًا لا تنجيمًا")
def _no_secrets():
    canary = "K4N4RY-secret-value-abcdef0123456789"
    dirty = {k: canary for k in
             ("password", "pw", "pw_hash", "pw_salt", "token", "session_token",
              "api_key", "apiKey", "cookie", "Authorization", "authorization",
              "secret", "credential", "private_key", "signature", "receipt",
              "payload", "reset_token", "csrf_token")}
    dirty.update({"nested": {"password": canary}, "arr": [canary],
                  "opaque": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                  "plan": "studio", "n": 7, "ok": True})
    out = AUD.scrub(dirty)
    leaked = [k for k, v in out.items() if canary in str(v)]
    kept = out.get("plan") == "studio" and out.get("n") == 7 and out.get("ok") is True
    no_star = not any("*" in str(v) for v in out.values())
    return not leaked and kept and no_star and "opaque" not in out, \
        f"تسرَّب={leaked} · أبقى المفيد={kept}"

@invariant("AUDIT_UNAUTHORIZED_ACCESS_DENIED",
           "قراءةُ السجلّ صلاحيةٌ مسمّاة لا يملكها المستخدم ولا المجهول")
def _audit_access():
    bad = []
    for r in ALL_ROLES:
        s = AZ.Subject(1, {"anonymous", r}) if r != "anonymous" else AZ.ANON
        allowed = bool(AZ.can(s, "list", AZ.Resource("audit", None, None)))
        want = "audit.list" in AZ.perms_of(r) and r != "anonymous"
        if allowed != want: bad.append((r, allowed, want))
    holders = {r for r in AZ.ROLES if "audit.list" in AZ.perms_of(r)}
    return not bad and "user" not in holders and "anonymous" not in holders, \
        f"يقرؤه={sorted(holders)} · خروق={bad}"

@invariant("AUDIT_CATALOGUE_CLOSED",
           "كتالوجُ الأحداث مغلق — حدثٌ خارجَه يُرفع لا يُبتلع")
def _audit_catalogue():
    try:
        AUD.record(None, "made.up.event")
        return False, "قَبِل حدثًا خارج الكتالوج"
    except ValueError:
        pass
    except Exception as e:
        return False, f"رفضه بخطأٍ آخر: {type(e).__name__}"
    try:
        AUD.record(None, "logout", result="maybe")
        return False, "قَبِل نتيجةً خارج المعدود"
    except ValueError:
        return True, f"{len(AUD.ACTIONS)} حدثًا · {len(AUD.RESULTS)} نتائج"
    except Exception as e:
        return False, f"رفضه بخطأٍ آخر: {type(e).__name__}"

@invariant("PERMISSION_CATALOGUE_DOCUMENTED",
           "كتالوجُ الصلاحيات مولَّدٌ من الشيفرة ومحدَّث — ولا صلاحيةَ ميتة ولا عملٌ حسّاسٌ بلا تسجيل")
def _catalogue():
    import perms_report as PR
    unaudited, dead, unreachable = PR.audit_gaps()
    cur = open(PR.OUT, encoding="utf-8").read() if os.path.exists(PR.OUT) else ""
    stale = cur.strip() != PR.table().strip()
    return not (unaudited or dead or unreachable or stale), \
        (f"حسّاسٌ بلا تسجيل={unaudited} · ميتة={dead} · "
         f"لا يبلغها دور={unreachable} · متقادم={stale}")

# ═══════════════════ ٣ · قراراتٌ مؤجَّلةٌ لا تُنسى ═══════════════════

@invariant("B21_ENUMERATION_DEFERRED_DOCUMENTED",
           "قرارُ تأجيل تعداد الحسابات موثَّقٌ، والسلوكُ لم يتغيّر صمتًا")
def _b21():
    """يمنع أن يُنسى القرارُ أو يُغيَّر بلا تحديثِ سجلّه.

    ولا يدّعي أن الخطرَ حُلّ — بل يثبت أنه **معروفٌ ومكتوبٌ ومحدود**.
    """
    bl = open(os.path.join(HERE, "P1_BACKLOG.md"), encoding="utf-8").read()
    card = all(x in bl for x in ("B21    = DEFERRED", "Reason =", "Risk   =", "Owner  ="))
    au = open(os.path.join(HERE, "falah", "auth.py"), encoding="utf-8").read()
    # السلوكُ القائم: التسجيلُ يكشف، والدخولُ والاستعادةُ لا يكشفان
    reveals = "هذا البريد مسجَّل من قبل" in au
    login_generic = "البريد أو كلمة المرور غير صحيحة" in au
    forgot_generic = "لا يُفصح عن وجود البريد من عدمه" in au
    return card and reveals and login_generic and forgot_generic, \
        f"بطاقة={card} · التسجيل يكشف={reveals} · الدخول عامّ={login_generic}"

@invariant("B23_413_SEMANTICS_DOCUMENTED",
           "حدُّ الجسم: دلالةُ HTTP مفصولةٌ عن سلوك النقل، والحدُّ مكتوب")
def _b23():
    bl = open(os.path.join(HERE, "P1_BACKLOG.md"), encoding="utf-8").read()
    card = "B23    = KNOWN LIMITATION" in bl
    it = open(os.path.join(HERE, "isolation_test.py"), encoding="utf-8").read()
    split = "def oversized(" in it and "سلوكُ النقل" in it
    ap = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    still = "close_connection = True" in ap and "413" in ap
    return card and split and still, f"بطاقة={card} · مفصول={split} · السلوك كما هو={still}"

# ═══════════════════ المشغّل ═══════════════════

def main(argv):
    if "--list" in argv:
        for name, what, _ in INV: print(f"  {name:44} {what}")
        return 0
    print("═" * 78)
    print("  الثوابت الأمنية — دائمةٌ لا تُخفَّف")
    print("═" * 78)
    failed = []
    for name, what, fn in INV:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name:44} {'PASS' if ok else 'FAIL'}")
        if detail and not ok: print(f"      {detail}")
        elif detail: print(f"      {detail[:110]}")
        if not ok: failed.append((name, what, detail))
    print("─" * 78)
    if failed:
        print(f"خُرقت {len(failed)} من {len(INV)}:")
        for n, w, d in failed:
            print(f"  ✗ {n}\n      المعنى : {w}\n      التفصيل: {d}")
        print("\nQUALITY_GATE = FAIL")
        return 1
    print(f"النتيجة: {len(INV)} ثابتًا صامدة ✓")
    print("QUALITY_GATE = PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
