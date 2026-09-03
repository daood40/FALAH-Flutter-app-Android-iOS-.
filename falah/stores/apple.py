"""App Store — التحقّق من المعاملات وإدارة التطبيق.

خادمان مختلفان لا يُخلط بينهما:
  • **App Store Server API** (api.storekit.itunes.apple.com) — يسأل عن معاملةٍ
    واشتراك، ويُجيب بحمولةٍ موقَّعة. هذا ما يُبنى عليه حقُّ المشترك.
  • **App Store Connect API** (api.appstoreconnect.apple.com) — يُنشئ سجلّ
    التطبيق ويضبط بياناته ومنتجات الاشتراك.

**القاعدة: لا يُصدَّق ردٌّ لم يُتحقَّق من توقيعه.** حمولات آبل مُوقَّعة JWS
وسلسلة شهاداتها تنتهي إلى جذر آبل. فإن لم يُعطَ الجذر، تُرفَض ولا تُقبل
«على حسن الظنّ». وتعطيل التحقّق ممكنٌ بنيّةٍ صريحة وحده، ويُطبع تحذيرًا.

المفاتيح تُقرأ من البيئة ولا تُكتب في المستودع أبدًا:
  FALAH_APPLE_KEY_P8      مسار ملف المفتاح ‎.p8 (أو محتواه)
  FALAH_APPLE_KEY_ID      معرّف المفتاح
  FALAH_APPLE_ISSUER_ID   معرّف المُصدِر
  FALAH_APPLE_BUNDLE_ID   معرّف الحزمة (للـ Server API)
  FALAH_APPLE_ROOT_CA     مسار شهادة AppleRootCA-G3.cer
  FALAH_APPLE_ENV         production | sandbox   (الافتراضي sandbox)
"""
import base64, json, os, time, urllib.error, urllib.request

SERVER_PROD = "https://api.storekit.itunes.apple.com"
SERVER_SBOX = "https://api.storekit-sandbox.itunes.apple.com"
CONNECT     = "https://api.appstoreconnect.apple.com"

class AppleError(Exception): pass

# ───────────────────────── المفاتيح ─────────────────────────

def _cfg(name, required=True):
    v = os.environ.get(name, "").strip()
    if required and not v:
        raise AppleError(f"المتغيّر {name} غير مضبوط — راجع launch/CREDENTIALS.md")
    return v

def _private_key():
    raw = _cfg("FALAH_APPLE_KEY_P8")
    if raw.startswith("-----BEGIN"):
        pem = raw.encode()
    else:
        if not os.path.isfile(raw):
            raise AppleError("ملف المفتاح ‎.p8 غير موجود: " + raw)
        pem = open(raw, "rb").read()
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    return load_pem_private_key(pem, password=None)

def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def _b64u_dec(s):
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())

