"""بناءُ البطاقات — طبقةُ نطاقٍ لا طبقةَ HTTP.

هنا يُقرأ النصّ من قاعدة المحتوى ويُبنى منه شيئان: **البطاقة** كما تُعرض،
و**سياقُها** (`ctx`) الذي يُسلَّم إلى `falah/verify.py` ليحكم عليه.

ولماذا نُقلت من `api.py`؟ لأن `falah/projects.py` و`falah/agent.py`
و`render.py` كانت تستورد `api` — أي أن طبقةَ النطاق تعتمد على طبقةِ
الويب، وهو عكسُ الاتّجاه الصحيح. صارت هنا، فالاعتمادُ ينزل: HTTP →
تطبيقٌ → نطاقٌ → بنيةٌ تحتية، ولا يصعد.

ولم يتغيّر في المنطق حرف: النصوصُ والفحوصُ والأحكامُ كما كانت. و`api.py`
يعيد تصديرَ هذه الأسماء، فكلُّ نداءٍ قائمٍ (`api.quran_card` وأخواته) يبقى
عاملًا كما هو — بما فيه ما في حزم الاختبار.
"""
import json, os, sqlite3, unicodedata

from falah.text import search_variants, searchable
from falah.matn import matn_sane

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERE, "falah.db")

def conn():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c

GRADE_EN = {"صحيح":"Sahih","حسن":"Hasan","حسن صحيح":"Hasan Sahih","صحيح لغيره":"Sahih li-ghayrihi",
            "حسن لغيره":"Hasan li-ghayrihi","إسناده صحيح":"Sound chain","إسناده حسن":"Good chain",
            "ضعيف":"Da'if","منكر":"Munkar","موضوع":"Fabricated","شاذ":"Shadh"}

def backoff(c, sql, term, limit):
    """يجرّب صيغ البحث بالترتيب ويتوقف عند أول نتيجة — بحث عربي بلا معجم."""
    for q in search_variants(term):
        rows = c.execute(sql, (q, limit)).fetchall()
        if rows: return [dict(r) for r in rows]
    return []

AR = "٠١٢٣٤٥٦٧٨٩"
def arabic_num(n): return "".join(AR[int(d)] for d in str(n))

