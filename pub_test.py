#!/usr/bin/env python3
"""النشر — لا ادّعاءَ دعم، ولا سرَّ عارٍ، ولا حسابَ غيرِك.

    python3 pub_test.py

القاعدةُ الأولى التي يحرسها هذا الملفّ هي شرطُ المالك نصًّا:
**لا يُدَّعى دعمُ منصّةٍ إلا إذا كان تكاملُها منفَّذًا ويعمل.**

فاختبارٌ هنا يمنع أن يصير «مدعومًا» بتغيير سلسلةٍ في القاموس: من أراد
منصّةً جديدةً فليكتب تكاملَها، ويحدّث هذا الاختبارَ بالاسم.
"""
import hashlib
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_TMP = tempfile.mkdtemp(prefix="falah_pub_")
os.environ["FALAH_APP_DB"] = os.path.join(_TMP, "app.db")
os.environ.setdefault("FALAH_SECRET_KEY", "test-key-for-sealing-only-not-a-secret")

from falah import migrate, publishing as PUB, store  # noqa: E402

# قاعدةٌ تمرّ بالهجرات — لا مخطَّطٌ مكتوبٌ بيدٍ في الاختبار. وجداولُ النشر
# تأتي من الهجرة ٠٠٧، فلا وجودَ لها بلا تشغيلها.
_boot = store.connect()
migrate.run(_boot, quiet=True)
_boot.close()

# رموزٌ مزيَّفةٌ **مشتقّةٌ لا مكتوبة**: الفاحصُ الأمنيّ و`ruff` يمسكان السرَّ
# الحرفيَّ ولو كان اختباريًّا — وهما محقّان، فلا يُستثنى ملفٌّ ولا يُخفَّف
# فاحص. تُشتقّ فتبقى ثابتةً بين التشغيلات.
def _bot(tag):
    """يحاكي شكلَ رمزِ بوت تلغرام: أرقامٌ ثم نقطتان ثم سلسلة."""
    h = hashlib.sha256(f"falah-pub-{tag}".encode()).hexdigest()
    return f"{int(h[:9], 16)}:AA{h[9:41]}"

TOKEN_A = _bot("a")
TOKEN_B = _bot("b")
SHORT = "ab"

OK = FAIL = 0
FAILURES: list = []


def check(name, cond, detail=""):
    global OK, FAIL
    if cond:
        OK += 1; print(f"  ✓ {name}")
    else:
        FAIL += 1; FAILURES.append((name, detail))
        print(f"  ✗ {name}" + (f"  ← {detail}" if detail else ""))


def head(t): print(f"\n▸ {t}")


def _raises(fn):
    try:
        fn(); return False
    except PUB.PublishError:
        return True


def mkuser(c, n=1):
    t = store.now()
    cur = c.execute(
        "INSERT INTO users(email,name,watermark,pw_hash,pw_salt,pw_iter,"
        "status,created_at) VALUES(?,?,?,?,?,?,'active',?)",
        (f"p{n}-{t}-{os.getpid()}@t.local", f"p{n}", "", b"x", b"y", 1, t))
    c.commit()
    return cur.lastrowid


# ═══════════ ١ · لا ادّعاءَ دعم ═══════════

def honesty():
    head("لا يُدَّعى دعمُ منصّةٍ بلا تكاملٍ حقيقيّ")

    # **الثابتُ المسمّى**: المنفَّذُ اليومَ هو تلغرام وحده. من أضاف غيره
    # فليكتب تكاملَه ويحدّث هذا السطرَ بالاسم — فيظهر التغييرُ في الفرق.
    check("المنفَّذُ اليومَ: تلغرام وحده", PUB.READY == {"telegram"},
          str(sorted(PUB.READY)))

    for k in ("instagram", "youtube", "tiktok"):
        check(f"«{k}» معلنٌ غيرَ منفَّذ",
              PUB.PROVIDERS[k]["status"] == "not_implemented")
        check(f"ولـ«{k}» سببٌ مكتوب", len(PUB.PROVIDERS[k]["note"]) > 20)

    cat = PUB.catalogue()
    check("والكتالوجُ يعرض الكلَّ بحالته لا المتاحَ وحده",
          len(cat) == len(PUB.PROVIDERS) and
          all("status" in x for x in cat), str(len(cat)))

    rep = PUB.status_report()
    check("والتقريرُ يفصل المنفَّذَ عن غيره",
          rep["ready"] == ["telegram"] and len(rep["not_implemented"]) == 3,
          str(rep))

    # منصّةٌ غيرُ منفَّذةٍ لا تُربط: حسابٌ يبدو مربوطًا ولا ينشر أسوأُ من رفضٍ
    c = store.connect()
    u = mkuser(c, 1)
    for k in ("instagram", "youtube", "tiktok"):
        check(f"ولا يُربط حسابُ «{k}»",
              _raises(lambda k=k: PUB.connect(c, u, k, secret=TOKEN_A)))
    check("ومنصّةٌ مجهولةٌ تُرفض",
          _raises(lambda: PUB.connect(c, u, "myspace", secret=TOKEN_A)))
    c.close()


# ═══════════ ٢ · السرُّ لا يُخزَّن عاريًا ═══════════

