"""حدُّ المعدّل — جدولٌ واحدٌ وقاعدةٌ واحدة.

كان الحدُّ على الدخول وحده. والتصدير والمقطع أثقلُ منه بكثير — بطاقةٌ
ثلاثُ ثوانٍ ومقطعٌ ستٌّ وعشرون — فمن يستطيع بدءَ ألفٍ في الساعة يخنق
الخدمة على غيره ولو لم يتجاوز حصّته الشهرية.

**وما يُعدّ هو العملُ المقبول لا الطلب.** مئةُ نقرةٍ على الزرّ نفسه تصير
مهمّةً واحدة (بفضل مفتاح التفرّد)، فتُحسب واحدة. بهذا يمنع الحدُّ الإساءة
ولا يكسر تزامنًا مشروعًا — وهو الفرق بين حدٍّ يحمي وحدٍّ يُزعج.

ولهذا يفترق موضعُ الفحص باختلاف المسار، وهو مُعلَنٌ في جدول المسارات:
`pre` يُفحص قبل المعالِج (تسجيلٌ · ملفٌّ · وكيل)، و`handler` يفحصه
المعالِجُ بنفسه بعد أن يتبيّن أن العمل مقبول (تصديرٌ · مقطع).
"""
import os

from falah import auth

def _lim(name, default, window):
    return (int(os.environ.get(f"FALAH_RATE_{name}", default)), window)

RATE = {
    "export":   _lim("EXPORT",   30, 3600),    # ثلاثون تصديرًا في الساعة
    "video":    _lim("VIDEO",    15, 3600),
    "agent":    _lim("AGENT",   300, 3600),    # سؤالٌ وجوابٌ — أخفّ بكثير
    "register": _lim("REGISTER", 20, 3600),    # لكل عنوان — والعناوين تُشارَك
    "file":     _lim("FILE",    600, 3600),
}

def ok(c, kind, who):
    """True إن بقي في الحدّ. ولا يزيد العدّاد — الزيادة عند القبول."""
    lim, win = RATE[kind]
    return not auth.throttled(c, f"rate:{kind}:{who}", limit=lim, window=win)

def bump(c, kind, who):
    auth.bump(c, f"rate:{kind}:{who}", window=RATE[kind][1])

def exceeded(kind):
    """جسمُ الردّ وترويسته عند التجاوز. الرمزُ ٤٢٩ يضعه المنادي."""
    lim, win = RATE[kind]
    mins = win // 60
    return ({"error": f"تجاوزتَ الحدّ: {lim} في {mins} دقيقة. "
                      f"انتظر قليلًا ثم أعد المحاولة.",
             "limit": lim, "window_seconds": win},
            [("Retry-After", str(win))])
