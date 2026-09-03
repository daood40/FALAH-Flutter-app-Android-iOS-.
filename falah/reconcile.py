"""مصالحة المصادر — أساس دعوى الموثوقية.

القاعدة: لا يخرج نصٌّ إلا إذا اتّفق عليه مصدران مستقلان. وما اختلفا فيه
يُحجب ويُدرَج في تقرير للمراجعة البشرية. لا تخمين، ولا ترجيح آلي.

الاختلاف نوعان:
  ١ اصطلاح ترميز — الحرف نفسه مكتوب بتسلسل يونيكود آخر (صور الهمزة،
    التطويل، الألف الخنجرية). هذه تُعتبر اتفاقًا، ويُخزَّن نص المرجع الأول.
  ٢ اختلاف حقيقي في الحروف — يُحجب النص ويُرفع للمراجعة.
"""
import re, unicodedata

# ــ البسملة الملحقة بأول السورة في بعض النسخ (خطأ عرض شائع) ــ
_BISM_PLAIN = "بسم الله الرحمن الرحيم"

def strip_leading_basmala(text: str, surah: int, ayah: int, plain_of) -> tuple[str, bool]:
    """تنزع البسملة المُلحقة بالآية الأولى — عدا الفاتحة (هي آية) وبراءة (لا بسملة فيها)."""
    if ayah != 1 or surah in (1, 9):
        return text, False
    p = plain_of(text)
    if not p.startswith(_BISM_PLAIN) or p == _BISM_PLAIN:
        return text, False
    # اقطع من النص الأصلي بمحاذاة عدد كلمات البسملة (٤ كلمات)
    words = text.split()
    for cut in range(3, 9):                     # البسملة ٤ كلمات، والهامش للاحتياط
        rest = " ".join(words[cut:])
        if plain_of(rest) == p[len(_BISM_PLAIN):].strip():
            return rest.strip(), True
    return text, False

# ــ معادلة الرسم: صور مختلفة لنفس الحرف ــ
_TATWEEL      = "ـ"
_HAMZA_ABOVE  = "ٔ"      # ٔ  همزة فوق
_HAMZA_BELOW  = "ٕ"
_SUPER_ALEF   = "ٰ"      # ٰ  ألف خنجرية
_ALEF_FORMS   = "آأإٱٲٳ"   # آ أ إ ٱ …

def orthographic_key(s: str) -> str:
    """مفتاح المقارنة بين الطبعات: يوحّد اصطلاحات الترميز دون المساس بالحروف.
    لا يُخزَّن ولا يُعرض — للمقارنة فقط."""
    s = unicodedata.normalize("NFD", s or "")
    s = s.replace(_TATWEEL, "")
    # ءَا / ـَٔا  →  صورة واحدة
    s = s.replace(_HAMZA_ABOVE, "ء").replace(_HAMZA_BELOW, "ء")
    s = re.sub("[" + _ALEF_FORMS + "]", "ا", s)
    # الألف الخنجرية حركةٌ لا حرف — تُجرَّد كبقية التشكيل، وإلا اختلّ ترتيب
    # المحارف بين طبعةٍ تكتب ـَٰٔ وأخرى تكتب ـَٔـٰ وهما نطقٌ واحد.
    s = re.sub("[ً-ٟۖ-ۭ" + _SUPER_ALEF + "]", "", s)
    s = re.sub(r"[^ء-ي]", "", s)               # الحروف فقط
    return s

# ــ نتيجة المصالحة ــ
AGREE_EXACT   = "exact"        # تطابق تام حرفًا وتشكيلًا
AGREE_ORTHO   = "orthographic" # نفس الحروف، اصطلاح ترميز مختلف
DISAGREE      = "conflict"     # اختلاف حقيقي — يُحجب

def compare(primary: str, secondary: str, fp) -> str:
    if fp(primary) == fp(secondary):
        return AGREE_EXACT
    if orthographic_key(primary) == orthographic_key(secondary):
        return AGREE_ORTHO
    return DISAGREE

def releasable(status: str) -> bool:
    """ما يُسمح بخروجه على البطاقة."""
    return status in (AGREE_EXACT, AGREE_ORTHO)
