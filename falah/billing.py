"""الاشتراك والحصص — من يملك ماذا، وكم بقي له هذا الشهر.

القاعدة الحاكمة: **الاشتراك يحدّ الكمّ لا الصحّة.** لا خطّةَ تُخفي مصدرًا،
ولا خطّةَ تحذف اسم المفسّر أو المترجم أو من حكم بالحديث، ولا خطّةَ تُرخي
فحصًا من الفحوص الخمسة والعشرين. المدفوع يشتري عددًا أكبر ومقاسًا أوسع،
ولا يشتري نصًّا أضعف. وعلامة فلاح وحدها هي ما يُرفع بالاشتراك — أما نسبة
النصّ إلى مصدره فثابتةٌ في كل خطّة، مجانيّها ومدفوعها.

المزوّد لا يُثق به على عِلّاته: كل إيصالٍ يُسجَّل كما ورد في `receipts`،
والحقّ يُشتقّ من حالة الاشتراك عندنا لا من كلمة العميل.
"""
import hashlib, json, os, secrets, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from falah import store

DAY   = 86400
MONTH = 30 * DAY

class BillingError(Exception): pass

# ───────────────────────── الخطط ─────────────────────────
# الأسعار أرقامٌ مبدئية تُضبط قبل النشر، والحصص محسوبةٌ على كلفة التصيير
# الحقيقية: البطاقة ثانيةٌ من المعالج تقريبًا، والمقطع نصف دقيقة.

PLANS = {
    "free": {
        "name": "مجّاني",
        "tagline": "لتجرّبه وتنشر منه",
        "price": {"month": 0, "year": 0},
        "limits": {"cards": 15, "videos": 0, "projects": 2},
        "features": {
            "ratios": ["square"],
            "designs": ["parch"],
            "tints": ["auto"],
            "falah_mark": True,          # علامة فلاح تبقى
            "series_max": 3,
            "bulk": False,
            "api": False,
        },
    },
    "creator": {
        "name": "مُنشئ",
        "tagline": "لمن ينشر كل يوم",
        "price": {"month": 19, "year": 190},
        "limits": {"cards": 400, "videos": 40, "projects": 50},
        "features": {
            "ratios": ["square", "portrait", "vertical", "wide"],
            "designs": ["parch", "night", "ivory"],
            "tints": ["auto", "sand", "green", "navy", "coal", "gold"],
            "falah_mark": False,         # لك أن ترفعها
            "series_max": 20,
            "bulk": True,
            "api": False,
        },
    },
    "studio": {
        "name": "دار",
        "tagline": "للقنوات والفرق",
        "price": {"month": 59, "year": 590},
        "limits": {"cards": 3000, "videos": 300, "projects": 500},
        "features": {
            "ratios": ["square", "portrait", "vertical", "wide"],
            "designs": ["parch", "night", "ivory"],
            "tints": ["auto", "sand", "green", "navy", "coal", "gold"],
            "falah_mark": False,
            "series_max": 100,
            "bulk": True,
            "api": True,
        },
    },
}
ORDER = ["free", "creator", "studio"]
CURRENCY = os.environ.get("FALAH_CURRENCY", "USD")

# ما لا يُباع ولا يُمنع: يُعرض في صفحة الخطط حتى لا يظنّ أحدٌ أنه ميزةٌ مدفوعة
ALWAYS = [
    "الفحوص الخمسة والعشرون على كل نصّ — في كل خطّة",
    "اسم المصدر والدرجة ومن حكم بها — لا تُحذف بالاشتراك",
    "التفسير والترجمة منسوبان إلى ناشرهما دائمًا",
    "ما لم يجتز الفحص يُحجب ويُذكر سببه — ولا يُفتح بالدفع",
]

def plan_of(name):
    return PLANS.get(name) or PLANS["free"]

def period_key(t=None):
    return time.strftime("%Y-%m", time.gmtime(t or time.time()))

# ───────────────────────── حالة الاشتراك ─────────────────────────

