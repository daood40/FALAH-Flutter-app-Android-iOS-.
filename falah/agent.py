"""وكيل فلاح — سؤالٌ واحدٌ في كل مرّة، والبطاقة فوق السؤال تتغيّر مع كل إجابة.

الوكيل هنا **لا يولّد نصًّا**. أسئلته تُحدِّد *الاختيار* لا *النصّ*: أيّ سورة،
وأيّ آية، وأيّ باب، وأيّ رقم. ثم يذهب إلى القاعدة فيأخذ ما اجتاز الفحوص
الخمسة والعشرين. وما لم يجتز يُعرض عليك بسبب سقوطه، ولا يُستبدل بشيءٍ من عنده.

ترتيب الأسئلة كما طُلب:
  نوع المحتوى (والأبعاد تتبعه تلقائيًّا) → المنصّة → العلامة المائية →
  نوع المحتوى الشرعي → [فرع القرآن أو فرع الحديث] →
  تصميم القالب → لون التصميم → نوع الخط → لون الخط → الترجمان.
"""
import sqlite3, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# نوع المحتوى يحدّد الأبعاد وحده — لا يُسأل المستخدم عن المقاس.
CONTENT_TYPES = [
    ("long_video",  "فيديو طويل", "wide"),
    ("short_video", "فيديو قصير", "vertical"),
    ("image",       "صورة",       "square"),
    ("post_tall",   "منشور طولي", "portrait"),
    ("story",       "قصة",        "vertical"),
    ("post",        "منشور",      "square"),
]
RATIO_OF = {v: r for v, _, r in CONTENT_TYPES}
RATIO_AR = {"wide": "عريض ١٩٢٠×١٠٨٠", "vertical": "طولي ١٠٨٠×١٩٢٠",
            "square": "مربّع ١٠٨٠×١٠٨٠", "portrait": "‏٤:٥ — ١٠٨٠×١٣٥٠"}

PLATFORMS = [("youtube","يوتيوب"), ("facebook","فيسبوك"), ("instagram","إنستقرام"),
             ("tiktok","تيك توك"), ("x","إكس"), ("telegram","تيليجرام"),
             ("messenger","ماسنجر"), ("whatsapp","واتساب")]

DESIGNS = [("parch","رقّ عتيق"), ("night","ليلي مذهّب"), ("ivory","نقي")]
TINTS   = [("auto","لون التصميم كما هو"), ("sand","رمليّ"), ("green","أخضر"),
           ("navy","كحليّ"), ("coal","فحميّ"), ("gold","ذهبيّ على أسود")]
FONTS   = [("auto","تلقائي — أميري قرآن للآيات وأميري للحديث"),
           ("amiri","أميري"), ("amiri-quran","أميري قرآن")]
INKS    = [("auto","لون الهيئة (تلقائي)"), ("#2B2116","بنّي داكن"),
           ("#1E2A24","أخضر داكن"), ("#111111","أسود"), ("#F0E5CA","عاجيّ")]

# ترتيب الخطوات: المشترك، ثم الفرع، ثم التصميم.
COMMON_HEAD = ["content_type", "platform", "watermark", "source_kind"]
QURAN_STEPS = ["surah", "count", "from", "to", "tafsir", "translation", "reciter"]
HADITH_STEPS = ["book", "chapter", "no", "grade", "matn", "count", "from", "to"]
COMMON_TAIL = ["design", "tint", "font", "ink", "translator"]

LABEL = {
    "content_type": "ما نوع المحتوى؟",
    "platform":     "لأي منصّة؟",
    "watermark":    "ما علامتك المائية؟",
    "source_kind":  "ما نوع المحتوى الشرعي؟",
    "surah":        "أي سورة؟",
    "count":        "كم آية؟",
    "from":         "من أي آية؟",
    "to":           "إلى أي آية؟",
    "tafsir":       "أي تفسير؟",
    "translation":  "أي ترجمة؟",
    "reciter":      "أي قارئ؟",
    "book":         "أي كتاب؟",
    "chapter":      "أي باب؟",
    "no":           "أي حديث؟",
    "grade":        "درجة الحديث",
    "matn":         "نصّ الحديث",
    "design":       "أي تصميم للقالب؟",
    "tint":         "أي لونٍ للتصميم؟",
    "font":         "أي خط؟",
    "ink":          "أي لونٍ للخط؟",
    "translator":   "أي ترجمان؟",
}

