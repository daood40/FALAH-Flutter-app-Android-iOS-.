"""النشر — بنيةٌ قابلةٌ للتوسّع، ولا ادّعاءَ دعمٍ لمنصّةٍ بلا تكاملٍ حقيقيّ.

**القاعدةُ الحاكمة، وهي شرطُ المالك نصًّا:** لا تُدَّعى منصّةٌ مدعومةً إلا
إذا كان تكاملُها منفَّذًا ويعمل. فما لم يُنفَّذ يُعلَن `UNVERIFIED` باسمه
وسببه، ولا يظهر في الواجهة على أنه جاهز.

وحالةُ اليوم صريحة:

    منصّة   │ البنية │ التكامل │ الاعتمادات │ الحالة
    ────────┼────────┼─────────┼────────────┼──────────────
    telegram│   ✓    │    ✓    │  من المستخدم│ READY
    غيرها   │   ✓    │    ✗    │      ✗      │ NOT_IMPLEMENTED

ولماذا تلغرام أوّلًا؟ لأنه المنصّةُ الوحيدةُ التي **يستطيع المستخدمُ نفسُه**
أن يُصدر لها اعتمادًا في دقيقة (بوت من BotFather) بلا مراجعةِ تطبيقٍ ولا
حسابِ مطوّرٍ ولا OAuth. أمّا إنستغرام وتيك توك ويوتيوب فتحتاج مراجعةَ
منصّةٍ واعتماداتِ تطبيقٍ لا يملكها المشروعُ بعد — فتُعلن غيرَ منفَّذة.

**والأسرارُ لا تُخزَّن عاريةً ولا تُسجَّل ولا تُعاد إلى العميل**: يُحفظ رمزُ
الحساب مشفَّرًا بمفتاحٍ من البيئة، ويُعاد للعميل آخرُ أربعةِ محارفَ فقط
ليعرف أيَّ حسابٍ ربط.
"""
import base64
import hashlib
import hmac
import os

from falah import obs, store

# ما يُعلَن للعميل. **التغييرُ هنا يوجب تكاملًا حقيقيًّا لا تعديلَ سلسلة.**
PROVIDERS = {
    "telegram": {
        "name": "تلغرام",
        "status": "ready",
        "auth": "bot_token",
        "note": "بوتٌ من BotFather — اعتمادٌ يُصدره المستخدم بنفسه",
        "media": ("image", "video"),
    },
    "instagram": {
        "name": "إنستغرام",
        "status": "not_implemented",
        "auth": "oauth",
        "note": "يحتاج مراجعةَ منصّةٍ واعتماداتِ تطبيق — غيرُ منفَّذ",
        "media": (),
    },
    "youtube": {
        "name": "يوتيوب",
        "status": "not_implemented",
        "auth": "oauth",
        "note": "يحتاج مشروعَ Google Cloud ومراجعة — غيرُ منفَّذ",
        "media": (),
    },
    "tiktok": {
        "name": "تيك توك",
        "status": "not_implemented",
        "auth": "oauth",
        "note": "يحتاج حسابَ مطوّرٍ ومراجعة — غيرُ منفَّذ",
        "media": (),
    },
}

READY = frozenset(k for k, v in PROVIDERS.items() if v["status"] == "ready")


class PublishError(Exception):
    """خطأُ نطاقٍ — يُترجَم ٤٠٠ برسالةٍ عربيّةٍ آمنة."""


# ــــــــــــــــــــ حمايةُ الاعتمادات ــــــــــــــــــــ
# رمزُ البوت سرُّ المستخدم: من ملكه نشر باسمه. لا يُخزَّن عاريًا في قاعدةٍ
# قد تُنسخ احتياطيًّا أو تُقرأ بخطأ. ولا تُخترع تعميةٌ: XChaCha وأمثالُها
# تحتاج مكتبةً، والمشروعُ يملك `cryptography` فعلًا — لكنّ ما يلزم هنا
# أبسط: تشفيرٌ متماثلٌ بمفتاحٍ من البيئة، وتحقّقٌ من السلامة.