def current(c, user_id):
    """الاشتراك النافذ الآن. المنتهي يُطوى تلقائيًّا ويعود صاحبه إلى المجاني."""
    t = store.now()
    r = c.execute("""SELECT * FROM subscriptions WHERE user_id=?
                     AND status IN ('active','grace')
                     ORDER BY (expires_at IS NULL) DESC, expires_at DESC LIMIT 1""",
                  (user_id,)).fetchone()
    if not r:
        return {"plan": "free", "status": "active", "provider": "free",
                "expires_at": None, "renews": 0}
    if r["expires_at"] and r["expires_at"] < t:
        # مهلةُ ثلاثة أيام بعد الانتهاء: التجديد قد يتأخّر عند المتجر ولا
        # يصحّ أن يُقطع عن مشترٍ دفع فعلًا.
        if r["renews"] and r["expires_at"] + 3 * DAY > t and r["status"] == "active":
            c.execute("UPDATE subscriptions SET status='grace' WHERE id=?", (r["id"],))
            c.commit()
            return dict(r, status="grace")
        c.execute("UPDATE subscriptions SET status='expired' WHERE id=?", (r["id"],))
        c.commit()
        store.log(c, user_id, "sub_expired", f"{r['plan']}:{r['provider']}")
        return {"plan": "free", "status": "active", "provider": "free",
                "expires_at": None, "renews": 0}
    return dict(r)

def entitlements(c, user_id):
    """ما يملكه المستخدم الآن: خطّته وحدودها وما استهلكه منها."""
    sub = current(c, user_id)
    p = plan_of(sub["plan"])
    per = period_key()
    used = {m: 0 for m in p["limits"]}
    for r in c.execute("SELECT metric, used FROM usage WHERE user_id=? AND period=?",
                       (user_id, per)):
        used[r["metric"]] = r["used"]
    projects = c.execute("SELECT COUNT(*) FROM projects WHERE user_id=?", (user_id,)).fetchone()[0]
    used["projects"] = projects
    return {
        "plan": sub["plan"], "plan_name": p["name"], "status": sub["status"],
        "provider": sub["provider"], "expires_at": sub.get("expires_at"),
        "renews": bool(sub.get("renews")),
        "limits": p["limits"], "used": used,
        "left": {k: max(0, p["limits"][k] - used.get(k, 0)) for k in p["limits"]},
        "features": p["features"], "period": per,
    }

# ───────────────────────── الحصص ─────────────────────────

def check(c, user_id, metric, n=1):
    """يرفع BillingError إن تجاوز الطلبُ الحصّة — ولا يستهلك شيئًا."""
    e = entitlements(c, user_id)
    lim = e["limits"].get(metric)
    if lim is None: return e
    if e["used"].get(metric, 0) + n > lim:
        names = {"cards": "بطاقة", "videos": "مقطعًا", "projects": "مشروعًا"}
        raise BillingError(
            f"بلغتَ حدّ خطّة «{e['plan_name']}»: {lim} {names.get(metric, metric)} في الشهر. "
            f"يتجدّد أول الشهر القادم، أو ارفع خطّتك.")
    return e

def consume(c, user_id, metric, n=1):
    """يُسجَّل بعد نجاح العمل لا قبله — فلا يُحاسَب أحدٌ على عملٍ لم يتمّ."""
    per = period_key()
    c.execute("""INSERT INTO usage(user_id,period,metric,used) VALUES(?,?,?,?)
                 ON CONFLICT(user_id,period,metric) DO UPDATE SET used=used+?""",
              (user_id, per, metric, n, n))
    c.commit()

def release(c, user_id, metric, n=1):
    """يردّ حصّةً حُجزت لعملٍ لم يتمّ. تُستعمل حين يُحجز قبل التصيير حتى لا
    يُغرِق أحدٌ الطابورَ بما يتجاوز خطّته — فإن فشل العمل رُدَّت الحصّة كاملةً.
    لا ينزل العدّاد تحت الصفر."""
    per = period_key()
    c.execute("""UPDATE usage SET used = MAX(0, used - ?)
                 WHERE user_id=? AND period=? AND metric=?""",
              (n, user_id, per, metric))
    c.commit()