WHY = {
    "content_type": "الأبعاد تُختار من النوع وحده: الطويل عريض، والقصير والقصة طوليّان، والصورة والمنشور مربّعان.",
    "platform":     "المنصّة تُكتب في وصف التصدير ولا تغيّر النصّ.",
    "watermark":    "تُكتب في خانتها، ومقابلها خانة علامة فلاح — وهي تلقائية لا تُحذف.",
    "source_kind":  "الآيات تُعرض بالرسم العثماني، والأحاديث بدرجتها ومن حكم بها.",
    "surah":        "عدد آيات السورة يُقرأ من القاعدة، فلا يُطلب رقمٌ لا وجود له.",
    "count":        "العدد يملأ «من» و«إلى» تلقائيًّا، ولك تعديلهما.",
    "from":         "أرقام الآيات المعروضة هي آيات هذه السورة وحدها.",
    "to":           "لا يُقبل ما تجاوز آخر آيةٍ في السورة.",
    "tafsir":       "التفسير يُنقل بنصّه وباسم مصدره، ولا يُكتب بالذكاء الاصطناعي.",
    "translation":  "الترجمة منقولةٌ عن ترجمةٍ منشورة، ومنسوبةٌ إليها.",
    "reciter":      "القارئ يُستعمل حين تُصدَّر البطاقة فيديو.",
    "book":         "لا يُعرض إلا كتابٌ فيه أحاديث اجتازت الفحص.",
    "chapter":      "الأبواب من ترقيم الكتاب نفسه.",
    "no":           "الأرقام المعروضة أحاديث هذا الباب التي اجتازت الفحص.",
    "grade":        "الدرجة من مصدرها ومن حكم بها — تُقرأ ولا تُختار.",
    "matn":         "المتن كما في المصدر، بلا زيادةٍ ولا نقص.",
    "design":       "التصميم يغيّر الهيئة لا النصّ.",
    "tint":         "اللون يغيّر الورق والإطار.",
    "font":         "أميري قرآن للرسم العثماني، وأميري لسائر النصوص.",
    "ink":          "لون الحبر؛ و«تلقائي» يتبع لون التصميم.",
    "translator":   "الترجمان يظهر في خانة الترجمة أسفل البطاقة.",
}

NO_CHAPTER = "بلا بابٍ مسجَّل في المصدر"

class Ask(Exception): pass

