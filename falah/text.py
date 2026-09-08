"""أدوات النص العربي — النص الأصلي لا يُعدَّل أبدًا، كل الدوال هنا تُنتج نسخًا موازية."""
import re, unicodedata, hashlib

# علامات التشكيل والوقف — لا يدخل فيها أي حرف هجاء
TASHKEEL   = re.compile("[ً-ٰٟۖ-ۭـ]")
HIDDEN     = re.compile("[​-‏‪-‮⁦-⁩﻿­]")
CTRL_MARKS = re.compile("[؜‎‏]")

def clean(s: str) -> str:
    """إزالة المحارف الخفية واتجاه النص فقط — الحروف والتشكيل تبقى كما هي."""
    return re.sub(r"[ \t]+", " ", HIDDEN.sub("", s or "")).strip()

def norm(s: str) -> str:
    """توحيد الترميز قبل البصمة: NFC + تنظيف الفراغات."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", clean(s))).strip()

def fingerprint(s: str) -> str:
    return hashlib.sha256(norm(s).encode("utf-8")).hexdigest()[:32]

def searchable(s: str) -> str:
    """نسخة للفهرسة والمقارنة: بلا تشكيل، بتوحيد الألف والهمزة والتاء المربوطة."""
    s = TASHKEEL.sub("", unicodedata.normalize("NFC", clean(s)))
    s = re.sub("[إأآٱ]", "ا", s)
    s = s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()

def core_key(s: str, words: int = 8) -> str:
    """مفتاح تجميع: أول ثماني كلمات من النسخة المجرّدة — يلمّ روايات المتن الواحد."""
    return " ".join(searchable(s).split()[:words])

def tashkeel_ratio(s: str) -> float:
    letters = [c for c in unicodedata.normalize("NFC", s) if c.isalpha()]
    if not letters: return 0.0
    marks = len(TASHKEEL.findall(s))
    return round(marks / max(len(letters), 1), 3)

def has_hidden(s: str) -> bool:
    return bool(HIDDEN.search(s or ""))

def is_nfc(s: str) -> bool:
    return unicodedata.is_normalized("NFC", s or "")

PARTICLES = re.compile(r"^(?:وال|فال|بال|كال|لل|ال|و|ف|ب|ك|ل)")

def stem_light(w: str) -> str:
    """تجريد خفيف: حذف أدوات البداية فقط. لا يُطبَّق على النص المخزَّن."""
    s = PARTICLES.sub("", w)
    return s if len(s) >= 3 else w

def search_variants(term: str) -> list[str]:
    """صيغ البحث بالتراجع: الكلمة كما هي، ثم بلا أدوات، ثم أطول جذر ممكن.
    الفهرس ثلاثيّ المقاطع (trigram) فيقبل البحث داخل الكلمة لا من أولها فقط."""
    words = [w for w in searchable(term).split() if len(w) > 1]
    if not words: return []
    out = []
    for form in (words, [stem_light(w) for w in words]):
        q = " ".join('"%s"' % w for w in form)
        if q not in out: out.append(q)
    longest = max(words, key=len)
    for n in (5, 4, 3):
        if len(longest) > n:
            q = '"%s"' % stem_light(longest)[:n]
            if q not in out: out.append(q)
    return out

def fts_query(term: str):
    v = search_variants(term)
    return v[0] if v else None