def token(audience="appstoreconnect-v1", with_bundle=True, ttl=1200):
    """رمز ES256 موقَّع بمفتاح آبل. مدّته قصيرة عمدًا — آبل ترفض ما زاد عن ٢٠ دقيقة."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    key = _private_key()
    now = int(time.time())
    head = {"alg": "ES256", "kid": _cfg("FALAH_APPLE_KEY_ID"), "typ": "JWT"}
    body = {"iss": _cfg("FALAH_APPLE_ISSUER_ID"), "iat": now, "exp": now + ttl,
            "aud": audience}
    if with_bundle:
        body["bid"] = _cfg("FALAH_APPLE_BUNDLE_ID")
    signing = f"{_b64u(json.dumps(head, separators=(',',':')).encode())}." \
              f"{_b64u(json.dumps(body, separators=(',',':')).encode())}"
    der = key.sign(signing.encode(), ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")     # JWS يريد R‖S لا DER
    return f"{signing}.{_b64u(raw)}"

# ───────────────────────── التحقّق من حمولةٍ موقَّعة ─────────────────────────

def verify_jws(signed, root_ca=None, now=None):
    """يفكّ حمولة JWS بعد التحقّق من توقيعها وسلسلة شهاداتها.

    الخطوات: قراءة سلسلة x5c من الترويسة، ثم التحقّق أن كل شهادةٍ موقَّعة
    من التي فوقها، وأن الجذر هو جذر آبل الذي أعطيتَه، وأن الشهادات صالحةٌ
    زمنًا، ثم التحقّق من توقيع الحمولة بمفتاح الشهادة الأولى.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    import datetime

    # المدخل يأتي من جهازٍ لا يُوثق به: كل تشويهٍ يُردّ خطأً معروفًا لا انهيارًا
    parts = (signed or "").split(".")
    if len(parts) != 3: raise AppleError("حمولة JWS مشوّهة")
    try:
        head = json.loads(_b64u_dec(parts[0]))
        chain = [x509.load_der_x509_certificate(base64.b64decode(c))
                 for c in (head.get("x5c") or [])]
    except AppleError:
        raise
    except Exception as e:
        raise AppleError("ترويسة أو شهادةٌ غير صالحة: " + type(e).__name__)
    if not chain: raise AppleError("لا سلسلة شهادات في الحمولة")

    root_ca = root_ca or os.environ.get("FALAH_APPLE_ROOT_CA", "").strip()
    if not root_ca:
        raise AppleError(
            "جذر آبل غير مضبوط (FALAH_APPLE_ROOT_CA). لا تُقبل حمولةٌ بلا "
            "تحقّقٍ من سلسلتها — نزّل AppleRootCA-G3.cer من "
            "https://www.apple.com/certificateauthority/")
    blob = open(root_ca, "rb").read()
    root = (x509.load_pem_x509_certificate(blob) if blob.lstrip()[:1] == b"-"
            else x509.load_der_x509_certificate(blob))

    t = datetime.datetime.fromtimestamp(now or time.time(), datetime.timezone.utc)
    for cert in chain:
        nb = cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else \
             cert.not_valid_before.replace(tzinfo=datetime.timezone.utc)
        na = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else \
             cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
        if not (nb <= t <= na):
            raise AppleError("شهادةٌ في السلسلة منتهية أو لم تبدأ")

    full = chain + ([root] if chain[-1].fingerprint(hashes.SHA256())
                    != root.fingerprint(hashes.SHA256()) else [])
    if full[-1].fingerprint(hashes.SHA256()) != root.fingerprint(hashes.SHA256()):
        raise AppleError("سلسلة الشهادات لا تنتهي إلى جذر آبل الذي أعطيتَه")
    for child, parent in zip(full, full[1:]):
        try:
            _verify_cert(child, parent)
        except AppleError:
            raise
        except Exception:
            # حلقةٌ في السلسلة لم يوقّعها من فوقها — تُردّ ولا تُقبل
            raise AppleError("سلسلة الشهادات غير متّصلة إلى الجذر المعطى")

    pub = chain[0].public_key()
    try:
        raw = _b64u_dec(parts[2])
        if len(raw) != 64: raise AppleError("طول التوقيع غير صحيح")
        r = int.from_bytes(raw[:32], "big"); s = int.from_bytes(raw[32:], "big")
        pub.verify(utils.encode_dss_signature(r, s),
                   f"{parts[0]}.{parts[1]}".encode(), ec.ECDSA(hashes.SHA256()))
        return json.loads(_b64u_dec(parts[1]))
    except AppleError:
        raise
    except Exception as e:
        raise AppleError("التوقيع لا يطابق الحمولة: " + type(e).__name__)

def _verify_cert(child, parent):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
    pub = parent.public_key()
    if isinstance(pub, ec.EllipticCurvePublicKey):
        pub.verify(child.signature, child.tbs_certificate_bytes,
                   ec.ECDSA(child.signature_hash_algorithm))
    elif isinstance(pub, rsa.RSAPublicKey):
        pub.verify(child.signature, child.tbs_certificate_bytes,
                   padding.PKCS1v15(), child.signature_hash_algorithm)
    else:
        raise AppleError("نوع مفتاحٍ غير مدعوم في السلسلة")

# ───────────────────────── نداءات الخادم ─────────────────────────

def _call(base, path, aud="appstoreconnect-v1", with_bundle=True, method="GET", body=None):
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer " + token(aud, with_bundle),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        raise AppleError(f"آبل ردّت {e.code}: {detail}")

def _server_base():
    return SERVER_PROD if os.environ.get("FALAH_APPLE_ENV") == "production" else SERVER_SBOX

def transaction(transaction_id, verify=True):
    """معلومات معاملةٍ بعينها — الأساس الذي يُبنى عليه منح الاشتراك."""
    d = _call(_server_base(), f"/inApps/v1/transactions/{transaction_id}")
    signed = d.get("signedTransactionInfo")
    if not signed: raise AppleError("لا حمولة موقَّعة في الردّ")
    return verify_jws(signed) if verify else json.loads(_b64u_dec(signed.split(".")[1]))