def _ro(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    return c

def _opt(pairs):
    return [{"value": v, "label": l} for v, l in pairs]

# ───────────────────────── قوائم من القاعدة ─────────────────────────

def surahs(db):
    c = _ro(db)
    rows = c.execute("""SELECT s.number, s.name_ar,
                          (SELECT COUNT(*) FROM ayat a WHERE a.surah=s.number) n,
                          (SELECT COUNT(*) FROM ayat a WHERE a.surah=s.number AND a.card_ok=1) ok
                        FROM surahs s ORDER BY s.number""").fetchall()
    c.close()
    return [dict(r) for r in rows]

def surah_info(db, n):
    for r in surahs(db):
        if r["number"] == int(n): return r
    return None

def books(db):
    c = _ro(db)
    rows = c.execute("""SELECT b.code, b.name_ar,
                          (SELECT COUNT(*) FROM hadiths h WHERE h.book_id=b.id AND h.card_ok=1) n
                        FROM books b ORDER BY b.id""").fetchall()
    c.close()
    return [dict(r) for r in rows if r["n"]]

def chapters(db, book):
    """أبواب الكتاب، ومعها — إن وُجد — بابٌ ظاهرٌ لِما لم يُسجَّل بابه في
    المصدر نفسه. لا يُنسب حديثٌ إلى بابٍ لم يذكره مصدره؛ يُعرض على حاله."""
    c = _ro(db)
    rows = c.execute("""SELECT ch.chapter_id, ch.name_ar,
                          (SELECT COUNT(*) FROM hadiths h WHERE h.book_id=b.id
                            AND h.chapter_id=ch.chapter_id AND h.card_ok=1) n
                        FROM chapters ch JOIN books b ON b.id=ch.book_id
                        WHERE b.code=? ORDER BY ch.chapter_id""", (book,)).fetchall()
    out = [dict(r) for r in rows if r["n"]]
    orphan = c.execute("""SELECT COUNT(*) FROM hadiths h JOIN books b ON b.id=h.book_id
                          WHERE b.code=? AND h.card_ok=1 AND (h.chapter_id IS NULL
                            OR NOT EXISTS (SELECT 1 FROM chapters ch
                               WHERE ch.book_id=h.book_id AND ch.chapter_id=h.chapter_id))""",
                       (book,)).fetchone()[0]
    c.close()
    if orphan:
        out.append({"chapter_id": -1, "name_ar": NO_CHAPTER, "n": orphan})
    return out

def chapter_hadiths(db, book, chapter):
    c = _ro(db)
    if str(chapter) == "-1":         # ما لم يُسجَّل بابه في المصدر
        rows = c.execute("""SELECT h.number_in_book no, h.grade, substr(h.matn,1,110) matn
                            FROM hadiths h JOIN books b ON b.id=h.book_id
                            WHERE b.code=? AND h.card_ok=1 AND (h.chapter_id IS NULL
                              OR NOT EXISTS (SELECT 1 FROM chapters ch
                                 WHERE ch.book_id=h.book_id AND ch.chapter_id=h.chapter_id))
                            ORDER BY h.number_in_book""", (book,)).fetchall()
    else:
        rows = c.execute("""SELECT h.number_in_book no, h.grade, substr(h.matn,1,110) matn
                            FROM hadiths h JOIN books b ON b.id=h.book_id
                            WHERE b.code=? AND h.chapter_id=? AND h.card_ok=1
                            ORDER BY h.number_in_book""", (book, int(chapter))).fetchall()
    c.close()
    return [dict(r) for r in rows]

def hadith_brief(db, book, no):
    c = _ro(db)
    r = c.execute("""SELECT h.grade, h.grade_by, h.grade_basis, h.matn, h.narrator_ar
                     FROM hadiths h JOIN books b ON b.id=h.book_id
                     WHERE b.code=? AND h.number_in_book=?""", (book, int(no))).fetchone()
    c.close()
    return dict(r) if r else None

def _sources(db, kind):
    c = _ro(db)
    rows = c.execute("SELECT code, name FROM sources WHERE kind=? AND enabled=1",
                     (kind,)).fetchall()
    c.close()
    return [{"value": r["code"], "label": r["name"]} for r in rows]

def reciters(db):
    c = _ro(db)
    rows = c.execute("SELECT code, name, riwayah FROM reciters ORDER BY riwayah, name").fetchall()
    c.close()
    return [{"value": r["code"], "label": f"{r['name']} — {r['riwayah']}"} for r in rows]

# ───────────────────────── تنظيف الإجابات ─────────────────────────

def sanitize(answers, db):
    """كل إجابةٍ تعتمد على ما قبلها؛ فإذا تغيّر ما قبلها سقطت. هذا يمنع
    بقاء «رقم حديثٍ» من بابٍ لم يعد مختارًا، أو «آية» خارج السورة."""
    a = {k: v for k, v in (answers or {}).items() if v not in (None, "")}
    kind = a.get("source_kind")
    if kind not in ("quran", "hadith"):
        for k in QURAN_STEPS + HADITH_STEPS: a.pop(k, None)
        return a
    if kind == "quran":
        for k in ("book", "chapter", "no", "grade", "matn"): a.pop(k, None)
        s = surah_info(db, a["surah"]) if a.get("surah") else None
        if a.get("surah") and not s: a.pop("surah")
        if s:
            last = s["n"]
            for k in ("from", "to"):
                try:
                    if not (1 <= int(a[k]) <= last): a.pop(k)
                except (KeyError, ValueError, TypeError): a.pop(k, None)
            if a.get("from") and a.get("to") and int(a["to"]) < int(a["from"]):
                a["to"] = a["from"]
        else:
            for k in ("from", "to", "count"): a.pop(k, None)
    else:
        for k in ("surah", "tafsir", "reciter"): a.pop(k, None)
        if a.get("book") and a["book"] not in {b["code"] for b in books(db)}:
            a.pop("book")
        if not a.get("book"):
            for k in ("chapter", "no", "grade", "matn", "from", "to", "count"): a.pop(k, None)
        elif a.get("chapter"):
            nums = [h["no"] for h in chapter_hadiths(db, a["book"], a["chapter"])]
            if not nums:
                for k in ("chapter", "no", "from", "to"): a.pop(k, None)
            else:
                for k in ("no", "from", "to"):
                    try:
                        if int(a[k]) not in nums: a.pop(k)
                    except (KeyError, ValueError, TypeError): a.pop(k, None)
        else:
            for k in ("no", "from", "to"): a.pop(k, None)
    return a

def steps_for(answers):
    k = answers.get("source_kind")
    branch = QURAN_STEPS if k == "quran" else (HADITH_STEPS if k == "hadith" else [])
    tail = [s for s in COMMON_TAIL if not (s == "translator" and k == "quran")]
    return COMMON_HEAD + branch + tail

# ───────────────────────── السؤال التالي ─────────────────────────

HADITH_LABEL = {"count": "كم حديثًا؟", "from": "من أي حديث؟", "to": "إلى أي حديث؟"}

def question(step, a, db, default_watermark=None):
    text = LABEL[step]
    if a.get("source_kind") == "hadith" and step in HADITH_LABEL:
        text = HADITH_LABEL[step]
    q = {"id": step, "text": text, "why": WHY[step], "type": "choice"}

    if step == "content_type":
        q["options"] = [{"value": v, "label": l, "hint": RATIO_AR[r]} for v, l, r in CONTENT_TYPES]
    elif step == "platform":
        q["options"] = _opt(PLATFORMS)
    elif step == "watermark":
        q.update(type="free", placeholder="مثال: قناة نور الهدى",
                 default=default_watermark or "", note="علامة فلاح تُضاف تلقائيًّا في خانتها.")
    elif step == "source_kind":
        q["options"] = _opt([("quran", "قرآن كريم"), ("hadith", "حديث")])

    # ── فرع القرآن ──
    elif step == "surah":
        q["options"] = [{"value": str(s["number"]), "label": f"{s['number']}. {s['name_ar']}",
                         "hint": f"{s['n']} آية"} for s in surahs(db)]
    elif step == "count" and a.get("source_kind") == "quran":
        s = surah_info(db, a["surah"])
        q.update(type="number", min=1, max=s["n"], default=1,
                 note=f"سورة {s['name_ar']}: {s['n']} آية.")
    elif step == "from" and a.get("source_kind") == "quran":
        s = surah_info(db, a["surah"])
        q["options"] = [{"value": str(i), "label": str(i)} for i in range(1, s["n"] + 1)]
        q["default"] = "1"          # أوّل السورة — ولك تغييره
    elif step == "to" and a.get("source_kind") == "quran":
        s = surah_info(db, a["surah"])
        start = int(a.get("from", 1)); n = int(a.get("count", 1) or 1)
        q["options"] = [{"value": str(i), "label": str(i)} for i in range(start, s["n"] + 1)]
        q["default"] = str(min(s["n"], start + n - 1))
    elif step == "tafsir":
        q["options"] = [{"value": "none", "label": "بلا تفسير"}] + _sources(db, "tafsir")
    elif step == "translation":
        q["options"] = [{"value": "none", "label": "بلا ترجمة"}] + _sources(db, "translation")
    elif step == "reciter":
        q["options"] = [{"value": "none", "label": "بلا تلاوة"}] + reciters(db)

    # ── فرع الحديث ──
    elif step == "book":
        q["options"] = [{"value": b["code"], "label": b["name_ar"],
                         "hint": f"{b['n']} حديثًا جاهزًا"} for b in books(db)]
    elif step == "chapter":
        q["options"] = [{"value": str(ch["chapter_id"]), "label": ch["name_ar"],
                         "hint": f"{ch['n']} حديثًا"} for ch in chapters(db, a["book"])]
    elif step == "no":
        q["options"] = [{"value": str(h["no"]), "label": f"حديث {h['no']}",
                         "hint": (h["matn"] or "")[:70]}
                        for h in chapter_hadiths(db, a["book"], a["chapter"])]
    elif step in ("grade", "matn"):
        h = hadith_brief(db, a["book"], a["no"]) or {}
        q.update(type="auto",
                 value=(h.get("grade") or "الدرجة غير مسجّلة") if step == "grade" else (h.get("matn") or ""),
                 note=(f"حكم بها: {h.get('grade_by') or '—'}" if step == "grade"
                       else f"الراوي: {h.get('narrator_ar') or '—'}"))
    elif step == "count":
        nums = [h["no"] for h in chapter_hadiths(db, a["book"], a["chapter"])]
        q.update(type="number", min=1, max=len(nums), default=1,
                 note=f"في هذا الباب {len(nums)} حديثًا جاهزًا.")
    elif step in ("from", "to"):
        nums = [h["no"] for h in chapter_hadiths(db, a["book"], a["chapter"])]
        if step == "to":
            start = int(a.get("from") or nums[0])
            nums = [n for n in nums if n >= start]
            n = int(a.get("count", 1) or 1)
            q["default"] = str(nums[min(n, len(nums)) - 1])
        else:
            q["default"] = str(a.get("no") or nums[0])
        q["options"] = [{"value": str(n), "label": f"حديث {n}"} for n in nums]

    # ── التصميم ──
    elif step == "design":      q["options"] = _opt(DESIGNS)
    elif step == "tint":        q["options"] = _opt(TINTS)
    elif step == "font":        q["options"] = _opt(FONTS)
    elif step == "ink":         q["options"] = _opt(INKS)
    elif step == "translator":
        q["options"] = [{"value": "none", "label": "بلا ترجمة"}] + _sources(db, "translation")
    return q

def next_question(answers, db, default_watermark=None):
    """السؤال التالي وحده — لا تُعرض الأسئلة جملةً واحدة."""
    a = sanitize(answers, db)
    seq = steps_for(a)
    for i, step in enumerate(seq):
        if a.get(step) not in (None, ""):
            continue
        q = question(step, a, db, default_watermark)
        q.update(index=i + 1, total=len(seq), back=seq[i - 1] if i else None)
        return q
    return None

def progress(answers, db):
    a = sanitize(answers, db); seq = steps_for(a)
    done = sum(1 for s in seq if a.get(s) not in (None, ""))
    return {"done": done, "total": len(seq), "steps": seq, "answers": a}

# ───────────────────────── من الإجابات إلى بطاقات ─────────────────────────

def selection(answers, db):
    """المواضع المختارة — سلسلةٌ بطاقةً لكل آيةٍ أو حديث."""
    a = sanitize(answers, db)
    k = a.get("source_kind")
    if k == "quran":
        if not a.get("surah"): return []
        s = surah_info(db, a["surah"])
        if not s: return []
        lo = int(a.get("from") or 1); hi = int(a.get("to") or lo)
        lo, hi = min(lo, hi), min(max(lo, hi), s["n"])
        return [{"kind": "quran", "ref": {"surah": s["number"], "ayah": i}} for i in range(lo, hi + 1)]
    if k == "hadith":
        if not (a.get("book") and a.get("chapter")): return []
        nums = [h["no"] for h in chapter_hadiths(db, a["book"], a["chapter"])]
        if not nums: return []
        lo = int(a.get("from") or a.get("no") or nums[0])
        hi = int(a.get("to") or lo)
        lo, hi = min(lo, hi), max(lo, hi)
        return [{"kind": "hadith", "ref": {"book": a["book"], "no": n}}
                for n in nums if lo <= n <= hi]
    return []

def style(answers):
    a = answers or {}
    return {"ratio": RATIO_OF.get(a.get("content_type"), "square"),
            # السند والعلامة المكرّرة: مفتاحان لا سؤالان — لا يزيدان طول الأسئلة
            "isnad": a.get("isnad") in (True, "1", "on", "نعم"),
            "tile": a.get("tile") or None,
            "skin": a.get("design", "parch"),
            "tint": a.get("tint", "auto"),
            "font": a.get("font", "auto"),
            "ink":  a.get("ink", "auto"),
            "watermark": a.get("watermark") or "",
            "platform": a.get("platform", "")}

def plan(answers, db=None):
    """الخطة من محرّك الفحص نفسه — فما يراه الوكيل هو ما يُصدَّر لاحقًا."""
    import api
    from falah import verify as V
    db = db or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "falah.db")
    a = sanitize(answers, db)
    c = _ro(db)
    cards, dropped = [], []
    want_tafsir = a.get("tafsir", "none") != "none"
    want_tr = (a.get("translation") or a.get("translator") or "none") != "none"
    try:
        for sel in selection(a, db):
            if sel["kind"] == "quran":
                it, ctx = api.quran_card(c, sel["ref"]["surah"], sel["ref"]["ayah"],
                                         None, want_tafsir, want_tr)
                tag = f"{sel['ref']['surah']}:{sel['ref']['ayah']}"
            else:
                it, ctx = api.hadith_card(c, sel["ref"]["book"], sel["ref"]["no"])
                tag = f"{sel['ref']['book']} {sel['ref']['no']}"
            if not it:
                dropped.append({"ref": tag, "why": "لا وجود له في المصادر المعتمدة"}); continue
            rep = V.run(it, ctx)
            if not rep["ok"]:
                dropped.append({"ref": tag, "why": "، ".join(rep["failed"])}); continue
            cards.append({"kind": sel["kind"], "ref": sel["ref"], "tag": tag,
                          "text": it["text"], "cells": it["cells"],
                          "checks": f"{rep['passed']}/{rep['total']}",
                          "card": it})
    finally:
        c.close()
    title = _title(a, db)
    return {"title": title, "style": style(a), "cards": cards, "dropped": dropped,
            "count": len(cards),
            "caption": _caption(title, cards, a)}