def secrets():
    head("الاعتمادُ مُغلَّفٌ ولا يُعاد ولا يُسجَّل")
    c = store.connect()
    u = mkuser(c, 2)
    token = TOKEN_A

    acc = PUB.connect(c, u, "telegram", secret=token, label="قناتي")
    check("الربطُ ينجح للمنفَّذ", acc["provider"] == "telegram")

    # **لا يُعاد السرُّ إلى العميل** — تلميحٌ فقط
    check("ولا يُعاد السرُّ", token not in str(acc), str(acc))
    check("ويُعاد تلميحٌ من أربعة", acc["hint"].endswith(token[-4:]))
    check("والتلميحُ لا يكفي لانتحال", len(acc["hint"].strip("·")) <= 4)

    # ولا يُخزَّن عاريًا في القاعدة
    raw = c.execute("SELECT secret_sealed FROM publish_accounts WHERE id=?",
                    (acc["id"],)).fetchone()[0]
    check("ولا يُخزَّن عاريًا في القاعدة", token not in raw, raw[:24])
    check("والمُغلَّفُ يُفكّ صحيحًا", PUB.unseal(raw) == token)

    # عبثٌ بالمُغلَّف يُكشف — لا يُفكّ إلى قمامةٍ صامتة
    import base64
    b = bytearray(base64.b64decode(raw))
    b[-1] ^= 0xFF
    check("والعبثُ يُكشف لا يُفكّ صامتًا",
          _raises(lambda: PUB.unseal(base64.b64encode(bytes(b)).decode())))

    # والسردُ لا يحمل سرًّا بحال
    lst = PUB.accounts(c, u)
    check("وسردُ الحسابات بلا أسرار",
          all("secret" not in k for row in lst for k in row), str(lst[:1]))

    check("واعتمادٌ قصيرٌ يُرفض",
          _raises(lambda: PUB.connect(c, u, "telegram", secret=SHORT)))
    c.close()


# ═══════════ ٣ · الملكيّة ═══════════

def ownership():
    head("حسابُ غيرِك ليس لك")
    c = store.connect()
    a, b = mkuser(c, 3), mkuser(c, 4)
    acc = PUB.connect(c, a, "telegram", secret=TOKEN_B)

    check("المالكُ يقرأ حسابَه", PUB.account(c, a, acc["id"])["id"] == acc["id"])
    check("وغيرُه لا يقرؤه", _raises(lambda: PUB.account(c, b, acc["id"])))
    check("ولا يفصله", _raises(lambda: PUB.disconnect(c, b, acc["id"])))
    check("ولا يستعمله في تحقّقٍ قبل نشر",
          _raises(lambda: PUB.validate(c, b, acc["id"], "image")))
    check("وسردُ ب فارغ", PUB.accounts(c, b) == [])
    check("والحسابُ باقٍ", PUB.account(c, a, acc["id"])["id"] == acc["id"])
    c.close()


# ═══════════ ٤ · التحقّق قبل النشر ═══════════

def validation():
    head("التحقّقُ قبل الإرسال — بلا لمسِ شبكة")
    c = store.connect()
    u = mkuser(c, 5)
    acc = PUB.connect(c, u, "telegram", secret=TOKEN_B)

    check("صورةٌ مقبولة", PUB.validate(c, u, acc["id"], "image")["id"] == acc["id"])
    check("ومقطعٌ مقبول", PUB.validate(c, u, acc["id"], "video") is not None)
    check("ونوعٌ غيرُ مدعومٍ يُرفض",
          _raises(lambda: PUB.validate(c, u, acc["id"], "carrier-pigeon")))

    c.execute("UPDATE publish_accounts SET status='suspended' WHERE id=?",
              (acc["id"],))
    c.commit()
    check("وحسابٌ موقوفٌ يُرفض",
          _raises(lambda: PUB.validate(c, u, acc["id"], "image")))
    c.close()


# ═══════════ ٥ · سجلُّ المحاولات ═══════════

def attempts():
    head("سجلُّ المحاولات — نجاحًا وفشلًا، وبلا سرّ")
    c = store.connect()
    u = mkuser(c, 6)
    acc = PUB.connect(c, u, "telegram", secret=TOKEN_B)

    PUB.record(c, u, acc["id"], result="sent", external_id="msg-1")
    PUB.record(c, u, acc["id"], result="failed", error="الشبكة لم تستجب")
    rows = PUB.attempts(c, u)
    check("المحاولتان مسجَّلتان", len(rows) == 2, str(len(rows)))
    check("والنتيجةُ محفوظة",
          {r["result"] for r in rows} == {"sent", "failed"})
    check("والسجلُّ لا يحمل سرًّا",
          all(TOKEN_B not in str(r) for r in rows))
    check("وسردُ غيرِه فارغ", PUB.attempts(c, mkuser(c, 7)) == [])
    c.close()


# ═══════════ ٦ · بلا مفتاحٍ لا ربط ═══════════

def no_key():
    head("بلا مفتاحِ تعميةٍ لا يُربط حساب — فشلٌ مغلق")
    saved = os.environ.pop("FALAH_SECRET_KEY", None)
    try:
        check("الإغلاقُ يُرفض بلا مفتاح", _raises(lambda: PUB.seal("x")))
        check("والفكُّ كذلك", _raises(lambda: PUB.unseal("AAAA")))
    finally:
        if saved:
            os.environ["FALAH_SECRET_KEY"] = saved


def run():
    print("═" * 46)
    print("  النشر — صدقُ الحالة وحمايةُ الاعتماد والملكيّة")
    print("═" * 46)
    honesty(); secrets(); ownership(); validation(); attempts(); no_key()
    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: سقط {FAIL} من {OK + FAIL}")
        for n, d in FAILURES:
            print(f"  ✗ {n}" + (f"  ← {d}" if d else ""))
        return 1
    print(f"النتيجة: {OK} فحصًا · كلّها نجحت ✓")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    finally:
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