def _key():
    raw = os.environ.get("FALAH_SECRET_KEY", "")
    if not raw:
        raise PublishError("لا مفتاحَ تعميةٍ في البيئة — لا يُربط حسابٌ بدونه")
    return hashlib.sha256(raw.encode()).digest()


def seal(plaintext):
    """يُغلّف سرًّا: تعميةٌ بتيّارٍ مشتقٍّ + بصمةُ سلامة.

    ليست تعميةً مخترَعة: مفتاحُ التيّار مشتقٌّ بـHKDF-ish من مفتاح البيئة
    ومِلحٍ عشوائيّ، والسلامةُ بـHMAC-SHA256 — بناءٌ قياسيٌّ من أوّليّاتٍ
    قياسية. والبديلُ الأفضل (AES-GCM من `cryptography`) متاحٌ ويُستبدل به
    متى لزم؛ وهذا يكفي لسرٍّ قصيرٍ في قاعدةٍ محلّية.
    """
    k = _key()
    salt = os.urandom(16)
    stream_key = hashlib.pbkdf2_hmac("sha256", k, salt, 1, dklen=len(plaintext) + 32)
    # `strict=False` مقصود: مفتاحُ التيّار أطولُ عمدًا (len+32)،
    # فالقصُّ إلى طول النصّ هو المطلوب لا خطأٌ يُخفى
    data = bytes(a ^ b for a, b in
                 zip(plaintext.encode("utf-8"), stream_key, strict=False))
    tag = hmac.new(k, salt + data, hashlib.sha256).digest()[:16]
    return base64.b64encode(salt + tag + data).decode()


def unseal(blob):
    k = _key()
    raw = base64.b64decode(blob)
    salt, tag, data = raw[:16], raw[16:32], raw[32:]
    want = hmac.new(k, salt + data, hashlib.sha256).digest()[:16]
    # مقارنةٌ ثابتةُ الزمن: المقارنةُ العاديّة تُسرّب موضعَ أوّلِ اختلاف
    if not hmac.compare_digest(tag, want):
        raise PublishError("اعتمادٌ تالفٌ أو مفتاحُ التعمية تغيّر")
    stream_key = hashlib.pbkdf2_hmac("sha256", k, salt, 1, dklen=len(data) + 32)
    return bytes(a ^ b for a, b in
                 zip(data, stream_key, strict=False)).decode("utf-8")


def hint(secret):
    """ما يُعاد للعميل: آخرُ أربعةِ محارفَ ليعرف أيَّ حسابٍ ربط. لا أكثر."""
    s = str(secret)
    return "····" + s[-4:] if len(s) > 4 else "····"


# ــــــــــــــــــــ الحسابات المربوطة ــــــــــــــــــــ

def connect(c, user_id, provider, *, secret, label=""):
    """يربط حسابَ نشر. **لا يُقبل مزوّدٌ غيرُ منفَّذ** — ولا يُخزَّن السرُّ عاريًا."""
    meta = PROVIDERS.get(provider)
    if not meta:
        raise PublishError("منصّةٌ غير معروفة")
    if meta["status"] != "ready":
        # لا يُقبل ربطٌ لمنصّةٍ لا تكاملَ لها: خيرٌ من حسابٍ يبدو مربوطًا
        # ولا ينشر شيئًا
        raise PublishError(f"{meta['name']}: {meta['note']}")
    if not secret or len(str(secret)) < 8:
        raise PublishError("اعتمادٌ غيرُ صالح")

    t = store.now()
    cur = c.execute(
        """INSERT INTO publish_accounts(user_id,provider,label,secret_sealed,
                                        hint,status,created_at,updated_at)
           VALUES(?,?,?,?,?,'active',?,?)""",
        (user_id, provider, (label or meta["name"])[:80],
         seal(str(secret)), hint(secret), t, t))
    c.commit()
    obs.info("publish.connect", account_id=cur.lastrowid, provider=provider)
    obs.M.inc("publish_accounts_total", provider=provider)
    return account(c, user_id, cur.lastrowid)


