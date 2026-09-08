"""Google Play — التحقّق من الاشتراكات وإدارة الإصدارات.

المفتاح حساب خدمة (Service Account) بصلاحيةٍ واحدة:
`https://www.googleapis.com/auth/androidpublisher`. ويُمنح في Play Console
دورًا محدودًا لا دور المالك — راجع launch/CREDENTIALS.md.

**القاعدة نفسها: الحقّ يُشتقّ من ردّ جوجل لا من كلمة العميل.** الجهاز
يرسل رمز الشراء، والخادم يسأل جوجل عنه، فإن قالت «نافذ» مُنح الحقّ وإلا
فلا. ولا يُقبل رمزٌ لم يُسأل عنه.

  FALAH_GOOGLE_SA_JSON    مسار ملف حساب الخدمة (أو محتواه)
  FALAH_ANDROID_PACKAGE   اسم الحزمة، مثل com.falah.app
"""
import base64, json, os, time, urllib.error, urllib.parse, urllib.request

API   = "https://androidpublisher.googleapis.com/androidpublisher/v3"
TOKEN = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/androidpublisher"

class GoogleError(Exception): pass

_cache = {"token": None, "exp": 0}

def _cfg(name, required=True):
    v = os.environ.get(name, "").strip()
    if required and not v:
        raise GoogleError(f"المتغيّر {name} غير مضبوط — راجع launch/CREDENTIALS.md")
    return v

def _sa():
    raw = _cfg("FALAH_GOOGLE_SA_JSON")
    if raw.lstrip().startswith("{"):
        return json.loads(raw)
    if not os.path.isfile(raw):
        raise GoogleError("ملف حساب الخدمة غير موجود: " + raw)
    return json.load(open(raw, encoding="utf-8"))

def _b64u(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def access_token():
    """رمز وصولٍ قصير الأجل. يُخزَّن في الذاكرة ولا يُكتب على القرص."""
    if _cache["token"] and _cache["exp"] > time.time() + 60:
        return _cache["token"]
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    sa = _sa()
    now = int(time.time())
    head = {"alg": "RS256", "typ": "JWT", "kid": sa.get("private_key_id")}
    body = {"iss": sa["client_email"], "scope": SCOPE, "aud": TOKEN,
            "iat": now, "exp": now + 3600}
    signing = f"{_b64u(json.dumps(head, separators=(',',':')).encode())}." \
              f"{_b64u(json.dumps(body, separators=(',',':')).encode())}"
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    sig = key.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
    assertion = f"{signing}.{_b64u(sig)}"
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(TOKEN, data=data), timeout=30) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise GoogleError(f"جوجل رفضت المفتاح {e.code}: {e.read().decode()[:200]}")
    _cache.update(token=d["access_token"], exp=now + int(d.get("expires_in", 3600)))
    return _cache["token"]