def allows(c, user_id, feature, value=None):
    """هل تسمح الخطّة بهذه الميزة؟ وللقوائم: هل تسمح بهذه القيمة منها؟"""
    f = entitlements(c, user_id)["features"]
    v = f.get(feature)
    if isinstance(v, list): return value is None or value in v
    return bool(v) if value is None else v == value

def require(c, user_id, feature, value=None, what=""):
    if not allows(c, user_id, feature, value):
        e = entitlements(c, user_id)
        raise BillingError(f"{what or 'هذه الميزة'} غير متاح في خطّة «{e['plan_name']}».")

# ───────────────────────── منح الاشتراك وإنهاؤه ─────────────────────────

def grant(c, user_id, plan, days=None, provider="grant", provider_id=None,
          period=None, renews=0, note=None):
    """يمنح خطّةً. إن كان له اشتراكٌ نافذ من النوع نفسه مُدّ، وإلا فُتح جديد."""
    if plan not in PLANS: raise BillingError("خطّة غير معروفة")
    t = store.now()
    if plan == "free":
        c.execute("UPDATE subscriptions SET status='canceled', canceled_at=? "
                  "WHERE user_id=? AND status IN ('active','grace')", (t, user_id))
        c.commit(); return current(c, user_id)
    span = (days * DAY) if days else (MONTH if period == "month" else
                                      365 * DAY if period == "year" else 30 * DAY)
    cur = c.execute("""SELECT * FROM subscriptions WHERE user_id=? AND plan=?
                       AND status IN ('active','grace') ORDER BY expires_at DESC LIMIT 1""",
                    (user_id, plan)).fetchone()
    if cur:
        base = max(cur["expires_at"] or t, t)
        c.execute("UPDATE subscriptions SET expires_at=?, status='active', renews=? WHERE id=?",
                  (base + span, renews, cur["id"]))
    else:
        # ترقّيةٌ من خطّةٍ أدنى: تُلغى الأدنى ولا تُترك عالقة
        c.execute("UPDATE subscriptions SET status='canceled', canceled_at=? "
                  "WHERE user_id=? AND status IN ('active','grace')", (t, user_id))
        c.execute("""INSERT INTO subscriptions(user_id,plan,status,provider,provider_id,
                       period,started_at,expires_at,renews,note,created_at)
                     VALUES(?,?,'active',?,?,?,?,?,?,?,?)""",
                  (user_id, plan, provider, provider_id, period, t, t + span, renews, note, t))
    c.commit()
    store.log(c, user_id, "sub_grant", f"{plan}:{provider}:{days or period}")
    return current(c, user_id)

def cancel(c, user_id, reason="user"):
    """إيقاف التجديد — والحقّ يبقى إلى نهاية المدّة المدفوعة."""
    t = store.now()
    n = c.execute("UPDATE subscriptions SET renews=0, canceled_at=?, note=? "
                  "WHERE user_id=? AND status IN ('active','grace')",
                  (t, reason, user_id)).rowcount
    c.commit()
    if n: store.log(c, user_id, "sub_cancel", reason)
    return current(c, user_id)

def refund(c, user_id, provider_id=None, reason="refund"):
    """الاسترداد يقطع الحقّ فورًا — لا مهلة، لأن المال رُدّ."""
    t = store.now()
    q = "UPDATE subscriptions SET status='refunded', canceled_at=?, note=? WHERE user_id=?"
    a = [t, reason, user_id]
    if provider_id: q += " AND provider_id=?"; a.append(provider_id)
    else:           q += " AND status IN ('active','grace')"
    c.execute(q, a); c.commit()
    store.log(c, user_id, "sub_refund", reason)
    return current(c, user_id)

# ───────────────────────── إيصالات المتاجر ─────────────────────────

APPLE_PRODUCTS = {"com.falah.creator.month":  ("creator", "month"),
                  "com.falah.creator.year":   ("creator", "year"),
                  "com.falah.studio.month":   ("studio",  "month"),
                  "com.falah.studio.year":    ("studio",  "year")}
GOOGLE_PRODUCTS = dict(APPLE_PRODUCTS)