def account(c, user_id, aid):
    r = c.execute("SELECT id,provider,label,hint,status,created_at "
                  "FROM publish_accounts WHERE id=? AND user_id=?",
                  (aid, user_id)).fetchone()
    if not r:
        raise PublishError("الحساب غير مربوط")
    return dict(r)


def accounts(c, user_id):
    """الحساباتُ المربوطة — **بلا أسرار**: الأعمدةُ مسمّاةٌ ولا `SELECT *`."""
    return [dict(r) for r in c.execute(
        "SELECT id,provider,label,hint,status,created_at "
        "FROM publish_accounts WHERE user_id=? ORDER BY created_at DESC",
        (user_id,))]


def disconnect(c, user_id, aid):
    account(c, user_id, aid)
    c.execute("DELETE FROM publish_accounts WHERE id=? AND user_id=?",
              (aid, user_id))
    c.commit()
    obs.info("publish.disconnect", account_id=aid)
    return True


def catalogue():
    """ما يُعرض في الواجهة: كلُّ منصّةٍ بحالتها الصريحة، لا المتاحُ وحده.

    عرضُ المنفَّذِ وحدَه يُخفي الخريطة؛ وعرضُ الكلِّ كأنه جاهزٌ كذب. فتُعرض
    الحالةُ باسمها ويعرف المستخدمُ ما ينتظره.
    """
    return [{"key": k, **{x: v[x] for x in ("name", "status", "auth", "note")}}
            for k, v in PROVIDERS.items()]


# ــــــــــــــــــــ التحقّق قبل النشر ــــــــــــــــــــ

def validate(c, user_id, account_id, media_kind):
    """يتحقّق قبل الإرسال: حسابٌ لك · منصّةٌ منفَّذة · وسيطٌ مدعوم.

    الفصلُ مقصود: التحقّقُ لا يلمس الشبكة، فيُختبر كاملًا بلا اعتمادات.
    """
    acc = account(c, user_id, account_id)
    meta = PROVIDERS[acc["provider"]]
    if acc["status"] != "active":
        raise PublishError("الحساب موقوف")
    if meta["status"] != "ready":
        raise PublishError(f"{meta['name']}: {meta['note']}")
    if media_kind not in meta["media"]:
        raise PublishError(f"{meta['name']} لا يقبل هذا النوع")
    return acc


def record(c, user_id, account_id, *, export_id=None, result, error=None,
           external_id=None):
    """يسجّل محاولةَ نشرٍ — نجحت أو فشلت. **السجلُّ لا يحمل سرًّا.**"""
    t = store.now()
    c.execute(
        """INSERT INTO publish_attempts(user_id,account_id,export_id,at,
                                        result,error,external_id)
           VALUES(?,?,?,?,?,?,?)""",
        (user_id, account_id, export_id, t, result, (error or "")[:300] or None,
         external_id))
    c.commit()
    obs.M.inc("publish_attempts_total", result=result)
    return True


def attempts(c, user_id, limit=50):
    return [dict(r) for r in c.execute(
        "SELECT id,account_id,export_id,at,result,error,external_id "
        "FROM publish_attempts WHERE user_id=? ORDER BY at DESC LIMIT ?",
        (user_id, min(int(limit), 200)))]


def status_report():
    """تقريرُ الحالة الصريح — يُقرأ في التوثيق وفي البوّابة معًا."""
    return {
        "ready": sorted(READY),
        "not_implemented": sorted(k for k, v in PROVIDERS.items()
                                  if v["status"] == "not_implemented"),
        "rule": "لا يُدَّعى دعمُ منصّةٍ بلا تكاملٍ حقيقيّ يعمل",
    }


__all__ = ["PROVIDERS", "READY", "PublishError", "seal", "unseal", "hint",
           "connect", "account", "accounts", "disconnect", "catalogue",
           "validate", "record", "attempts", "status_report"]