def _call(path, method="GET", body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer " + access_token(),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise GoogleError(f"جوجل ردّت {e.code}: {e.read().decode()[:300]}")

def _pkg(): return _cfg("FALAH_ANDROID_PACKAGE")

# ───────────────────────── الاشتراك ─────────────────────────

ACTIVE_STATES = {"SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"}

def subscription(purchase_token):
    """حالة اشتراكٍ من رمز الشراء — هذا هو مصدر الحقّ لا رسالة الجهاز."""
    p = urllib.parse.quote(purchase_token, safe="")
    d = _call(f"/applications/{_pkg()}/purchases/subscriptionsv2/tokens/{p}")
    items = d.get("lineItems") or []
    first = items[0] if items else {}
    return {
        "state": d.get("subscriptionState"),
        "active": d.get("subscriptionState") in ACTIVE_STATES,
        "product_id": first.get("productId"),
        "offer": (first.get("offerDetails") or {}).get("basePlanId"),
        "expiry": first.get("expiryTime"),
        "auto_renew": bool((first.get("autoRenewingPlan") or {}).get("autoRenewEnabled")),
        "order_id": d.get("latestOrderId"),
        "acknowledged": d.get("acknowledgementState"),
        "test": bool(d.get("testPurchase")),
        "raw": d,
    }

def acknowledge(purchase_token, product_id):
    """جوجل تُلغي شراءً لم يُقرّ به خلال ثلاثة أيام — فالإقرار ليس ترفًا."""
    p = urllib.parse.quote(purchase_token, safe="")
    return _call(f"/applications/{_pkg()}/purchases/subscriptions/"
                 f"{urllib.parse.quote(product_id, safe='')}/tokens/{p}:acknowledge",
                 method="POST", body={})

def decode_rtdn(message):
    """إشعار جوجل الفوريّ يصل عبر Pub/Sub مرمَّزًا بـbase64 في message.data."""
    raw = message.get("message", {}).get("data") or message.get("data")
    if not raw: raise GoogleError("لا حمولة في الإشعار")
    d = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)).decode())
    sub = d.get("subscriptionNotification") or {}
    return {"package": d.get("packageName"), "at": d.get("eventTimeMillis"),
            "type": sub.get("notificationType"),      # 4 شراء · 2 تجديد · 3 إلغاء · 12 سحب …
            "purchase_token": sub.get("purchaseToken"),
            "product_id": sub.get("subscriptionId"), "raw": d}

# ───────────────────────── التطبيق والإصدار ─────────────────────────

def whoami():
    """أصغر نداءٍ يُثبت أن المفتاح يعمل وأن الحزمة مرئيّة له."""
    e = _call(f"/applications/{_pkg()}/edits", method="POST", body={})
    _call(f"/applications/{_pkg()}/edits/{e['id']}", method="DELETE")
    return {"ok": True, "package": _pkg(), "edit_probe": e.get("id")}

def base_plans(product_id):
    d = _call(f"/applications/{_pkg()}/subscriptions/"
              f"{urllib.parse.quote(product_id, safe='')}")
    return [{"id": b.get("basePlanId"), "state": b.get("state"),
             "period": (b.get("autoRenewingBasePlanType") or {}).get("billingPeriodDuration")}
            for b in (d.get("basePlans") or [])]

def list_subscriptions():
    d = _call(f"/applications/{_pkg()}/subscriptions?pageSize=50")
    return [{"product_id": s.get("productId"),
             "listings": [l.get("title") for l in (s.get("listings") or [])],
             "base_plans": [b.get("basePlanId") for b in (s.get("basePlans") or [])]}
            for s in (d.get("subscriptions") or [])]

def upload_aab(path, track="internal", notes_ar=None):
    """يرفع حزمة AAB ويضعها في مسارٍ مغلق. النشر العامّ يبقى قرارًا بشريًّا."""
    if not os.path.isfile(path): raise GoogleError("ملف AAB غير موجود: " + path)
    edit = _call(f"/applications/{_pkg()}/edits", method="POST", body={})
    eid = edit["id"]
    up = (f"https://androidpublisher.googleapis.com/upload/androidpublisher/v3"
          f"/applications/{_pkg()}/edits/{eid}/bundles?uploadType=media")
    req = urllib.request.Request(up, method="POST", data=open(path, "rb").read(),
                                 headers={"Authorization": "Bearer " + access_token(),
                                          "Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            bundle = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise GoogleError(f"فشل الرفع {e.code}: {e.read().decode()[:200]}")
    rel = {"releases": [{"versionCodes": [str(bundle["versionCode"])],
                         "status": "draft" if track == "production" else "completed"}]}
    if notes_ar:
        rel["releases"][0]["releaseNotes"] = [{"language": "ar", "text": notes_ar}]
    _call(f"/applications/{_pkg()}/edits/{eid}/tracks/{track}", method="PUT", body=rel)
    _call(f"/applications/{_pkg()}/edits/{eid}:commit", method="POST")
    return {"version_code": bundle["versionCode"], "track": track,
            "note": "في مسارٍ مغلق — النشر العامّ يبقى بيدك"}
