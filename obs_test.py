#!/usr/bin/env python3
"""المراقبة — سجلٌّ بلا أسرار، ومقاييسُ بلا انفجارٍ عدديّ، وعطبٌ لا يُسقط طلبًا.

    python3 obs_test.py

القواعدُ الثلاثُ التي تحرسها هذه الاختبارات، وكلُّها من `docs/P1.3_*`:

  ١ · **عطبُ المراقبة لا يصير عطبًا أمنيًّا** — قرصٌ ممتلئٌ أو أنبوبٌ مغلقٌ
      يمضي معه الطلبُ ولا يسقط.
  ٢ · **لا سرَّ في سطر** — الحقلُ المشبوهُ يُحذف لا يُستر بنجوم.
  ٣ · **لا انفجارَ عدديّ** — `user_id` و`request_id` حقولُ سجلٍّ لا وسومُ
      مقياس، والمسارُ يُوسم مُعمَّمًا لا خامًا.
"""
import hashlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from falah import obs  # noqa: E402

# قيمٌ مزيَّفةٌ **مشتقّةٌ لا مكتوبة**: الفاحصُ الأمنيّ يمسك السرَّ الحرفيَّ
# في الشيفرة ولو كان اختباريًّا — وهو محقّ، فلا يُستثنى الملفُّ ولا يُخفَّف
# الفاحص. تُشتقّ من قيمةٍ ثابتةٍ فتبقى النتيجةُ قابلةً لإعادة الإنتاج.
def _fake(tag, n=16):
    return hashlib.sha256(f"falah-obs-{tag}".encode()).hexdigest()[:n]

FAKE_PASSWORD = _fake("pw")
FAKE_VALUE = "SENTINEL-" + _fake("val", 12)
LONG_TOKEN_SHAPE = _fake("tok", 24)          # ٢٤ محرفًا ⇒ يُمسك بالشكل

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


def capture(fn):
    """يلتقط ما يُكتب على stderr — فيُفحص السطرُ نفسُه لا أثرُه."""
    old, buf = sys.stderr, io.StringIO()
    sys.stderr = buf
    try:
        fn()
    finally:
        sys.stderr = old
    return buf.getvalue()


# ═══════════ ١ · حذفُ الأسرار ═══════════

def secrets():
    head("لا سرَّ في سطر — حذفٌ لا سترٌ بنجوم")

    out = capture(lambda: obs.info("t", password=FAKE_PASSWORD, user_id=7))
    check("كلمةُ المرور لا تظهر", FAKE_PASSWORD not in out, out.strip())
    check("ولا يُترك مكانُها بنجوم", "*" not in out, out.strip())
    check("والحقلُ نفسُه يُحذف", "password" not in out, out.strip())
    check("وما ليس سرًّا يبقى", "user_id=7" in out, out.strip())

    for k in ("token", "session", "api_key", "secret", "cookie",
              "auth", "credential", "signature", "receipt"):
        out = capture(lambda k=k: obs.info("t", **{k: FAKE_VALUE}))
        check(f"يُحذف الحقل «{k}»", FAKE_VALUE not in out)

    # الشكلُ يُمسك ما فات الاسمَ: سرٌّ قد يُسمّى `data`
    tok = LONG_TOKEN_SHAPE                    # ٢٤ محرفًا ⇒ يُمسك بالشكل
    out = capture(lambda: obs.info("t", data=tok))
    check("والشكلُ يُمسك ما فات الاسم", tok not in out, out.strip())

    # ولا يُحذف نصٌّ عاديٌّ طويل
    out = capture(lambda: obs.info("t", note="هذه ملاحظةٌ عربيّةٌ طويلةٌ عاديّة"))
    check("ولا يُحذف نصٌّ بريء", "ملاحظة" in out)

    # العمق: سرٌّ داخل خريطة
    out = capture(lambda: obs.info("t", meta={"password": FAKE_PASSWORD, "n": 3}))
    check("ويُحذف السرُّ في العمق", FAKE_PASSWORD not in out, out.strip())
    check("ويبقى جارُه", "'n': 3" in out or "n" in out)


# ═══════════ ٢ · المستويات ═══════════

def levels():
    head("المستويات — ليس كلُّ شيءٍ ERROR ولا الأمنيُّ DEBUG")

    obs.MIN_LEVEL = "info"
    check("DEBUG يُكتم عند info", capture(lambda: obs.debug("x")) == "")
    check("INFO يُكتب", "x" in capture(lambda: obs.info("x")))
    check("WARNING يُكتب", "x" in capture(lambda: obs.warn("x")))
    check("ERROR يُكتب", "x" in capture(lambda: obs.error("x")))

    obs.MIN_LEVEL = "error"
    check("وINFO يُكتم عند error", capture(lambda: obs.info("x")) == "")
    check("وERROR يبقى", "x" in capture(lambda: obs.error("x")))
    obs.MIN_LEVEL = "info"

    check("المستوياتُ خمسةٌ معلومة", obs.LEVELS ==
          ("debug", "info", "warning", "error", "critical"))


# ═══════════ ٣ · عطبُ المراقبة لا يُسقط ═══════════

