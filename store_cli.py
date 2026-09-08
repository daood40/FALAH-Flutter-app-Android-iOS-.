#!/usr/bin/env python3
"""أداة المتاجر — كل ما يُدار بمفتاحٍ بدل لوحة التحكّم.

    python3 store_cli.py check                     # هل المفاتيح تعمل؟
    python3 store_cli.py apple apps
    python3 store_cli.py apple groups <app_id>
    python3 store_cli.py apple setup <app_id>      # ينشئ مجموعة الاشتراك ومنتجاتها
    python3 store_cli.py apple tx <transaction_id>
    python3 store_cli.py google subs
    python3 store_cli.py google check <purchase_token>
    python3 store_cli.py google upload <file.aab> [--track internal]

**لا يُكتب مفتاحٌ في هذا الملف ولا في المستودع.** تُقرأ كلها من البيئة،
فمن شغّل الأداة على جهازه بقي مفتاحه عنده. راجع launch/CREDENTIALS.md.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def out(x): print(json.dumps(x, ensure_ascii=False, indent=1))

def need(msg):
    print("✗ " + msg, file=sys.stderr); sys.exit(2)

def cmd_check():
    """أصغر نداءٍ لكل متجر — يُشغَّل أولًا قبل أي شيء."""
    ok = True
    print("▸ آبل")
    try:
        from falah.stores import apple as AP
        out(AP.whoami())
    except Exception as e:
        ok = False; print("  ✗ " + str(e))
    print("▸ جوجل")
    try:
        from falah.stores import google as GP
        out(GP.whoami())
    except Exception as e:
        ok = False; print("  ✗ " + str(e))
    print("\n" + ("كل المفاتيح تعمل ✓" if ok else "بعض المفاتيح ناقصة — راجع launch/CREDENTIALS.md"))
    sys.exit(0 if ok else 1)

def cmd_apple(args):
    from falah.stores import apple as AP
    if not args: need("apps | groups <app_id> | subs <group_id> | setup <app_id> | tx <id>")
    a = args[0]
    if a == "apps":    return out(AP.apps())
    if a == "groups":  return out(AP.subscription_groups(args[1]))
    if a == "subs":    return out(AP.subscriptions_in(args[1]))
    if a == "tx":      return out(AP.transaction(args[1]))
    if a == "status":  return out(AP.subscription_statuses(args[1]))
    if a == "setup":
        from falah import billing as B
        app_id = args[1]
        g = AP.create_subscription_group(app_id, "FALAH")
        gid = g["data"]["id"]
        made = []
        for pid, (plan, period) in B.APPLE_PRODUCTS.items():
            made.append(AP.create_subscription(
                gid, pid, f"{B.PLANS[plan]['name']} — "
                          f"{'شهري' if period == 'month' else 'سنوي'}",
                "ONE_MONTH" if period == "month" else "ONE_YEAR",
                review_note="اشتراكٌ يرفع حصّة البطاقات والمقاطع. "
                            "لا يُخفي مصدرًا ولا يُرخي فحصًا."))
        return out({"group": gid, "created": len(made),
                    "next": "اضبط الأسعار والوصف في App Store Connect — السعر لا يُضبط بالمفتاح"})
    need("أمر آبل غير معروف: " + a)

def cmd_google(args):
    from falah.stores import google as GP
    if not args: need("subs | plans <product_id> | check <token> | upload <file.aab>")
    a = args[0]
    if a == "subs":   return out(GP.list_subscriptions())
    if a == "plans":  return out(GP.base_plans(args[1]))
    if a == "check":  return out(GP.subscription(args[1]))
    if a == "upload":
        track = "internal"
        if "--track" in args: track = args[args.index("--track") + 1]
        return out(GP.upload_aab(args[1], track))
    need("أمر جوجل غير معروف: " + a)

if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(0)
    c = sys.argv[1]
    if c == "check":     cmd_check()
    elif c == "apple":   cmd_apple(sys.argv[2:])
    elif c == "google":  cmd_google(sys.argv[2:])
    else:                need("أمر غير معروف: " + c)