def _title(a, db):
    if a.get("source_kind") == "quran" and a.get("surah"):
        s = surah_info(db, a["surah"])
        nm = s["name_ar"] if s["name_ar"].startswith("سُورَة") else "سورة " + s["name_ar"]
        import api as _api
        lo = a.get("from") or 1; hi = a.get("to") or lo
        return (f"{nm} {_api.arabic_num(lo)}" if str(lo) == str(hi)
                else f"{nm} {_api.arabic_num(lo)}–{_api.arabic_num(hi)}")
    if a.get("source_kind") == "hadith" and a.get("book"):
        b = next((x["name_ar"] for x in books(db) if x["code"] == a["book"]), a["book"])
        ch = next((x["name_ar"] for x in chapters(db, a["book"])
                   if str(x["chapter_id"]) == str(a.get("chapter"))), "")
        return f"{b} — {ch}" if ch else b
    return "بطاقة فلاح"

def _caption(title, cards, a):
    import api as _api
    n = _api.arabic_num(len(cards))
    who = a.get("watermark") or "—"
    ct = dict((v, l) for v, l, _ in CONTENT_TYPES).get(a.get("content_type"), "—")
    pf = dict(PLATFORMS).get(a.get("platform"), "—")
    ratio = RATIO_AR.get(RATIO_OF.get(a.get("content_type"), "square"), "")
    return (f"{title}\n{n} بطاقة، كلٌّ منها اجتاز فحوص المصدر قبل عرضه.\n"
            f"العلامة: {who} · فلاح\n"
            f"المنصّة: {pf} · {ct} · {ratio}")