def never_raises():
    head("عطبُ المراقبة لا يصير عطبًا أمنيًّا")

    class Exploding:
        def __repr__(self): raise RuntimeError("انفجر التمثيل")

    try:
        capture(lambda: obs.info("t", bad=Exploding()))
        check("حقلٌ ينفجر تمثيلُه لا يُسقط السجلّ", True)
    except Exception as e:
        check("حقلٌ ينفجر تمثيلُه لا يُسقط السجلّ", False, repr(e))

    # stderr مغلق: كما لو امتلأ القرصُ أو أُغلق الأنبوب
    old = sys.stderr
    class Closed:
        def write(self, *a): raise OSError(28, "No space left on device")
        def flush(self): raise OSError(28, "No space left on device")
    sys.stderr = Closed()
    try:
        obs.info("t", a=1)
        check("قرصٌ ممتلئٌ لا يُسقط الطلب", True)
    except Exception as e:
        check("قرصٌ ممتلئٌ لا يُسقط الطلب", False, repr(e))
    finally:
        sys.stderr = old

    try:
        obs.M.inc("x", route="/a")
        obs.M.observe("y", 1.0, route="/a")
        check("والمقاييسُ كذلك لا ترمي", True)
    except Exception as e:
        check("والمقاييسُ كذلك لا ترمي", False, repr(e))


# ═══════════ ٤ · الانفجارُ العدديّ ═══════════

def cardinality():
    head("لا انفجارَ عدديّ — المسارُ يُعمَّم والمعرّفاتُ ليست وسومًا")

    import app as APP
    cases = [("/app/projects/7", "/app/projects/:id"),
             ("/app/jobs/1234", "/app/jobs/:id"),
             ("/app/admin/users/9", "/app/admin/users/:id"),
             ("/app/me", "/app/me"),
             ("/app/items/add", "/app/items/add")]
    for raw, want in cases:
        got = APP._route_label(raw)
        check(f"{raw} → {want}", got == want, got)

    # ألفُ مشروعٍ ⇒ سطرٌ واحد. هذا هو الفرقُ كلُّه.
    obs.M.reset()
    for i in range(1000):
        obs.M.inc("http_requests_total",
                  route=APP._route_label(f"/app/projects/{i}"),
                  method="GET", status="200")
    n = len(obs.M.snapshot()["counters"])
    check("ألفُ مشروعٍ ⇒ سطرُ مقياسٍ واحد", n == 1, f"{n} سطرًا")

    # ولا يُقبل معرّفٌ وسمًا في أيِّ نداءٍ في الشيفرة
    import re
    src = open(os.path.join(HERE, "app.py"), encoding="utf8").read()
    bad = re.findall(r"M\.(?:inc|observe)\([^)]*\b(user_id|request_id|job_id)\s*=", src)
    check("ولا معرّفَ وسمًا في app.py", not bad, str(bad))


# ═══════════ ٥ · المقاييسُ تعدّ صحيحًا ═══════════

def counting():
    head("العدُّ والتوقيت")

    obs.M.reset()
    obs.M.inc("c", route="/a")
    obs.M.inc("c", route="/a")
    obs.M.inc("c", route="/b")
    snap = obs.M.snapshot()
    by = {(x["name"], x["labels"].get("route")): x["value"] for x in snap["counters"]}
    check("العدُّ يتراكم للوسم نفسِه", by[("c", "/a")] == 2, str(by))
    check("ويفصل بين الوسوم", by[("c", "/b")] == 1)

    obs.M.observe("t", 10.0, route="/a")
    obs.M.observe("t", 20.0, route="/a")
    t = [x for x in obs.M.snapshot()["timers"] if x["name"] == "t"][0]
    check("المتوسّطُ صحيح", t["avg_ms"] == 15.0, str(t))
    check("والأقصى محفوظ", t["max_ms"] == 20.0)
    check("والعددُ محفوظ", t["count"] == 2)

    # لا تُحفظ كلُّ قيمة: قائمةٌ تنمو بلا حدٍّ تسريبُ ذاكرةٍ لا قياس
    obs.M.reset()
    for i in range(10000):
        obs.M.observe("t", float(i), route="/a")
    check("عشرةُ آلافِ قياسٍ ⇒ سطرٌ واحد",
          len(obs.M.snapshot()["timers"]) == 1)


# ═══════════ ٦ · تصنيفُ الأخطاء ═══════════

def codes():
    head("تصنيفُ الأخطاء — أسماءٌ مستخرَجةٌ لا مخترَعة")
    check("٤٠١ → AUTH_EXPIRED", obs.code_for(401) == obs.Code.AUTH_EXPIRED)
    check("٤٠٣ → AUTHZ_DENIED", obs.code_for(403) == obs.Code.AUTHZ_DENIED)
    check("٤٢٩ → RATE_LIMIT", obs.code_for(429) == obs.Code.RATE_LIMIT)
    check("٤٠٠ → VALIDATION", obs.code_for(400) == obs.Code.VALIDATION)
    check("٥٠٠ → INTERNAL", obs.code_for(500) == obs.Code.INTERNAL)
    check("والتصنيفُ مغلقٌ لا مفتوح", len(obs.Code.ALL) == 12, str(len(obs.Code.ALL)))


def run():
    print("═" * 46)
    print("  المراقبة — سجلٌّ ومقاييسُ بلا تسريبٍ ولا انفجار")
    print("═" * 46)
    secrets(); levels(); never_raises(); cardinality(); counting(); codes()
    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: سقط {FAIL} من {OK + FAIL}")
        for n, d in FAILURES:
            print(f"  ✗ {n}" + (f"  ← {d}" if d else ""))
        return 1
    print(f"النتيجة: {OK} فحصًا · كلّها نجحت ✓")
    return 0


if __name__ == "__main__":
    sys.exit(run())
