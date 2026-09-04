"""إدارةُ الأدوار من سطر الأوامر — بديلُ المفتاح المشترك.

    python3 -m falah.roles list
    python3 -m falah.roles show <البريد>
    python3 -m falah.roles grant <البريد> super_admin --reason "..."
    python3 -m falah.roles revoke <البريد> --reason "..."      → يعيده إلى user

**ولماذا سطرُ أوامرٍ لا مسارُ شبكة؟** لأن أوّلَ `super_admin` لا يمكن أن
يُصنع بصلاحيةٍ لا يملكها أحدٌ بعد. والبديلُ الشائع — مفتاحٌ في ترويسة —
هو ما نُزع في P1.2 أصلًا: من يملكه يملك كلَّ شيءٍ ولا يُعرف مَن استعمله.

ومن يملك تشغيلَ هذا الأمر يملك القرصَ وقاعدةَ البيانات أصلًا، فليس هذا
توسيعًا لسطح الهجوم. **والفرقُ أن الفعل يترك أثرًا باسمه**: كلُّ منحةٍ
تُكتب في `audit_logs` بفاعلٍ `system:cli` وسببٍ مكتوب.

ولا يعمل هذا عبر HTTP بحال — لا مسارَ ينادي شيئًا منه.
"""
import argparse, sys

from . import audit as AUD, authz as AZ, store

def _find(c, email):
    r = c.execute("SELECT id,email,role,status FROM users WHERE email=?",
                  ((email or "").strip().lower(),)).fetchone()
    if not r: raise SystemExit(f"⛔ لا حساب بهذا البريد: {email}")
    return r

def cmd_list(c, a):
    rows = c.execute("""SELECT role, COUNT(*) n FROM users
                        GROUP BY role ORDER BY n DESC""").fetchall()
    print("الأدوار في القاعدة:")
    for r in rows: print(f"  {r['role']:14} {r['n']}")
    print("\nوما يملكه كلٌّ منها:")
    for name in AZ.ASSIGNABLE:
        print(f"  {name:14} {len(AZ.perms_of(name))} صلاحية")

def cmd_show(c, a):
    u = _find(c, a.email)
    print(f"  #{u['id']}  {u['email']}")
    print(f"  الدور: {u['role']}   الحالة: {u['status']}")
    for p in sorted(AZ.perms_of(u["role"])): print(f"    · {p}")

def _set_role(c, a, new_role):
    u = _find(c, a.email)
    if new_role not in AZ.ASSIGNABLE:
        raise SystemExit(f"⛔ دورٌ غير معروف: {new_role} — المتاح: "
                         + " · ".join(AZ.ASSIGNABLE))
    if u["role"] == new_role:
        print(f"  · {u['email']} دورُه {new_role} أصلًا — لا تغيير"); return
    c.execute("UPDATE users SET role=?, role_changed_at=? WHERE id=?",
              (new_role, store.now(), u["id"]))
    # الجلساتُ القائمة تحمل دورًا صار قديمًا — تُنهى كلُّها، وإلا بقي مَن
    # خُفِّض دورُه يعمل بصلاحياتٍ نُزعت منه حتى تنتهي كعكتُه.
    c.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
    AUD.record(c, "role.changed", actor_id=None, actor_role="system:cli",
               resource_type="user", resource_id=u["id"],
               metadata={"from": u["role"], "to": new_role,
                         "reason": a.reason, "via": "cli"}, commit=False)
    c.commit()
    print(f"  ✓ {u['email']}: {u['role']} → {new_role}  (وأُنهيت جلساتُه)")

def cmd_grant(c, a):  _set_role(c, a, a.role)
def cmd_revoke(c, a): _set_role(c, a, AZ.DEFAULT_ROLE)

def main(argv=None):
    ap = argparse.ArgumentParser(prog="falah.roles", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("show"); p.add_argument("email")
    p = sub.add_parser("grant")
    p.add_argument("email"); p.add_argument("role", choices=list(AZ.ASSIGNABLE))
    p.add_argument("--reason", default=None)
    p = sub.add_parser("revoke")
    p.add_argument("email"); p.add_argument("--reason", default=None)
    a = ap.parse_args(argv)
    if not hasattr(a, "reason"): a.reason = None
    c = store.init()
    try:
        {"list": cmd_list, "show": cmd_show,
         "grant": cmd_grant, "revoke": cmd_revoke}[a.cmd](c, a)
    finally:
        c.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
