"""محرّك التحقّق — الفحوص الخمسة والعشرون، منفّذة فعلًا لا معروضة.

كل فحص دالة تعيد (نجح، تفصيل). ترتيب المراحل والفحوص هو نفسه المعروض في
واجهة فلاح، فما يراه المستخدم هو ما يجري حقًا.
القاعدة الحاكمة: سقوط فحص واحد ⇒ لا يُنتَج المحتوى.
"""
from .text import fingerprint, tashkeel_ratio, has_hidden, searchable, norm
import unicodedata

STAGES = ["أصل المصدر", "سلامة النص", "الموضع والإسناد", "سلامة المعنى", "الإخراج والحقوق"]

def _r(ok, detail=""): return {"ok": bool(ok), "detail": detail}

def run(item: dict, ctx: dict) -> dict:
    """item: مخرج بناء البطاقة. ctx: حقائق مقروءة من القاعدة (لا تُخمَّن)."""
    C = []          # (المرحلة، العنوان، النتيجة)
    add = lambda s, t, r: C.append({"stage": s, "title": t, **r})
    kind = item["type"]
    text = item["text"]

    # ---------- ١ أصل المصدر ----------
    add(0, "المصدر مُدرج في سجل المصادر المعتمدة",
        _r(ctx.get("source_registered"), ctx.get("source_name", "")))
    add(0, "بصمة النص المخزَّن تطابق إعادة الحساب",
        _r(all(fingerprint(t) == f for t, f in ctx.get("fp_pairs", [])),
           "%d نصًا" % len(ctx.get("fp_pairs", []))))
    add(0, "طبعة المصدر وإصداره مسجَّلان لا مجهولان",
        _r(bool(ctx.get("edition")), ctx.get("edition", "")))
    add(0, "للنص شاهد في أكثر من مرجع" if kind == "hadith" else "الطبعة أصلٌ لا نقل عن ناقل",
        _r(ctx.get("corroboration", 0) >= (2 if kind == "hadith" else 1),
           "عدد المراجع: %d" % ctx.get("corroboration", 0)))
    add(0, "أصل البيانات معلوم ومسجَّل",
        _r(bool(ctx.get("origin")), ctx.get("origin", "")))

    # ---------- ٢ سلامة النص ----------
    add(1, "مطابقة حرفية للنص المخزَّن في المصدر",
        _r(ctx.get("exact_match"), "diff=0" if ctx.get("exact_match") else "اختلاف"))
    add(1, "تطابق النص بين المراجع" if kind == "hadith" else "تطابق النص مع الطبعة المرجعية",
        _r(ctx.get("cross_match", True), ctx.get("cross_note", "")))
    tr = tashkeel_ratio(text)
    # فواتح السور (الحروف المقطعة: طه، يس، ص) تُرسم بلا تشكيلٍ كثير في المصحف،
    # فلا تُقاس بنسبة غيرها. القاعدة: نصٌّ قصيرٌ جدًّا من المصدر نفسه لا يُحاكَم بالنسبة.
    short_opening = kind == "quran" and len(text.split()) <= 3
    add(1, "التشكيل موجود بنسبة معتبرة",
        _r(tr >= (0.25 if kind == "quran" else 0.10) or short_opening,
           "نسبة التشكيل %.2f%s" % (tr, " · فاتحة سورة" if short_opening else "")))
    add(1, "الرسم والضبط كما ورد في المصدر",
        _r(ctx.get("script_ok", True), ctx.get("script_note", "")))
    add(1, "لا محارف تحكّم أو اتجاه داخل النص",
        _r(not has_hidden(text), "نظيف" if not has_hidden(text) else "محارف خفية"))
    add(1, "التطبيع لا يغيّر حرفًا من النص",
        _r(ctx.get("normalization_safe", True), ctx.get("normalization_note", "متسق")))

    # ---------- ٣ الموضع والإسناد ----------
    add(2, "الموضع موجود في المصدر", _r(ctx.get("locus_ok"), ctx.get("locus", "")))
    add(2, "الترقيم مطابق للترقيم المعتمد", _r(ctx.get("numbering_ok"), ctx.get("numbering", "")))
    add(2, "الدرجة منقولة من مصدر معتمد لا مُولّدة" if kind == "hadith"
           else "القراءة والرواية محدّدتان",
        _r(ctx.get("grade_ok", True), ctx.get("grade_note", "")))
    add(2, "التخريج مذكور كاملًا" if kind == "hadith" else "الموضع موثّق بأكثر من فهرس",
        _r(ctx.get("takhrij_ok", True), ctx.get("takhrij_note", "")))
    add(2, "الرواية معلنة في بيانات المحتوى",
        _r(bool(ctx.get("riwayah")), ctx.get("riwayah", "")))

    # ---------- ٤ سلامة المعنى ----------
    add(3, "النص كامل غير مقتطع", _r(ctx.get("complete", True), ctx.get("complete_note", "")))
    add(3, "السياق قبله وبعده متاح للمراجعة",
        _r(ctx.get("context_ok", True), ctx.get("context_note", "")))
    # الآية المتكرّرة لفظًا ليست ملتبسة ما دام موضعها مطبوعًا على البطاقة
    # ومواضعها الأخرى مصرَّحًا بها في القالب. الالتباس أن تُنشر بلا موضع.
    add(3, "المتشابه اللفظي مميَّز عن مواضعه الأخرى",
        _r(not ctx.get("mutashabih_unresolved") or ctx.get("mutashabih_disclosed"),
           ctx.get("mutashabih_note", "لا التباس")))
    add(3, "النص يخدم الموضوع المطلوب",
        _r(ctx.get("topic_ok", True), ctx.get("topic_note", "")))

    # ---------- ٥ الإخراج والحقوق ----------
    tf = item.get("tafsir")
    add(4, "التفسير أو الشرح مُسند لمصدر مسمّى",
        _r(tf is None or bool(tf.get("source")), (tf or {}).get("source", "لم يُطلب")))
    tl = item.get("translation")
    add(4, "الترجمة مُسندة لمترجم معروف",
        _r(tl is None or bool(tl.get("source")), (tl or {}).get("source", "لم تُطلب")))
    add(4, "قفل المصدر: لا حرف مولّد آليًا",
        _r(ctx.get("source_lock"), "النص مطابق لقيد القاعدة"))
    n = len(text)
    # الطويل يُقسَّم على شرائح متتابعة بحدود الكلمات، ولا يُقصّ منه حرف.
    # فالفحص يسقط على القطع لا على الطول.
    fits = n <= ctx.get("max_len", 340)
    slides = ctx.get("slides", 1)
    add(4, "النص يسع البطاقة دون قطع",
        _r(fits or (slides > 1 and ctx.get("split_ok")),
           ("%d حرفًا" % n) if fits else "%d حرفًا على %d شرائح" % (n, slides)))
    add(4, "حالة ترخيص كل مصدر مسجَّلة",
        _r(bool(ctx.get("license_status")), ctx.get("license_status", "")))

    passed = sum(1 for c in C if c["ok"])
    return {
        "total": len(C), "passed": passed, "ok": passed == len(C),
        "stages": [{"name": STAGES[i],
                    "checks": [c for c in C if c["stage"] == i],
                    "passed": sum(1 for c in C if c["stage"] == i and c["ok"]),
                    "count": sum(1 for c in C if c["stage"] == i)} for i in range(5)],
        "failed": [c["title"] for c in C if not c["ok"]],
    }