# ───────────────────────── بناء البطاقة ─────────────────────────
def quran_card(c, surah, ayah, to=None, tafsir=False, translation=False, topic=None):
    to = to or ayah
    rows = c.execute("SELECT * FROM ayat WHERE surah=? AND ayah BETWEEN ? AND ? ORDER BY ayah",
                     (surah, ayah, to)).fetchall()
    if not rows: return None, None
    s   = c.execute("SELECT * FROM surahs WHERE number=?", (surah,)).fetchone()
    src = c.execute("SELECT * FROM sources WHERE id=?", (rows[0]["source_id"],)).fetchone()
    pages = sorted({r["page"] for r in rows})
    text  = " ۝ ".join(r["text"] for r in rows)

    page_ar = ("صفحة " + arabic_num(pages[0])) if len(pages) == 1 else \
              ("صفحات %s–%s" % (arabic_num(pages[0]), arabic_num(pages[-1])))
    page_en = ("Page %d" % pages[0]) if len(pages) == 1 else ("Pages %d–%d" % (pages[0], pages[-1]))
    v_ar = ("الآية " + arabic_num(ayah)) if ayah == to else \
           ("الآيات %s – %s" % (arabic_num(ayah), arabic_num(to)))
    v_en = ("Verse %d" % ayah) if ayah == to else ("Verses %d–%d" % (ayah, to))

    item = {"type": "quran", "text": text,
            "cells": {"c1": [s["name_ar"], s["name_en"]],
                      "c2": [s["revelation_ar"], s["revelation_en"]],
                      "c3": [page_ar, page_en], "c4": [v_ar, v_en]},
            "locus": {"surah": surah, "from": ayah, "to": to, "page": pages, "juz": rows[0]["juz"]},
            "verification": {"second_source": "Quran.com API v4",
                             "status": [r["verify_status"] for r in rows],
                             "basmala_stripped": any(r["basmala_stripped"] for r in rows)},
            "provenance": {"source": src["name"], "edition": src["edition"],
                           "riwayah": src["riwayah"], "origin": src["origin"],
                           "license": src["license_status"]}}
    if tafsir:
        t = c.execute("""SELECT t.text, s.name FROM ayah_tafsir t JOIN sources s ON s.id=t.source_id
                         WHERE t.surah=? AND t.ayah BETWEEN ? AND ? ORDER BY t.ayah""",
                      (surah, ayah, to)).fetchall()
        # آيتان قد تشتركان في نصّ تفسير واحد — لا يُكرَّر
        if t:
            seen, parts = set(), []
            for r in t:
                if r["text"] not in seen: seen.add(r["text"]); parts.append(r["text"])
            item["tafsir"] = {"text": " ".join(parts), "source": t[0]["name"]}
    if translation:
        t = c.execute("""SELECT t.text, s.name FROM ayah_translation t
                         JOIN sources s ON s.id=t.source_id
                         WHERE t.surah=? AND t.ayah BETWEEN ? AND ? ORDER BY t.ayah""",
                      (surah, ayah, to)).fetchall()
        if t:
            seen, parts = set(), []
            for r in t:
                if r["text"] not in seen: seen.add(r["text"]); parts.append(r["text"])
            item["translation"] = {"text": " ".join(parts), "source": t[0]["name"]}

    # سياق ما قبل وما بعد
    prev_ = c.execute("SELECT text FROM ayat WHERE surah=? AND ayah=?", (surah, ayah-1)).fetchone()
    next_ = c.execute("SELECT text FROM ayat WHERE surah=? AND ayah=?", (surah, to+1)).fetchone()
    # السورة كاملةً سياقُها تامٌّ بنفسها: لا آية قبل أولاها ولا بعد آخرتها،
    # وليس ذلك اقتطاعًا. فالشرط أن يُتاح السياق، وهو هنا متاحٌ كلُّه.
    _last = c.execute("SELECT MAX(ayah) FROM ayat WHERE surah=?", (surah,)).fetchone()[0]
    whole_surah = (ayah == 1 and to == _last)
    item["context"] = {"before": prev_["text"] if prev_ else None,
                       "after":  next_["text"] if next_ else None}

    # مواضع المتشابه اللفظي
    others = []
    for r in rows:
        if r["mutashabih_group"]:
            for o in c.execute("""SELECT surah,ayah FROM ayat WHERE mutashabih_group=? AND id<>?""",
                               (r["mutashabih_group"], r["id"])):
                others.append(f"{o['surah']}:{o['ayah']}")
    if others: item["mutashabih"] = others

    ctx = {
        "source_registered": bool(src["enabled"]), "source_name": src["name"],
        "fp_pairs": [(r["text"], r["fingerprint"]) for r in rows],
        "edition": src["edition"], "origin": src["origin"],
        "license_status": src["license_status"], "riwayah": src["riwayah"],
        "corroboration": 2 if all(r["verify_status"] in ("exact","orthographic") for r in rows) else 1,
        "exact_match": True,
        "cross_match": all(r["verify_status"] in ("exact","orthographic") for r in rows),
        "cross_note": " · ".join(sorted({r["verify_status"] for r in rows})),
        "script_ok": True, "script_note": "الرسم العثماني",
        "locus_ok": True, "locus": f"{s['name_ar']} {ayah}–{to}",
        # `zip` وحدها تقتطع عند الأقصر: لو نقصت آيةٌ من المدى لَمرّ الفحص
        # على ما بقي وقال «متسلسل». العدد يُقارن أوّلًا ثم يُقارن كلُّ رقم.
        "numbering_ok": (len(rows) == to - ayah + 1 and
                         all(r["ayah"] == n for r, n in
                             zip(rows, range(ayah, to+1), strict=True))),
        "numbering": "متسلسل",
        "grade_ok": True, "grade_note": src["riwayah"],
        "takhrij_ok": True, "takhrij_note": "موضع مفهرس بالصفحة والجزء",
        "complete": True, "complete_note": "آيات كاملة",
        "context_ok": bool(prev_ or next_ or whole_surah),
        "context_note": "السورة كاملة" if whole_surah else "متاح",
        "mutashabih_unresolved": bool(others),
        "mutashabih_disclosed": bool(others),   # المواضع الأخرى مذكورة في البطاقة نفسها
        "mutashabih_note": ("يتكرر في: " + "، ".join(others)) if others else "لا التباس",
        "topic_ok": (searchable(topic) in searchable(text)) if topic else True,
        "topic_note": topic or "لم يُحدَّد",
        "source_lock": True, "max_len": 260,
        "slides": max(1, -(-len(text) // 260)),   # كم شريحةً يلزم النصّ
        "split_ok": True,                          # التقسيم بحدود الكلمات لا بالقصّ
        "normalization_safe": searchable(text) == searchable(unicodedata.normalize("NFC", text)),
        "normalization_note": "التطبيع لا يمسّ الرسم",
    }
    return item, ctx

def hadith_card(c, book, no, topic=None):
    r = c.execute("""SELECT h.*, b.name_ar bn, b.name_en bne, b.code bcode
                     FROM hadiths h JOIN books b ON b.id=h.book_id
                     WHERE b.code=? AND h.number_in_book=?""", (book, no)).fetchone()
    if not r: return None, None
    ch  = c.execute("SELECT name_ar,name_en FROM chapters WHERE book_id=? AND chapter_id=?",
                    (r["book_id"], r["chapter_id"])).fetchone()
    src = c.execute("SELECT * FROM sources WHERE id=?", (r["source_id"],)).fetchone()
    tk  = c.execute("""SELECT b.name_ar, t.number_in_book FROM takhrij t
                       JOIN books b ON b.id=t.book_id WHERE t.group_key=?""",
                    (r["core_key"] or "",)).fetchall()
    takhrij = [f"{x['name_ar']} {arabic_num(x['number_in_book'])}" for x in tk]

    item = {"type": "hadith", "text": r["matn"] or r["full_ar"],
            "cells": {"c1": [r["bn"], r["bne"]],
                      "c2": [ch["name_ar"] if ch else "", ch["name_en"] if ch else ""],
                      "c3": ["رقم " + arabic_num(r["number_in_book"]), "No. %d" % r["number_in_book"]],
                      "c4": [r["grade"] or "الدرجة غير مسجّلة",
                             GRADE_EN.get(r["grade"], "grade not on file")]},
            "narrator": r["narrator_ar"], "narrator_en": r["narrator_en"],
            "grade": r["grade"], "grade_basis": r["grade_basis"],
            "grade_by": r["grade_by"], "grade_raw": r["grade_raw"],
            "grade_all": json.loads(r["grade_all"]) if r["grade_all"] else None,
            "verification": {"second_source": "hadith-api (Sunnah.com)",
                             "status": r["verify_status"]},
            "takhrij": takhrij, "isnad_full": r["full_ar"],
            "jami": ({"book": "الجامع الكامل في الحديث الصحيح الشامل",
                      "author": "ضياء الرحمن الأعظمي",
                      "volume": r["jami_vol"],
                      "chapter": r["jami_book"], "bab": r["jami_bab"],
                      "grade_in_book": r["jami_grade"],
                      "takhrij_in_book": r["jami_takhrij"],
                      "conflict": r["jami_conflict"],
                      "match": f"{r['jami_hits']} مقاطع متطابقة",
                      "role": "شاهدٌ وملحقات — لا مصدرٌ لنصّ الحديث",
                      "note": "الحكم والتخريج مقروءان من نافذة النصّ الممسوح آليًا"}
                     if r["jami_vol"] else None),
            "matn_method": r["matn_method"], "matn_confidence": r["matn_conf"],
            "provenance": {"source": src["name"], "edition": src["edition"],
                           "origin": src["origin"], "license": src["license_status"]}}
    if r["text_en"]:
        item["translation"] = {"text": r["text_en"], "source": "الترجمة الإنجليزية — Sunnah.com"}

    # شرح الحديث من الموسوعة الحديثية حين يكون متنُها مطابقًا لمتنِه
    sh = c.execute("""SELECT e.explanation, e.hints, s2.name FROM enc_link l
                      JOIN enc e ON e.id=l.enc_id JOIN sources s2 ON s2.id=e.source_id
                      WHERE l.hadith_id=? AND e.explanation IS NOT NULL LIMIT 1""",
                   (r["id"],)).fetchone()
    if sh:
        item["sharh"] = {"text": sh["explanation"], "source": sh["name"]}
        try:
            hints = json.loads(sh["hints"] or "[]")
            if hints: item["hints"] = hints
        except Exception:
            pass

    ctx = {
        "source_registered": bool(src["enabled"]), "source_name": src["name"],
        "fp_pairs": [(r["full_ar"], r["fingerprint"])],
        "edition": src["edition"], "origin": src["origin"],
        "license_status": src["license_status"], "riwayah": r["bn"],
        "corroboration": (max(len(tk), 2 if r["verify_status"] == "confirmed" else 1)
                          + (1 if r["jami_vol"] else 0)),
        "exact_match": True,
        "cross_match": r["verify_status"] == "confirmed",
        "cross_note": ("تأكّد من مصدر ثانٍ" if r["verify_status"] == "confirmed"
                       else "مصدر واحد فقط"),
        "script_ok": bool(r["matn"]), "script_note": r["matn_method"],
        "locus_ok": True, "locus": f"{r['bn']} — {ch['name_ar'] if ch else ''}",
        "numbering_ok": True, "numbering": "رقم %d" % r["number_in_book"],
        # الحكم يُقيَّم وحده: طول المتن أو فصله لهما فحوصهما الخاصة
        # التعارض بين حكمين يُسقط فحص الحكم، كما يُسقطه انعدامه أو ضعفه
        "grade_ok": bool(r["grade"]) and not (r["block_reason"] or "").startswith(
                        ("الحكم", "لا حكم", "تعارض")),
        "grade_note": r["grade_basis"] or "لا مصدر معتمد للدرجة — محجوب",
        "takhrij_ok": bool(takhrij) or r["verify_status"] == "confirmed",
        "takhrij_note": ("، ".join(takhrij) or "الكتاب ورقمه مثبتان")
                        + (" · الجامع الكامل مج%d %s" % (r["jami_vol"], r["jami_book"] or "")
                           if r["jami_vol"] else ""),
        # يجب أن يوافق هذا قاعدةَ الإفراج في البناء، وإلا صدّر المحرّك
        # بطاقةً حجبتها القاعدة. الشرط: فصلٌ مؤكّد بعلامة الطبعة + حارس سليم.
        "complete": ((r["matn_conf"] or 0) >= 0.95 and bool(r["matn"])
                     and matn_sane(r["matn"])[0]),
        "complete_note": r["block_reason"] or r["matn_method"],
        "context_ok": True, "context_note": "السند الكامل محفوظ مع البطاقة",
        "mutashabih_unresolved": False, "mutashabih_note": "لا ينطبق",
        "topic_ok": (searchable(topic) in searchable(r["matn"] or "")) if topic else True,
        "topic_note": topic or "لم يُحدَّد",
        "source_lock": True, "max_len": 320,   # نفس حدّ is_card_ready
        "normalization_safe": searchable(item["text"]) == searchable(unicodedata.normalize("NFC", item["text"])),
        "normalization_note": "التطبيع لا يمسّ الضبط",
    }
    return item, ctx

def enc_card(c, eid, lang=None, topic=None):
    r = c.execute("SELECT * FROM enc WHERE id=?", (eid,)).fetchone()
    if not r: return None, None
    src = c.execute("SELECT * FROM sources WHERE id=?", (r["source_id"],)).fetchone()
    links = c.execute("""SELECT b.name_ar, h.number_in_book FROM enc_link l
                         JOIN hadiths h ON h.id=l.hadith_id JOIN books b ON b.id=h.book_id
                         WHERE l.enc_id=?""", (eid,)).fetchall()
    trs = {t["lang"]: dict(t) for t in c.execute("SELECT * FROM enc_tr WHERE enc_id=?", (eid,))}
    hints = json.loads(r["hints"] or "[]")
    item = {"type": "hadith", "source_kind": "enc", "text": r["matn"],
            "cells": {"c1": ["الموسوعة الحديثية", "Hadeeth Encyclopedia"],
                      "c2": [r["attribution"] or "", trs.get("en",{}).get("title","")[:40]],
                      "c3": ["رقم " + arabic_num(r["id"]), "No. %d" % r["id"]],
                      "c4": [r["grade"] or "الدرجة غير مسجّلة", GRADE_EN.get(r["grade"], "")]},
            "title": r["title"], "intro": r["intro"],
            "grade": r["grade"], "grade_basis": "حكم الموسوعة الحديثية",
            "grade_by": "الموسوعة الحديثية", "narrator": None,
            "takhrij": [f"{x['name_ar']} {arabic_num(x['number_in_book'])}" for x in links] or
                       ([r["attribution"]] if r["attribution"] else []),
            "reference": r["reference"],
            "sharh": {"text": r["explanation"], "source": src["name"]} if r["explanation"] else None,
            "hints": hints,
            "words": json.loads(r["words"] or "[]"),
            "translations": {k: {"title": v["title"], "text": v["matn"],
                                 "explanation": v["explanation"]} for k, v in trs.items()},
            "verification": {"second_source": "الكتب التسعة", 
                             "status": "confirmed" if links else "single-source"},
            "provenance": {"source": src["name"], "edition": src["edition"],
                           "origin": src["origin"], "license": src["license_status"]}}
    if trs.get("en"): item["translation"] = {"text": trs["en"]["matn"], "source": "HadeethEnc — English"}
    ctx = {
        "source_registered": True, "source_name": src["name"],
        "fp_pairs": [(r["matn"], r["matn_fp"])],
        "edition": src["edition"], "origin": src["origin"],
        "license_status": src["license_status"], "riwayah": r["attribution"] or "—",
        "corroboration": 2 if links else 1,
        "exact_match": True, "cross_match": bool(links),
        "cross_note": ("مطابق في %d من الكتب التسعة" % len(links)) if links else "الموسوعة وحدها",
        "script_ok": True, "script_note": "متن منقّح من الناشر",
        "locus_ok": True, "locus": r["attribution"] or "",
        "numbering_ok": True, "numbering": "رقم %d" % r["id"],
        "grade_ok": bool(r["grade"]) and r["card_ok"] == 1, "grade_note": "حكم الموسوعة: " + (r["grade"] or "—"),
        "takhrij_ok": bool(r["attribution"]), "takhrij_note": r["attribution"] or "",
        "complete": True, "complete_note": "متن مستقل لا يحتاج فصلًا عن سند",
        "context_ok": bool(r["intro"] or r["reference"]), "context_note": "المقدمة والمرجع محفوظان",
        "mutashabih_unresolved": False, "mutashabih_note": "لا ينطبق",
        "topic_ok": (searchable(topic) in searchable(r["matn"])) if topic else True,
        "topic_note": topic or "لم يُحدَّد",
        "source_lock": True, "max_len": 400,
        "normalization_safe": True, "normalization_note": "متن منشور",
    }
    return item, ctx
