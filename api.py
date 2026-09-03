#!/usr/bin/env python3
"""FALAH — خادم المحتوى. مكتبة قياسية فقط.

    python3 api.py          →  http://localhost:8080/health

المسارات
  GET /health                                          حالة الخدمة والأعداد
  GET /sources                                         سجل المصادر وحالة تراخيصها
  GET /topics                                          فهرس الموضوعات (لسؤال الوكيل)
  GET /topics/{id}?kind=quran|hadith&limit=20          مقترحات جاهزة للبطاقة
  GET /quran/search?q=&limit=                          بحث بلا تشكيل
  GET /quran/ayah?surah=&ayah=&to=                     الآية بمرجعها
  GET /hadith/search?q=&limit=&card_only=1
  GET /hadith?book=bukhari&no=1                        الحديث بمتنه وتخريجه
  GET /card?kind=quran&surah=94&ayah=5&to=6&tafsir=1&translation=1
  GET /card?kind=hadith&book=bukhari&no=1              ← البطاقة بعد ٢٥ فحصًا
  GET /card?…&require_jami=1                           تشديد: لا يخرج إلا ما شهد له الأعظمي
  GET /reciters                                        القرّاء مرتَّبين بالروايات
  GET /audio?surah=&ayah=[&reciter=]                   روابط التلاوة لكل قارئ
  GET /enc/search?q=&card_only=1                       بحث في الموسوعة
  GET /enc?id=                                         حديث بشرحه وفوائده وترجماته
  GET /card?kind=enc&id=                               بطاقة من الموسوعة بعد الفحص
  GET /verify?text=[&surah=&ayah=]                     فحص البصمة وحده
  GET /review?kind=quran|hadith&limit=                 كل ما حُجب ولماذا
"""
import sqlite3, json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unicodedata
from falah.text import fingerprint, search_variants, searchable
from falah import verify as V
from falah.audio import audio_url
from falah.matn import matn_sane

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "falah.db")

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