def record_receipt(c, user_id, provider, provider_id, kind, payload=None):
    c.execute("""INSERT INTO receipts(user_id,provider,provider_id,kind,payload,at)
                 VALUES(?,?,?,?,?,?)""",
              (user_id, provider, provider_id, kind,
               json.dumps(payload, ensure_ascii=False) if payload else None, store.now()))
    c.commit()

def apply_store_event(c, user_id, provider, event, verified=False):
    """يطبّق حدثًا من المتجر. `verified=True` تعني أن المستدعي تحقّق بنفسه.

    وإلا فالتحقّق يقع هنا: يُسأل المتجرُ عن المعاملة، ويُشتقّ الحقّ من
    ردّه لا من الحمولة القادمة من الجهاز. فلو زوّر أحدٌ رسالة شراءٍ لم
    يُمنح شيئًا، لأن المتجر يُسأل بالرمز ويردّ بالحقيقة.
    """
    if provider not in ("apple", "google"):
        raise BillingError("مزوّد غير معروف")
    pid  = event.get("transaction_id") or event.get("purchase_token")
    prod = event.get("product_id")
    kind = event.get("type")
    record_receipt(c, user_id, provider, pid, kind or "unknown", event)

    if not verified:
        kind, prod, pid = _verify_with_store(provider, event)

    table = APPLE_PRODUCTS if provider == "apple" else GOOGLE_PRODUCTS
    if kind in ("purchase", "renew"):
        if prod not in table: raise BillingError("منتَج غير معروف: " + str(prod))
        plan, period = table[prod]
        return grant(c, user_id, plan, provider=provider, provider_id=pid,
                     period=period, renews=1, note=kind)
    if kind == "cancel":  return cancel(c, user_id, provider)
    if kind == "refund":  return refund(c, user_id, pid, provider)
    if kind == "expire":
        c.execute("UPDATE subscriptions SET status='expired' WHERE user_id=? AND provider=?",
                  (user_id, provider)); c.commit()
        return current(c, user_id)
    raise BillingError("حدث غير معروف: " + str(kind))

def _verify_with_store(provider, event):
    """يسأل المتجر عن الشراء ويعيد (النوع، المنتج، المعرّف) من ردّه هو.

    ينهض بالمفاتيح إن ضُبطت، ويرفض صراحةً إن لم تُضبط — ولا يقبل شيئًا
    «مؤقّتًا»، لأن قبول ما لم يُتحقَّق منه يعني اشتراكاتٍ مجّانيةً لمن
    عرف شكل الطلب.
    """
    if provider == "apple":
        from falah.stores import apple as AP
        tid = event.get("transaction_id")
        if not tid: raise BillingError("لا معرّف معاملة")
        try:    info = AP.transaction(tid)
        except AP.AppleError as e: raise BillingError("تعذّر التحقّق من آبل: " + str(e))
        expires = int(info.get("expiresDate") or 0) / 1000
        kind = "purchase" if expires > time.time() else "expire"
        if info.get("revocationDate"): kind = "refund"
        return kind, info.get("productId"), info.get("originalTransactionId") or tid
    from falah.stores import google as GP
    tok = event.get("purchase_token")
    if not tok: raise BillingError("لا رمز شراء")
    try:    info = GP.subscription(tok)
    except GP.GoogleError as e: raise BillingError("تعذّر التحقّق من جوجل: " + str(e))
    state = info.get("state") or ""
    kind = ("purchase" if info.get("active") else
            "refund" if "REVOKED" in state else
            "cancel" if "CANCELED" in state else "expire")
    return kind, info.get("product_id"), info.get("order_id") or tok

# ───────────────────────── العرض ─────────────────────────

def catalogue():
    """ما يُعرض في صفحة الخطط — ومعه ما لا يُباع أصلًا."""
    return {"currency": CURRENCY,
            "plans": [{"id": k, **{x: PLANS[k][x] for x in
                                   ("name", "tagline", "price", "limits", "features")}}
                      for k in ORDER],
            "always": ALWAYS,
            "note": "الاشتراك يحدّ الكمّ لا الصحّة: لا خطّة تُخفي مصدرًا ولا تُرخي فحصًا."}