def subscription_statuses(original_transaction_id, verify=True):
    """حالة كل اشتراكات هذا المشتري — النافذ منها والمنتهي."""
    d = _call(_server_base(), f"/inApps/v1/subscriptions/{original_transaction_id}")
    out = []
    for group in d.get("data", []):
        for item in group.get("lastTransactions", []):
            tx = item.get("signedTransactionInfo")
            rn = item.get("signedRenewalInfo")
            out.append({
                "status": item.get("status"),          # 1 نافذ · 2 منتهٍ · 3 تجديد متعثّر …
                "original_transaction_id": item.get("originalTransactionId"),
                "transaction": verify_jws(tx) if (tx and verify) else
                               (json.loads(_b64u_dec(tx.split(".")[1])) if tx else None),
                "renewal": verify_jws(rn) if (rn and verify) else
                           (json.loads(_b64u_dec(rn.split(".")[1])) if rn else None),
            })
    return out

def decode_notification(signed_payload, verify=True):
    """إشعار آبل الخادميّ (v2) — يصل إلى خطّاف الخادم عند كل تغيير."""
    payload = verify_jws(signed_payload) if verify else \
              json.loads(_b64u_dec(signed_payload.split(".")[1]))
    data = payload.get("data") or {}
    for k, dst in (("signedTransactionInfo", "transaction"),
                   ("signedRenewalInfo", "renewal")):
        if data.get(k):
            data[dst] = verify_jws(data[k]) if verify else \
                        json.loads(_b64u_dec(data[k].split(".")[1]))
    return {"type": payload.get("notificationType"),
            "subtype": payload.get("subtype"),
            "uuid": payload.get("notificationUUID"), "data": data}

# ــ App Store Connect: سجلّ التطبيق ومنتجاته ــ

def apps():
    d = _call(CONNECT, "/v1/apps?limit=50", with_bundle=False)
    return [{"id": a["id"], "name": a["attributes"].get("name"),
             "bundle_id": a["attributes"].get("bundleId"),
             "sku": a["attributes"].get("sku")} for a in d.get("data", [])]

def subscription_groups(app_id):
    d = _call(CONNECT, f"/v1/apps/{app_id}/subscriptionGroups?limit=50", with_bundle=False)
    return [{"id": g["id"], "reference": g["attributes"].get("referenceName")}
            for g in d.get("data", [])]

def subscriptions_in(group_id):
    d = _call(CONNECT, f"/v1/subscriptionGroups/{group_id}/subscriptions?limit=50",
              with_bundle=False)
    return [{"id": s["id"], "product_id": s["attributes"].get("productId"),
             "name": s["attributes"].get("name"),
             "period": s["attributes"].get("subscriptionPeriod"),
             "state": s["attributes"].get("state")} for s in d.get("data", [])]

def create_subscription_group(app_id, reference_name):
    return _call(CONNECT, "/v1/subscriptionGroups", with_bundle=False, method="POST",
                 body={"data": {"type": "subscriptionGroups",
                                "attributes": {"referenceName": reference_name},
                                "relationships": {"app": {"data": {"type": "apps",
                                                                   "id": app_id}}}}})

def create_subscription(group_id, product_id, name, period, review_note=None):
    """ينشئ منتج اشتراك. السعر يُضبط بعده بمسارٍ آخر، والمراجعة يدويّة."""
    attrs = {"name": name, "productId": product_id,
             "subscriptionPeriod": period,            # ONE_MONTH | ONE_YEAR …
             "familySharable": False}
    if review_note: attrs["reviewNote"] = review_note
    return _call(CONNECT, "/v1/subscriptions", with_bundle=False, method="POST",
                 body={"data": {"type": "subscriptions", "attributes": attrs,
                                "relationships": {"subscriptionGroup":
                                    {"data": {"type": "subscriptionGroups",
                                              "id": group_id}}}}})

def whoami():
    """أصغر نداءٍ يُثبت أن المفاتيح تعمل — يُستعمل قبل أي شيء آخر."""
    d = _call(CONNECT, "/v1/apps?limit=1", with_bundle=False)
    return {"ok": True, "apps_visible": len(d.get("data", [])),
            "env": os.environ.get("FALAH_APPLE_ENV", "sandbox")}
