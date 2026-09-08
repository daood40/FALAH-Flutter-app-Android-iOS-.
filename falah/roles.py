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
تُكتب في `audit_logs` بفاعلٍ `system:cli`، ومعها مستخدمُ النظام والمضيف
وسببٌ مكتوب.

ولا يعمل هذا عبر HTTP بحال — لا مسارَ ينادي شيئًا منه، ويفحص ذلك
`invariants.py`.

## حرّاسُه

| الحارس | لماذا |
|---|---|
| **لا سرَّ في وسائطه** | لا كلمةَ مرورٍ ولا رمز. الوسائطُ تظهر في `ps` وفي تاريخ الصدفة، فما يُمرَّر فيها يُعدّ مكشوفًا |
| **ولا سرَّ في طبعه** | يطبع البريدَ والدورَ والحالة، ولا يقترب من اشتقاقٍ ولا ملحٍ ولا رمزِ جلسة |
| **حالةُ الهجرات** | يرفض العملَ وهجرةٌ **آمنة** معلّقة — فلا يُكتب في مخطَّطٍ ناقص. والهادمةُ المؤجَّلة عمدًا (٠٠٣) لا تمنعه |
| **حسابٌ واحدٌ لا غير** | بريدٌ لا حسابَ له يُرفض، والتباسٌ في الاختيار يُرفض |
| **دورٌ معلَنٌ فقط** | ما ليس في `ASSIGNABLE` يُرفض قبل أن يمسّ القاعدة |
| **لا يتكرّر أثرُه** | منحُ الدور نفسِه مرّتين لا يغيّر شيئًا ولا يكتب سطرًا ثانيًا |
| **آمنٌ تحت التزامن** | `BEGIN IMMEDIATE` يقفل الكتابة، فالقراءةُ والتغييرُ والتسجيل صفقةٌ واحدة |
"""
import argparse, getpass, platform, sqlite3, sys

from . import audit as AUD, authz as AZ, store

class RolesError(Exception):
    """خطأٌ يُعرض للمشغّل ويُخرج برمزٍ غير صفر."""

def _guard_migrations(c):
    """لا يُكتب في مخطَّطٍ ناقص.

    الهجراتُ الآمنة تجري في `store.init()`، فبقاءُ واحدةٍ منها معلّقةً يعني
    عطبًا لا تأجيلًا. أمّا الهادمةُ الموقوفة بقرار (٠٠٣) فلا تمنع شيئًا —
    وإلا صار الحارسُ الأمنيّ سببًا في تعطيل الإدارة.
    """
    from . import migrate as MG
    pending = [(v, n) for v, n, destructive, _ in MG.pending(c) if not destructive]
    if pending:
        raise RolesError("هجراتٌ آمنةٌ معلّقة: "
                         + " · ".join(f"{v:03d} {n}" for v, n in pending)
                         + "\n   شغّل: python3 -m falah.migrate")
    if "role" not in {r[1] for r in c.execute("PRAGMA table_info(users)")}:
        raise RolesError("عمودُ الدور غير موجود — الهجرة ٠٠٥ لم تُطبَّق")

def _find(c, email):
    """حسابٌ واحدٌ بالضبط، أو رفض.

    `email` فريدٌ في المخطَّط، فالالتباسُ غيرُ متوقَّع — ويُفحص مع ذلك.
    الحارسُ الذي لا يُختبر إلا حين يُنتهك ليس حارسًا.
    """
    e = (email or "").strip().lower()
    if not e:
        raise RolesError("بريدٌ فارغ")
    rows = c.execute("SELECT id,email,role,status FROM users WHERE lower(email)=?",
                     (e,)).fetchall()
    if not rows:
        raise RolesError(f"لا حساب بهذا البريد: {e}")
    if len(rows) > 1:
        raise RolesError(f"التباسٌ في الاختيار: {len(rows)} حساباتٍ بالبريد {e}. "
                         "لا يُغيَّر دورٌ على شكّ.")
    return rows[0]

def _who():
    """مَن شغّل الأمر — لا سرَّ فيه، وبه يُعرف الفاعلُ في السجلّ."""
    try:    user = getpass.getuser()
    except Exception: user = "?"
    return {"os_user": user, "host": platform.node()[:60], "via": "cli"}

# ───────────────────────── الأوامر ─────────────────────────

def cmd_list(c, a):
    rows = c.execute("""SELECT role, COUNT(*) n FROM users
                        GROUP BY role ORDER BY n DESC""").fetchall()
    print("الأدوار في القاعدة:")
    for r in rows: print(f"  {r['role']:14} {r['n']}")
    unknown = [r["role"] for r in rows if r["role"] not in AZ.ASSIGNABLE]
    if unknown:
        print(f"  ⚠ أدوارٌ لا تعرفها الشيفرة: {unknown} — أصحابُها بلا صلاحية")
    print("\nوما يملكه كلٌّ منها:")
    for name in AZ.ASSIGNABLE:
        print(f"  {name:14} {len(AZ.perms_of(name))} صلاحية")
    return 0

def cmd_show(c, a):
    u = _find(c, a.email)
    print(f"  #{u['id']}  {u['email']}")
    print(f"  الدور: {u['role']}   الحالة: {u['status']}")
    for p in sorted(AZ.perms_of(u["role"])): print(f"    · {p}")
    return 0

def _set_role(c, email, new_role, reason):
    """صفقةٌ واحدة: يقرأ ويغيّر ويسجّل ويُنهي الجلسات — أو لا شيء.

    `BEGIN IMMEDIATE` يأخذ قفلَ الكتابة قبل القراءة، فتشغيلان متزامنان
    لا يتداخلان: الثاني ينتظر ثم يرى ما كتبه الأوّل، فيصير بلا أثرٍ إن
    كان يطلب الدورَ نفسَه.
    """
    if new_role not in AZ.ASSIGNABLE:
        raise RolesError(f"دورٌ غير معروف: {new_role!r} — المتاح: "
                         + " · ".join(AZ.ASSIGNABLE))
    c.execute("BEGIN IMMEDIATE")
    try:
        u = _find(c, email)
        if u["role"] == new_role:
            c.execute("COMMIT")
            print(f"  · {u['email']} دورُه {new_role} أصلًا — لا تغيير")
            return 0
        c.execute("UPDATE users SET role=?, role_changed_at=? WHERE id=?",
                  (new_role, store.now(), u["id"]))
        # الجلساتُ القائمة تحمل دورًا صار قديمًا — تُنهى كلُّها، وإلا بقي مَن
        # خُفِّض دورُه يعمل بصلاحياتٍ نُزعت منه حتى تنتهي كعكتُه.
        c.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
        AUD.record(c, "role.changed", actor_id=None, actor_role="system:cli",
                   resource_type="user", resource_id=u["id"],
                   metadata={"from": u["role"], "to": new_role,
                             "reason": reason, **_who()}, commit=False)
        c.execute("COMMIT")
    except Exception:
        try: c.execute("ROLLBACK")
        except sqlite3.Error: pass
        raise
    print(f"  ✓ {u['email']}: {u['role']} → {new_role}  (وأُنهيت جلساتُه)")
    return 0

def cmd_grant(c, a):  return _set_role(c, a.email, a.role, a.reason)
def cmd_revoke(c, a): return _set_role(c, a.email, AZ.DEFAULT_ROLE, a.reason)

CMDS = {"list": cmd_list, "show": cmd_show, "grant": cmd_grant, "revoke": cmd_revoke}

def build_parser():
    ap = argparse.ArgumentParser(prog="falah.roles",
                                 description="إدارةُ الأدوار محلّيًّا. "
                                             "لا يقبل كلمةَ مرورٍ ولا رمزًا في وسائطه.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="الأدوار في القاعدة وصلاحياتُ كلٍّ منها")
    p = sub.add_parser("show", help="دورُ حسابٍ وصلاحياتُه"); p.add_argument("email")
    p = sub.add_parser("grant", help="يمنح دورًا")
    p.add_argument("email"); p.add_argument("role", choices=list(AZ.ASSIGNABLE))
    p.add_argument("--reason", default=None, help="سببٌ يُكتب في سجلّ التدقيق")
    p = sub.add_parser("revoke", help=f"يعيده إلى {AZ.DEFAULT_ROLE}")
    p.add_argument("email"); p.add_argument("--reason", default=None)
    return ap

def main(argv=None):
    a = build_parser().parse_args(argv)
    if not hasattr(a, "reason"): a.reason = None
    if not hasattr(a, "email"):  a.email = None
    c = store.init()
    try:
        if a.cmd in ("grant", "revoke"): _guard_migrations(c)
        return CMDS[a.cmd](c, a)
    except (RolesError, AZ.Denied) as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 2
    finally:
        c.close()

if __name__ == "__main__":
    sys.exit(main())
