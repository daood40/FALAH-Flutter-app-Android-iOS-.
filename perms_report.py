#!/usr/bin/env python3
"""كتالوجُ الصلاحيات — يُولَّد من الشيفرة لا يُكتب بجانبها.

    python3 perms_report.py            # يكتب docs/PERMISSIONS.md
    python3 perms_report.py --check    # يسقط إن تقادم

جدولٌ يُقرأ في نظرة: الصلاحية · العملية · المورِد · النطاق · الأدوار التي
تملكها · أتُسجَّل في التدقيق؟ · أعليها حدُّ معدّل؟

وثيقةٌ كهذه تُكتب باليد تتقادم في أسبوع. تُقرأ من `authz.POLICY` و
`authz.ROLES` و`routing.TABLE` و`audit.ACTIONS` في كل مرّة، فما في
الشيفرة هو ما في الجدول.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from falah import audit as AUD, authz as AZ, routing as RT  # noqa: E402

OUT = os.path.join(HERE, "docs", "PERMISSIONS.md")

SCOPE_NAME = {AZ.PUBLIC: "PUBLIC", AZ.AUTHENTICATED: "AUTH",
              AZ.SELF: "SELF", AZ.OWNER: "OWNER", AZ.ANY: "ANY"}

SCOPE_WHAT = {
    "PUBLIC": "بلا جلسةٍ ولا مورِد — والمجهولُ يملك الصلاحية",
    "AUTH":   "جلسةٌ فقط — لا رقمَ مورِدٍ يأتي من الطلب",
    "SELF":   "صاحبُ الجلسة نفسُه لا غير",
    "OWNER":  "**مالكٌ مقروءٌ من القاعدة** يُقارَن بصاحب الجلسة",
    "ANY":    "لا يقيّده نطاق — والصلاحيةُ الإدارية هي الحاسمة، وفوقها حارسُ التسلسل",
}

# أحداثُ التدقيق **لكلِّ عمليةٍ بعينها** لا لكلِّ مورِد. والدقّةُ هنا
# مقصودة: قولُ «المشاريعُ تُسجَّل» يوهم أن سردَها يُسجَّل، وهو لا يُسجَّل
# ولا ينبغي. وما لا حدثَ له يُكتب «—» صراحةً — فلا يُدَّعى تسجيلٌ لا يقع.
AUDIT_OF = {
    ("registration", "create"): ["account.created"],
    ("session", "create"):      ["login.success", "login.failure"],
    ("session", "delete"):      ["logout"],
    ("credential", "update"):   ["password.reset"],
    ("account", "update"):      ["account.updated", "password.changed"],
    ("account", "delete"):      ["account.deleted"],
    ("subscription", "update"): ["subscription.canceled", "subscription.store_event"],
    ("subscription", "grant"):  ["subscription.granted"],
    ("project", "create"):      ["project.created"],
    ("project", "delete"):      ["project.deleted"],
    ("project", "render"):      ["export.created", "export.completed", "export.failed"],
    ("user", "update"):         ["user.suspended", "user.reactivated"],
    ("user_role", "update"):    ["role.changed"],
    ("audit", "list"):          ["audit.read"],
}

# وكلُّ منعٍ يُسجَّل `security.denied` أيًّا كان المورِد — يُقال مرّةً في
# رأس الجدول لا في ثمانيةٍ وثلاثين سطرًا.

def rate_of():
    """حدُّ المعدّل لكل زوج — قبليٌّ من الجدول، أو داخل المعالِج."""
    out = {}
    for rs in RT.TABLE.values():
        for r in rs:
            k = (r.resource, r.action)
            if r.rate: out[k] = f"`{r.rate[0]}` (قبليّ · لكل {'عنوان' if r.rate[1]=='ip' else 'مستخدم'})"
            elif r.quota in ("cards", "videos"): out.setdefault(k, "`export`/`video` (داخل المعالِج — يُعدّ العملَ المقبول)")
    return out

def routes_of():
    out = {}
    for rs in RT.TABLE.values():
        for r in rs:
            out.setdefault((r.resource, r.action), []).append(
                f"{r.method} {r.path}" + ("{id}" if r.kind == "param" else ""))
    return out

def rows():
    rate, routes = rate_of(), routes_of()
    out = []
    for (t, a), scope in sorted(AZ.POLICY.items()):
        perm = AZ._p(t, a)
        holders = [r for r in ("anonymous", "user", "moderator", "admin", "super_admin")
                   if perm in AZ.perms_of(r)]
        # الدورُ الأدنى الذي يملكها يكفي — والباقي يرثه بالضمّ
        least = holders[0] if holders else "—"
        ev = [e for e in AUDIT_OF.get((t, a), []) if e in AUD.ACTIONS]
        out.append({
            "perm": perm, "resource": t, "action": a,
            "scope": SCOPE_NAME.get(scope, "?"),
            "roles": holders, "least": least,
            "audit": ev, "rate": rate.get((t, a), "—"),
            "routes": routes.get((t, a), []),
        })
    return out

def table():
    rs = rows()
    L = ["# كتالوجُ الصلاحيات",
         "",
         "> مولَّدٌ من الشيفرة بـ`python3 perms_report.py`. **لا يُحرَّر باليد.**",
         "",
         f"**{len(AZ.PERMISSIONS)} صلاحيةً ⟷ {len(AZ.POLICY)} زوجًا (مورِد، فعل)** — "
         "تقابلٌ تامٌّ في الاتجاهين. واسمُ الصلاحية هو الزوجُ نفسُه، فلا يمكن أن "
         "توجد عمليةٌ بلا صلاحية.",
         "",
         "## النطاقات",
         "",
         "| النطاق | ما يعنيه |",
         "|---|---|"]
    for k, v in SCOPE_WHAT.items(): L.append(f"| `{k}` | {v} |")
    L += ["",
          "## الجدول",
          "",
          "«أدنى دورٍ يملكها» يكفي: التسلسلُ محسوبٌ بالضمّ "
          "(`anonymous ⊂ user ⊂ moderator ⊂ admin ⊂ super_admin`)، فما يملكه "
          "الأدنى يملكه من فوقه.",
          "",
          "**وكلُّ منعٍ يُسجَّل `security.denied`** أيًّا كان المورِد — فلا يُعاد "
          "في كل سطر. وعمودُ «تُسجَّل؟» يذكر أحداثَ **النجاح** لهذه العملية بعينها.",
          "",
          "| الصلاحية | المورِد | الفعل | النطاق | أدنى دورٍ يملكها | تُسجَّل؟ | حدُّ معدّل | المسار |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rs:
        ev = "✔ " + " · ".join(f"`{e}`" for e in r["audit"]) if r["audit"] else "—"
        rt = " · ".join(f"`{x}`" for x in r["routes"]) or "— (قاعدةٌ عامّة)"
        L.append(f"| `{r['perm']}` | {r['resource']} | {r['action']} | `{r['scope']}` "
                 f"| `{r['least']}` | {ev} | {r['rate']} | {rt} |")
    L += ["", "## الأدوار", "",
          "| الدور | عددُ الصلاحيات | ما يزيده على ما قبله |", "|---|---:|---|"]
    prev = frozenset()
    for name in ("anonymous",) + tuple(AZ.ASSIGNABLE):
        p = AZ.perms_of(name)
        add = " · ".join(f"`{x}`" for x in sorted(p - prev)) or "—"
        L.append(f"| `{name}` | {len(p)} | {add} |")
        prev = p
    L += ["", "## ما يفحصه هذا الجدولُ آليًّا", "",
          "- **لا صلاحيةَ ميتة**: كلُّ صلاحيةٍ لها زوجٌ في `POLICY` ومسارٌ أو "
          "قاعدةٌ عامّة.",
          "- **لا عمليةَ بلا صلاحية**: كلُّ زوجٍ في `POLICY` له صلاحيةٌ باسمه.",
          "- **لا صلاحيةَ لا يبلغها دور**: كلُّ صلاحيةٍ في حزمةِ دورٍ واحدٍ على الأقلّ.",
          "",
          "وهذه الثلاثةُ ثوابتُ بوّابةٍ في `invariants.py` "
          "(`NEW_OPERATION_WITHOUT_PERMISSION`) — لا مراجعةٌ بشرية.", ""]
    return "\n".join(L)

def audit_gaps():
    """أعمالٌ حسّاسةٌ بلا تسجيل، وصلاحياتٌ ميتة. تُقال ولا تُخفى."""
    rs = rows()
    SENSITIVE = {("user_role", "update"), ("user", "update"), ("account", "delete"),
                 ("subscription", "grant"), ("session", "create"), ("audit", "list")}
    unaudited = sorted(r["perm"] for r in rs
                       if (r["resource"], r["action"]) in SENSITIVE and not r["audit"])
    dead = sorted(r["perm"] for r in rs if not r["routes"]
                  and r["perm"] not in ("unknown.read", "content.read",
                                        "content.list", "service.read"))
    unreachable = sorted(AZ.PERMISSIONS - set().union(*AZ.ROLES.values()))
    return unaudited, dead, unreachable

if __name__ == "__main__":
    md = table()
    unaudited, dead, unreachable = audit_gaps()
    if "--check" in sys.argv:
        bad = False
        for name, items in (("عملٌ حسّاسٌ بلا تسجيل", unaudited),
                            ("صلاحيةٌ ميتةٌ لا مسارَ لها", dead),
                            ("صلاحيةٌ لا يبلغها دور", unreachable)):
            if items: bad = True; print(f"  ✗ {name}: {items}")
        cur = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if cur.strip() != md.strip():
            bad = True; print("  ✗ docs/PERMISSIONS.md متقادم — شغّل python3 perms_report.py")
        print("QUALITY_GATE = " + ("FAIL" if bad else "PASS"))
        sys.exit(1 if bad else 0)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(md + "\n")
    print(f"كُتب docs/PERMISSIONS.md — {len(AZ.PERMISSIONS)} صلاحية")
    for name, items in (("عملٌ حسّاسٌ بلا تسجيل", unaudited),
                        ("صلاحيةٌ ميتة", dead), ("لا يبلغها دور", unreachable)):
        if items: print(f"  ! {name}: {items}")
