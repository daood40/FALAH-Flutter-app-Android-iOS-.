"""سجلٌّ مبنيٌّ ومقاييسُ خفيفة — تشخيصٌ بلا إبطاءٍ وبلا تسريب.

خطُّ الأساس المقيس في `docs/P1.3_BASELINE.md` قال شيئًا واحدًا حاسمًا:
**الخادمُ يُصدر صفرَ بايتٍ سجلًّا لدورة تصديرٍ ناجحةٍ كاملة.** أي أن
إطلاقًا اليومَ إطلاقٌ أعمى: لا يُعرف من فشل، ولا لماذا، ولا كم مرّة.

والقواعدُ التي يقوم عليها هذا الملفّ:

١ · **عطبُ المراقبة لا يصير عطبًا أمنيًّا.** كلُّ كتابةٍ هنا مغلَّفةٌ: إن
    امتلأ القرصُ أو أُغلق الأنبوبُ يمضي الطلبُ ولا يسقط. والفرقُ بين هذا
    وسجلِّ التدقيق (`audit.py`) جوهريّ: ذاك حدثٌ قابلٌ للمراجعة وفشلُه
    يُسقط العملية؛ وهذا تشخيصٌ وفشلُه يُبتلع.

٢ · **لا سرَّ في سطر.** الحقلُ المشبوهُ يُحذف — لا يُستر بنجوم. الاستبدالُ
    بنجومٍ يُبقي الطولَ والموضع، وكلاهما معلومة.

٣ · **الانفجارُ العدديّ مُتجنَّب.** `request_id` و`user_id` و`job_id` حقولُ
    سجلٍّ لا وسومُ مقياس. وسومُ المقاييس معدودةٌ مسبقًا (مسارٌ · رمزٌ ·
    نتيجة)، فلا ينمو الجدولُ بعدد المستخدمين.

٤ · **الكلفةُ محسوبة.** المقاييسُ عدّاداتٌ في الذاكرة تُقرأ من `/metrics`
    عند الطلب — لا كتابةَ قرصٍ لكلِّ طلب. والسجلُّ سطرٌ واحدٌ في نهاية
    الطلب لا عدّةُ أسطرٍ متفرّقة.
"""
import json
import os
import re
import sys
import threading
import time

# ــــــــــــــــــــ ما لا يُسجَّل ــــــــــــــــــــ
# طبقتان كما في `audit.py`: الاسمُ والشكل. سرٌّ قد يُسمّى `data`، واسمٌ
# بريءٌ قد يحمل رمزًا — فلا تكفي واحدة.
_SECRET_NAME = re.compile(
    r"pass|pwd|secret|token|cookie|session|auth|api_?key|credential|salt|"
    r"hash|signature|receipt|payload|private", re.I)
_SECRET_SHAPE = re.compile(r"^[A-Za-z0-9_\-+/=]{24,}$")