# ───────────────────────── الخادم ─────────────────────────
class H(BaseHTTPRequestHandler):
    server_version = "FALAH/1.0"
    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

    def do_GET(self):
        u = urlparse(self.path); qs = parse_qs(u.query)
        g = lambda k, d=None: qs.get(k, [d])[0]
        gi = lambda k, d=None: int(g(k)) if g(k) else d
        c = conn()
        try:
            p = u.path.rstrip("/") or "/"
            if p == "/health":
                one = lambda s: c.execute(s).fetchone()[0]
                self._send({"ok": True, "db": os.path.basename(DB),
                    "ayat": one("SELECT COUNT(*) FROM ayat"),
                    "ayat_card_ready": one("SELECT COUNT(*) FROM ayat WHERE card_ok=1"),
                    "hadiths": one("SELECT COUNT(*) FROM hadiths"),
                    "hadiths_card_ready": one("SELECT COUNT(*) FROM hadiths WHERE card_ok=1"),
                    "takhrij_groups": one("SELECT COUNT(DISTINCT group_key) FROM takhrij"),
                    "jami_witnessed": one("SELECT COUNT(*) FROM hadiths WHERE jami_vol IS NOT NULL"),
                    "jami_and_card_ready": one("SELECT COUNT(*) FROM hadiths WHERE jami_vol IS NOT NULL AND card_ok=1"),
                    "topics": one("SELECT COUNT(*) FROM topics"),
                    "reciters": one("SELECT COUNT(*) FROM reciters"),
                    "enc": one("SELECT COUNT(*) FROM enc"),
                    "enc_card_ready": one("SELECT COUNT(*) FROM enc WHERE card_ok=1"),
                    "sources": one("SELECT COUNT(*) FROM sources")})

            elif p == "/review":
                kind = g("kind"); lim = gi("limit", 50)
                # استعلامان مكتوبان لا واحدٌ يُركَّب: المركَّب هنا لم يكن
                # قابلًا للحقن (الجزءُ المدمَج ثابت)، لكن النمط يُغري بأن
                # يُدمَج فيه يومًا ما ليس ثابتًا. يُزال النمط لا الخطر وحده.
                rows = (c.execute("SELECT * FROM review_queue WHERE kind=? LIMIT ?",
                                  (kind, lim)) if kind else
                        c.execute("SELECT * FROM review_queue LIMIT ?", (lim,))).fetchall()
                tot = c.execute("SELECT reason, COUNT(*) n FROM review_queue"
                                " GROUP BY reason ORDER BY n DESC").fetchall()
                self._send({"summary": [dict(r) for r in tot],
                            "items": [dict(r) for r in rows]})

            elif p == "/reciters":
                rows = c.execute("SELECT * FROM reciters ORDER BY riwayah, name").fetchall()
                by = {}
                for r in rows: by.setdefault(r["riwayah"], []).append(
                    {"code": r["code"], "name": r["name"]})
                self._send({"count": len(rows), "riwayat": by})

            elif p == "/audio":
                s_, a_ = gi("surah"), gi("ayah")
                row = c.execute("SELECT id FROM ayat WHERE surah=? AND ayah=?", (s_, a_)).fetchone()
                if not row: return self._send({"error":"الآية غير موجودة"}, 404)
                only = g("reciter")
                out = []
                for r in c.execute("SELECT * FROM reciters" + (" WHERE code=?" if only else ""),
                                   (only,) if only else ()):
                    out.append({"reciter": r["name"], "code": r["code"], "riwayah": r["riwayah"],
                                "url": audio_url(r["scheme"], r["folder"], s_, a_, row["id"])})
                self._send({"surah": s_, "ayah": a_, "recitations": out})

            elif p == "/enc/search":
                sql = """SELECT e.id, e.title, e.grade, e.attribution, e.card_ok,
                                substr(e.matn,1,180) matn
                         FROM enc_fts f JOIN enc e ON e.id=f.rowid
                         WHERE enc_fts MATCH ? %s LIMIT ?""" % (
                         "AND e.card_ok=1" if g("card_only")=="1" else "")
                self._send(backoff(c, sql, g("q",""), gi("limit",10)))

            elif p == "/enc":
                it, _ = enc_card(c, gi("id"))
                self._send(it or {"error":"غير موجود"}, 200 if it else 404)

            elif p == "/sources":
                self._send([dict(r) for r in c.execute("SELECT * FROM sources ORDER BY kind")])

            elif p == "/topics":
                self._send([{**dict(r),
                    "quran": c.execute("SELECT COUNT(*) FROM topic_items WHERE topic_id=? AND kind='quran'",(r["id"],)).fetchone()[0],
                    "hadith": c.execute("SELECT COUNT(*) FROM topic_items WHERE topic_id=? AND kind='hadith'",(r["id"],)).fetchone()[0]}
                    for r in c.execute("SELECT * FROM topics ORDER BY id")])

            elif p.startswith("/topics/"):
                tid = int(p.split("/")[2]); kind = g("kind","quran"); lim = gi("limit",20)
                if kind == "quran":
                    rows = c.execute("""SELECT a.surah,a.ayah,a.text,a.page,s.name_ar
                        FROM topic_items ti JOIN ayat a ON a.id=ti.ref_id
                        JOIN surahs s ON s.number=a.surah
                        WHERE ti.topic_id=? AND ti.kind='quran' LIMIT ?""",(tid,lim))
                else:
                    rows = c.execute("""SELECT b.code,b.name_ar,h.number_in_book,h.matn,h.narrator_ar
                        FROM topic_items ti JOIN hadiths h ON h.id=ti.ref_id
                        JOIN books b ON b.id=h.book_id
                        WHERE ti.topic_id=? AND ti.kind='hadith' LIMIT ?""",(tid,lim))
                self._send([dict(r) for r in rows])

            elif p == "/quran/search":
                sql = """SELECT a.surah,a.ayah,a.text,a.page,a.card_ok,s.name_ar
                         FROM ayat_fts f JOIN ayat a ON a.id=f.rowid
                         JOIN surahs s ON s.number=a.surah
                         WHERE ayat_fts MATCH ? %s LIMIT ?""" % (
                         "AND a.card_ok=1" if g("card_only")=="1" else "")
                self._send(backoff(c, sql, g("q",""), gi("limit",10)))

            elif p == "/hadith/search":
                sql = """SELECT b.code,b.name_ar,h.number_in_book,h.narrator_ar,h.grade,h.card_ok,
                                substr(h.matn,1,180) matn
                         FROM hadith_fts f JOIN hadiths h ON h.id=f.rowid
                         JOIN books b ON b.id=h.book_id
                         WHERE hadith_fts MATCH ? %s LIMIT ?""" % (
                         "AND h.card_ok=1" if g("card_only")=="1" else "")
                self._send(backoff(c, sql, g("q",""), gi("limit",10)))

            elif p == "/quran/ayah":
                it,_ = quran_card(c, gi("surah"), gi("ayah"), gi("to"),
                                  g("tafsir")=="1", g("translation")=="1")
                self._send(it or {"error":"غير موجود"}, 200 if it else 404)

            elif p == "/hadith":
                it,_ = hadith_card(c, g("book"), gi("no"))
                self._send(it or {"error":"غير موجود"}, 200 if it else 404)

            elif p == "/card":
                kind = g("kind","quran")
                if kind == "quran":
                    it, ctx = quran_card(c, gi("surah"), gi("ayah"), gi("to"),
                                         g("tafsir")=="1", g("translation")=="1", g("topic"))
                elif kind == "enc":
                    it, ctx = enc_card(c, gi("id"), g("lang"), g("topic"))
                else:
                    it, ctx = hadith_card(c, g("book"), gi("no"), g("topic"))
                if not it: return self._send({"error":"غير موجود"},404)
                report = V.run(it, ctx)
                # وضع التشديد: لا يُفرَج إلا عمّا شهد له «الجامع الكامل»
                if g("require_jami") == "1" and kind == "hadith" and not it.get("jami"):
                    report["ok"] = False
                    report["failed"] = report["failed"] + ["لم يرد في الجامع الكامل"]
                self._send({"released": report["ok"], "card": it if report["ok"] else None,
                            "verification": report,
                            "blocked_because": report["failed"] or None},
                           200 if report["ok"] else 409)

            elif p == "/options":
                # كل ما تحتاجه حقول الأسئلة: سور وأبواب وأرقام وتفاسير وتراجم وقرّاء وتصاميم
                what = g("what", "all")
                out = {}
                if what in ("all", "content"):
                    out["content_types"] = [
                        {"value": "long_video",  "label": "فيديو طويل",  "ratio": "wide"},
                        {"value": "short_video", "label": "فيديو قصير",  "ratio": "vertical"},
                        {"value": "image",       "label": "صورة",        "ratio": "square"},
                        {"value": "story",       "label": "قصة",         "ratio": "vertical"},
                        {"value": "post",        "label": "منشور",       "ratio": "square"}]
                    out["platforms"] = [
                        {"value": "youtube",   "label": "يوتيوب"},
                        {"value": "facebook",  "label": "فيسبوك"},
                        {"value": "instagram", "label": "إنستقرام"},
                        {"value": "tiktok",    "label": "تيك توك"},
                        {"value": "x",         "label": "إكس"},
                        {"value": "telegram",  "label": "تيليجرام"},
                        {"value": "messenger", "label": "ماسنجر"},
                        {"value": "whatsapp",  "label": "واتساب"}]
                if what in ("all", "quran"):
                    out["surahs"] = [{"value": r["number"], "label": r["name_ar"],
                                      "label_en": r["name_en"], "ayat": r["ayah_count"],
                                      "revelation": r["revelation_ar"]}
                                     for r in c.execute(
                        """SELECT s.number, s.name_ar, s.name_en, s.revelation_ar,
                                  (SELECT COUNT(*) FROM ayat a WHERE a.surah=s.number) ayah_count
                           FROM surahs s ORDER BY s.number""")]
                    out["tafsirs"] = [{"value": r["code"], "label": r["name"]} for r in c.execute(
                        "SELECT code, name FROM sources WHERE kind='tafsir' AND enabled=1")]
                    out["translations"] = [{"value": r["code"], "label": r["name"]} for r in c.execute(
                        "SELECT code, name FROM sources WHERE kind='translation' AND enabled=1")]
                    out["reciters"] = [{"value": r["code"], "label": r["name"],
                                        "riwayah": r["riwayah"]} for r in c.execute(
                        "SELECT code, name, riwayah FROM reciters ORDER BY riwayah, name")]
                if what in ("all", "hadith"):
                    out["books"] = [{"value": r["code"], "label": r["name_ar"],
                                     "label_en": r["name_en"], "ready": r["n"]}
                                    for r in c.execute(
                        """SELECT b.code, b.name_ar, b.name_en,
                                  (SELECT COUNT(*) FROM hadiths h
                                    WHERE h.book_id=b.id AND h.card_ok=1) n
                           FROM books b ORDER BY b.id""") if r["n"]]
                if what in ("all", "design"):
                    out["designs"] = [{"value": k, "label": v} for k, v in
                                      (("parch","رقّ عتيق"),("night","ليلي مذهّب"),("ivory","نقي"))]
                    out["fonts"] = [{"value": "amiri", "label": "أميري"},
                                    {"value": "amiri-quran", "label": "أميري قرآن (للمصحف)"}]
                    out["ink_colors"] = [{"value": "auto", "label": "لون الهيئة (تلقائي)"},
                                         {"value": "#2B2116", "label": "بنّي داكن"},
                                         {"value": "#1E2A24", "label": "أخضر داكن"},
                                         {"value": "#111111", "label": "أسود"},
                                         {"value": "#F0E5CA", "label": "عاجي"}]
                self._send(out)

            elif p == "/chapters":
                # أبواب كتابٍ بعينه، ومعها أرقام الأحاديث المفحوصة في كل باب.
                # و«بلا بابٍ مسجَّل» بابٌ ظاهرٌ رقمه ‎-1 لِما لم يذكر المصدرُ بابَه،
                # فلا يُنسب حديثٌ إلى بابٍ لم يُذكر، ولا يُخفى عن الاختيار.
                bk = g("book", "")
                rows = c.execute("""
                    SELECT ch.chapter_id, ch.name_ar, ch.name_en,
                           (SELECT COUNT(*) FROM hadiths h WHERE h.book_id=b.id
                             AND h.chapter_id=ch.chapter_id AND h.card_ok=1) n
                    FROM chapters ch JOIN books b ON b.id=ch.book_id
                    WHERE b.code=? ORDER BY ch.chapter_id""", (bk,)).fetchall()
                out = [dict(r) for r in rows if r["n"]]
                orphan = c.execute("""SELECT COUNT(*) FROM hadiths h JOIN books b ON b.id=h.book_id
                    WHERE b.code=? AND h.card_ok=1 AND (h.chapter_id IS NULL
                      OR NOT EXISTS (SELECT 1 FROM chapters ch
                         WHERE ch.book_id=h.book_id AND ch.chapter_id=h.chapter_id))""",
                    (bk,)).fetchone()[0]
                if orphan:
                    out.append({"chapter_id": -1, "name_ar": "بلا بابٍ مسجَّل في المصدر",
                                "name_en": "No chapter recorded in source", "n": orphan})
                self._send({"book": bk, "chapters": out})

            elif p == "/chapter/hadiths":
                bk, ch = g("book", ""), gi("chapter", 0)
                if ch == -1:
                    rows = c.execute("""
                        SELECT h.number_in_book AS no, h.grade, substr(h.matn,1,120) matn
                        FROM hadiths h JOIN books b ON b.id=h.book_id
                        WHERE b.code=? AND h.card_ok=1 AND (h.chapter_id IS NULL
                          OR NOT EXISTS (SELECT 1 FROM chapters c2
                             WHERE c2.book_id=h.book_id AND c2.chapter_id=h.chapter_id))
                        ORDER BY h.number_in_book""", (bk,)).fetchall()
                else:
                    rows = c.execute("""
                        SELECT h.number_in_book AS no, h.grade, substr(h.matn,1,120) matn
                        FROM hadiths h JOIN books b ON b.id=h.book_id
                        WHERE b.code=? AND h.chapter_id=? AND h.card_ok=1
                        ORDER BY h.number_in_book""", (bk, ch)).fetchall()
                self._send({"book": bk, "chapter": ch, "hadiths": [dict(r) for r in rows]})

            elif p == "/templates":
                # تصفّح القوالب الجاهزة: مفلترةً بالنوع والموضوع والطول والملحقات
                kind = g("kind"); topic = g("topic"); q = g("q")
                where, args = ["1=1"], []
                if kind:  where.append("kind=?"); args.append(kind)
                if topic: where.append("(','||topics||',') LIKE ?"); args.append(f"%,{topic},%")
                if q:     where.append("(text LIKE ? OR title LIKE ?)"); args += [f"%{q}%"]*2
                if g("with_tafsir") == "1": where.append("has_tafsir=1")
                if g("with_translation") == "1": where.append("has_tr=1")
                lim = min(gi("limit", 20), 200); off = gi("offset", 0)
                sql = "FROM templates WHERE " + " AND ".join(where)
                total = c.execute("SELECT COUNT(*) " + sql, args).fetchone()[0]
                rows = c.execute("SELECT ref,kind,title,text,chars,checks,has_tafsir,has_tr,topics "
                                 + sql + " ORDER BY chars LIMIT ? OFFSET ?",
                                 args + [lim, off]).fetchall()
                self._send({"total": total, "limit": lim, "offset": off,
                            "templates": [dict(r) for r in rows]})

            elif p == "/template":
                r = c.execute("SELECT payload FROM templates WHERE ref=?", (g("ref"),)).fetchone()
                self._send(json.loads(r["payload"]) if r else {"error": "لا قالب بهذا المرجع"},
                           200 if r else 404)

            elif p == "/series":
                # خطة سلسلة بطاقات: ما اجتاز الفحص فقط، ومعه وصفٌ مبنيّ من القاعدة
                import carousel as CR
                try:
                    P = CR.plan(topic=gi("topic"), items=g("items"),
                                kind=g("kind","mixed"), count=gi("count",5),
                                title=g("title"), title_en=g("title_en",""))
                except SystemExit as e:
                    return self._send({"error": str(e)}, 404)
                total = len(P["cards"]) + 2
                slides = [{"slide":1,"role":"cover","title":P["title"],
                           "title_en":P["title_en"],"kicker":"سلسلة",
                           "lines":[f"{P['what']} — {arabic_num(len(P['cards']))} بطاقات",
                                    "كلُّ نصٍّ بسنده ودرجته"],
                           "badge":f"١ / {arabic_num(total)}"}]
                for i,(k,card,rep,tag) in enumerate(P["cards"], start=2):
                    slides.append({"slide":i,"role":"card","kind":k,"ref":CR.ref_line(card),
                                   "sanad":CR.sanad_line(card),
                                   "checks":f"{rep['passed']}/{rep['total']}",
                                   "badge":f"{arabic_num(i)} / {arabic_num(total)}",
                                   "card":card})
                slides.append({"slide":total,"role":"sources","heading":"المصادر",
                               "entries":P["sources_slide"],
                               "note":f"كل نصٍّ في هذه السلسلة اجتاز {arabic_num(P['checks'])} فحصًا قبل عرضه",
                               "badge":f"{arabic_num(total)} / {arabic_num(total)}"})
                self._send({"title":P["title"],"title_en":P["title_en"],
                            "slides":slides,"caption":P["caption"],"sources":P["sources"],
                            "dropped":[{"ref":a,"why":b} for a,b in P["dropped"]]})

            elif p == "/verify":
                text = g("text","")
                got = fingerprint(text)
                if gi("surah") and gi("ayah"):
                    r = c.execute("SELECT text,fingerprint FROM ayat WHERE surah=? AND ayah=?",
                                  (gi("surah"), gi("ayah"))).fetchone()
                    return self._send({"ok": bool(r) and r["fingerprint"]==got,
                                       "expected": r["fingerprint"] if r else None,
                                       "got": got, "source_text": r["text"] if r else None})
                r = c.execute("SELECT surah,ayah FROM ayat WHERE fingerprint=?",(got,)).fetchone()
                if r: return self._send({"ok":True,"matched":{"surah":r["surah"],"ayah":r["ayah"]}})
                r = c.execute("""SELECT b.code,h.number_in_book FROM hadiths h JOIN books b ON b.id=h.book_id
                                 WHERE h.fingerprint=? OR h.matn_fp=?""",(got,got)).fetchone()
                if r: return self._send({"ok":True,"matched":{"book":r["code"],"no":r["number_in_book"]}})
                self._send({"ok":False,"reason":"لا يطابق أي نص في المصادر المعتمدة","got":got})
            else:
                self._send({"error":"مسار غير معروف"},404)
        except (ValueError, TypeError):
            # رقمٌ غير رقم، أو حقلٌ ناقص — خطأ في الطلب لا في الخادم
            self._send({"error": "قيمةٌ غير صالحة في الطلب"}, 400)
        except Exception as e:
            # لا يُسرَّب أثر التنفيذ إلى الخارج؛ يُسجَّل عندنا ويُختصر عندهم
            print("ERR", type(e).__name__, e, flush=True)
            self._send({"error": "خطأ داخلي"}, 500)
        finally:
            c.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"FALAH content API → http://localhost:{port}/health", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