def scrub(value):
    """يحذف ما يُشتبه أنه سرّ — حذفًا لا سترًا."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _SECRET_NAME.search(str(k)):
                continue                     # يُحذف الحقلُ كلُّه
            out[str(k)] = scrub(v)
        return out
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, str) and _SECRET_SHAPE.match(value):
        return None
    return value


# ــــــــــــــــــــ المستويات ــــــــــــــــــــ
# القاعدة: ليس كلُّ شيءٍ ERROR، ولا الأمنيُّ DEBUG.
#   DEBUG   — تفصيلٌ للتطوير
#   INFO    — ما جرى في المسار السعيد (طلبٌ تمّ، مهمّةٌ اكتملت)
#   WARNING — رفضٌ متوقَّعٌ في نظامٍ سليم: ٤٠١ · ٤٠٣ · ٤٢٩ · تحقّقٌ ساقط
#   ERROR   — عطبٌ فينا: ٥xx · استثناءٌ · مهمّةٌ فشلت
#   CRITICAL— ما يوقظ إنسانًا: القاعدةُ لا تُفتح · العاملُ ميّت
LEVELS = ("debug", "info", "warning", "error", "critical")
_ORDER = {n: i for i, n in enumerate(LEVELS)}

MIN_LEVEL = os.environ.get("FALAH_LOG_LEVEL", "info").lower()
if MIN_LEVEL not in _ORDER:
    MIN_LEVEL = "info"

# `json` سطرًا لكل حدث (للإنتاج، يُقرأ آليًّا) أو `text` (للتطوير، يُقرأ بعين)
FORMAT = os.environ.get("FALAH_LOG_FORMAT", "text").lower()

_lock = threading.Lock()


def log(level, event, **fields):
    """سطرٌ واحدٌ مبنيّ. **لا يرمي أبدًا** — انظر القاعدة ١ أعلاه."""
    try:
        if _ORDER.get(level, 99) < _ORDER[MIN_LEVEL]:
            return
        rec = {"ts": round(time.time(), 3), "level": level, "event": event}
        rec.update({k: v for k, v in scrub(fields).items() if v is not None})
        if FORMAT == "json":
            line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
        else:
            head = f"{time.strftime('%H:%M:%S')} {level:<7} {event}"
            rest = " ".join(f"{k}={v}" for k, v in rec.items()
                            if k not in ("ts", "level", "event"))
            line = f"{head} {rest}".rstrip()
        with _lock:
            sys.stderr.write(line + "\n")
            sys.stderr.flush()
    except Exception:
        # قرصٌ ممتلئٌ أو أنبوبٌ مغلق: يمضي الطلبُ ولا يسقط
        pass


def debug(event, **f): log("debug", event, **f)
def info(event, **f): log("info", event, **f)
def warn(event, **f): log("warning", event, **f)
def error(event, **f): log("error", event, **f)
def critical(event, **f): log("critical", event, **f)


# ــــــــــــــــــــ المقاييس ــــــــــــــــــــ
# عدّاداتٌ في الذاكرة. تُقرأ من `/metrics` وتُصفَّر بإعادة التشغيل — وهذا
# مقبولٌ لأن المقصودَ اتّجاهٌ لا محاسبة. والمحاسبةُ في `audit_logs`.

class _Metrics:
    """وسومٌ معدودةٌ مسبقًا — فلا ينفجر الجدولُ بعدد المستخدمين.

    القاعدةُ الحاسمة: **لا `user_id` ولا `request_id` ولا `job_id` وسمًا.**
    مسارٌ واحدٌ لكلِّ ألفِ مستخدمٍ يبقى سطرًا واحدًا؛ ولو وُسم بالمستخدم
    لصار ألفَ سطر، ولو وُسم بالطلب لصار مليونًا.
    """

    __slots__ = ("_c", "_h", "_lock", "started_at")

    def __init__(self):
        self._c = {}
        self._h = {}
        self._lock = threading.Lock()
        self.started_at = time.time()

    def inc(self, name, n=1, **labels):
        try:
            key = (name, tuple(sorted(labels.items())))
            with self._lock:
                self._c[key] = self._c.get(key, 0) + n
        except Exception:
            pass

    def observe(self, name, ms, **labels):
        """مدّةٌ بالمللي ثانية. يُحفظ العددُ والمجموعُ والأقصى — لا كلُّ قيمة:
        قائمةٌ تنمو بلا حدٍّ هي تسريبُ ذاكرةٍ لا قياس."""
        try:
            key = (name, tuple(sorted(labels.items())))
            with self._lock:
                n, s, mx = self._h.get(key, (0, 0.0, 0.0))
                self._h[key] = (n + 1, s + ms, max(mx, ms))
        except Exception:
            pass

    def snapshot(self):
        with self._lock:
            counters = [
                {"name": n, "labels": dict(l), "value": v}
                for (n, l), v in sorted(self._c.items(), key=lambda x: str(x[0]))
            ]
            timers = [
                {"name": n, "labels": dict(l), "count": c,
                 "avg_ms": round(s / c, 3) if c else 0.0, "max_ms": round(mx, 3)}
                for (n, l), (c, s, mx) in sorted(self._h.items(),
                                                 key=lambda x: str(x[0]))
            ]
        return {
            "uptime_s": round(time.time() - self.started_at, 1),
            "counters": counters,
            "timers": timers,
        }

    def reset(self):
        with self._lock:
            self._c.clear()
            self._h.clear()


M = _Metrics()


# ــــــــــــــــــــ تصنيفُ الأخطاء ــــــــــــــــــــ
# أسماءٌ مستخرَجةٌ من النظام القائم لا مخترَعة: لكلِّ صنفٍ مسارٌ يولّده.

class Code:
    AUTH_INVALID = "AUTH_INVALID"          # بريدٌ أو كلمةٌ خاطئة
    AUTH_EXPIRED = "AUTH_EXPIRED"          # جلسةٌ انتهت أو أُبطلت
    AUTHZ_DENIED = "AUTHZ_DENIED"          # صلاحيةٌ ناقصة
    AUTHZ_SCOPE = "AUTHZ_SCOPE"            # مورِدُ غيرِه
    VALIDATION = "VALIDATION"              # حقلٌ ناقصٌ أو قيمةٌ مرفوضة
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA = "QUOTA"
    DB_ERROR = "DB_ERROR"
    QUEUE_FULL = "QUEUE_FULL"
    WORKER_FAILED = "WORKER_FAILED"
    RENDER_FAILED = "RENDER_FAILED"
    INTERNAL = "INTERNAL"

    ALL = frozenset({
        AUTH_INVALID, AUTH_EXPIRED, AUTHZ_DENIED, AUTHZ_SCOPE, VALIDATION,
        RATE_LIMIT, QUOTA, DB_ERROR, QUEUE_FULL, WORKER_FAILED,
        RENDER_FAILED, INTERNAL,
    })


def code_for(status):
    """يشتقّ صنفَ الخطأ من رمز الحالة حين لا يُصرَّح به."""
    return {401: Code.AUTH_EXPIRED, 403: Code.AUTHZ_DENIED,
            429: Code.RATE_LIMIT, 400: Code.VALIDATION,
            }.get(status, Code.INTERNAL if status >= 500 else Code.VALIDATION)
