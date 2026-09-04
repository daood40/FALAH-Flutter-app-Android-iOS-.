"""مساراتُ القراءة العامّة — جدولٌ ومعالِجاتٌ صغيرة.

كانت هذه ثلاثَمئةِ سطرٍ داخل `if/elif` واحدٍ في `api.H.do_GET`. والمشكلةُ
لم تكن الطولَ وحده، بل أن **الاختيار** و**العمل** كانا شيئًا واحدًا: لا
تعرف ما المساراتُ الموجودة إلا بقراءةِ منطقِ كلٍّ منها، ولا تختبر منطقَ
مسارٍ إلا بخادمٍ يعمل.

هنا انفصلا. `ROUTES` جدولٌ يُقرأ في نظرة، وكلُّ معالِجٍ دالّةٌ صافية:

    handler(c, q) → (الجسم، رمزُ الحالة)

لا `self`، ولا كتابةَ ترويسة، ولا معرفةَ بـHTTP. تُنادى في اختبارٍ باتّصالِ
قاعدةٍ وقاموسِ استعلامٍ فحسب.

**ولم يتغيّر حرفٌ في منطق أيّ مسار.** ما كان يُرجَع ٤٠٤ يُرجَع ٤٠٤، وما
كان نصُّه كذا فهو كذا. النقلُ نقلٌ لا إعادةُ كتابة.
"""
import json, os

from falah.audio import audio_url
from falah.cards import (DB, arabic_num, backoff, enc_card, hadith_card,
                         quran_card)
from falah.text import fingerprint

class Query:
    """قراءةُ حقول الاستعلام. `g` نصٌّ و`gi` عدد — كما كانتا في `do_GET`."""
    __slots__ = ("qs",)

    def __init__(self, qs):  self.qs = qs
    def g(self, k, d=None):  return self.qs.get(k, [d])[0]
    def gi(self, k, d=None):
        v = self.g(k)
        return int(v) if v else d

# ───────────────────────── المعالِجات ─────────────────────────

def health(c, q):
    one = lambda s: c.execute(s).fetchone()[0]           # noqa: E731
    return {"ok": True, "db": os.path.basename(DB),
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
            "sources": one("SELECT COUNT(*) FROM sources")}, 200

def review(c, q):
    kind = q.g("kind"); lim = q.gi("limit", 50)
    # استعلامان مكتوبان لا واحدٌ يُركَّب: المركَّب هنا لم يكن قابلًا للحقن
    # (الجزءُ المدمَج ثابت)، لكن النمط يُغري بأن يُدمَج فيه يومًا ما ليس
    # ثابتًا. يُزال النمط لا الخطر وحده.
    rows = (c.execute("SELECT * FROM review_queue WHERE kind=? LIMIT ?", (kind, lim))
            if kind else
            c.execute("SELECT * FROM review_queue LIMIT ?", (lim,))).fetchall()
    tot = c.execute("SELECT reason, COUNT(*) n FROM review_queue"
                    " GROUP BY reason ORDER BY n DESC").fetchall()
    return {"summary": [dict(r) for r in tot],
            "items": [dict(r) for r in rows]}, 200

def reciters(c, q):
    rows = c.execute("SELECT * FROM reciters ORDER BY riwayah, name").fetchall()
    by = {}
    for r in rows:
        by.setdefault(r["riwayah"], []).append({"code": r["code"], "name": r["name"]})
    return {"count": len(rows), "riwayat": by}, 200

def audio(c, q):
    s_, a_ = q.gi("surah"), q.gi("ayah")
    row = c.execute("SELECT id FROM ayat WHERE surah=? AND ayah=?", (s_, a_)).fetchone()
    if not row: return {"error": "الآية غير موجودة"}, 404
    only = q.g("reciter")
    out = []
    for r in c.execute("SELECT * FROM reciters" + (" WHERE code=?" if only else ""),
                       (only,) if only else ()):
        out.append({"reciter": r["name"], "code": r["code"], "riwayah": r["riwayah"],
                    "url": audio_url(r["scheme"], r["folder"], s_, a_, row["id"])})
    return {"surah": s_, "ayah": a_, "recitations": out}, 200

def enc_search(c, q):
    sql = """SELECT e.id, e.title, e.grade, e.attribution, e.card_ok,
                    substr(e.matn,1,180) matn
             FROM enc_fts f JOIN enc e ON e.id=f.rowid
             WHERE enc_fts MATCH ? %s LIMIT ?""" % (
             "AND e.card_ok=1" if q.g("card_only") == "1" else "")
    return backoff(c, sql, q.g("q", ""), q.gi("limit", 10)), 200

def enc(c, q):
    it, _ = enc_card(c, q.gi("id"))
    return (it or {"error": "غير موجود"}), (200 if it else 404)

def sources(c, q):
    return [dict(r) for r in c.execute("SELECT * FROM sources ORDER BY kind")], 200

def topics(c, q):
    return [{**dict(r),
             "quran": c.execute("SELECT COUNT(*) FROM topic_items WHERE topic_id=? AND kind='quran'", (r["id"],)).fetchone()[0],
             "hadith": c.execute("SELECT COUNT(*) FROM topic_items WHERE topic_id=? AND kind='hadith'", (r["id"],)).fetchone()[0]}
            for r in c.execute("SELECT * FROM topics ORDER BY id")], 200

def topic_items(c, q, tid):
    kind = q.g("kind", "quran"); lim = q.gi("limit", 20)
    if kind == "quran":
        rows = c.execute("""SELECT a.surah,a.ayah,a.text,a.page,s.name_ar
            FROM topic_items ti JOIN ayat a ON a.id=ti.ref_id
            JOIN surahs s ON s.number=a.surah
            WHERE ti.topic_id=? AND ti.kind='quran' LIMIT ?""", (tid, lim))
    else:
        rows = c.execute("""SELECT b.code,b.name_ar,h.number_in_book,h.matn,h.narrator_ar
            FROM topic_items ti JOIN hadiths h ON h.id=ti.ref_id
            JOIN books b ON b.id=h.book_id
            WHERE ti.topic_id=? AND ti.kind='hadith' LIMIT ?""", (tid, lim))
    return [dict(r) for r in rows], 200

def quran_search(c, q):
    sql = """SELECT a.surah,a.ayah,a.text,a.page,a.card_ok,s.name_ar
             FROM ayat_fts f JOIN ayat a ON a.id=f.rowid
             JOIN surahs s ON s.number=a.surah
             WHERE ayat_fts MATCH ? %s LIMIT ?""" % (
             "AND a.card_ok=1" if q.g("card_only") == "1" else "")
    return backoff(c, sql, q.g("q", ""), q.gi("limit", 10)), 200

def hadith_search(c, q):
    sql = """SELECT b.code,b.name_ar,h.number_in_book,h.narrator_ar,h.grade,h.card_ok,
                    substr(h.matn,1,180) matn
             FROM hadith_fts f JOIN hadiths h ON h.id=f.rowid
             JOIN books b ON b.id=h.book_id
             WHERE hadith_fts MATCH ? %s LIMIT ?""" % (
             "AND h.card_ok=1" if q.g("card_only") == "1" else "")
    return backoff(c, sql, q.g("q", ""), q.gi("limit", 10)), 200

def quran_ayah(c, q):
    it, _ = quran_card(c, q.gi("surah"), q.gi("ayah"), q.gi("to"),
                       q.g("tafsir") == "1", q.g("translation") == "1")
    return (it or {"error": "غير موجود"}), (200 if it else 404)

def hadith(c, q):
    it, _ = hadith_card(c, q.g("book"), q.gi("no"))
    return (it or {"error": "غير موجود"}), (200 if it else 404)

def card(c, q):
    """المسارُ الوحيد الذي يُفرِج أو يحجب. الحكمُ من `falah/verify.py` وحده."""
    from falah import verify as V
    kind = q.g("kind", "quran")
    if kind == "quran":
        it, ctx = quran_card(c, q.gi("surah"), q.gi("ayah"), q.gi("to"),
                             q.g("tafsir") == "1", q.g("translation") == "1", q.g("topic"))
    elif kind == "enc":
        it, ctx = enc_card(c, q.gi("id"), q.g("lang"), q.g("topic"))
    else:
        it, ctx = hadith_card(c, q.g("book"), q.gi("no"), q.g("topic"))
    if not it: return {"error": "غير موجود"}, 404
    report = V.run(it, ctx)
    # وضع التشديد: لا يُفرَج إلا عمّا شهد له «الجامع الكامل»
    if q.g("require_jami") == "1" and kind == "hadith" and not it.get("jami"):
        report["ok"] = False
        report["failed"] = report["failed"] + ["لم يرد في الجامع الكامل"]
    return ({"released": report["ok"], "card": it if report["ok"] else None,
             "verification": report,
             "blocked_because": report["failed"] or None},
            200 if report["ok"] else 409)

def options(c, q):
    # كل ما تحتاجه حقول الأسئلة: سور وأبواب وأرقام وتفاسير وتراجم وقرّاء وتصاميم
    what = q.g("what", "all")
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
                          (("parch", "رقّ عتيق"), ("night", "ليلي مذهّب"), ("ivory", "نقي"))]
        out["fonts"] = [{"value": "amiri", "label": "أميري"},
                        {"value": "amiri-quran", "label": "أميري قرآن (للمصحف)"}]
        out["ink_colors"] = [{"value": "auto", "label": "لون الهيئة (تلقائي)"},
                             {"value": "#2B2116", "label": "بنّي داكن"},
                             {"value": "#1E2A24", "label": "أخضر داكن"},
                             {"value": "#111111", "label": "أسود"},
                             {"value": "#F0E5CA", "label": "عاجي"}]
    return out, 200

def chapters(c, q):
    # أبواب كتابٍ بعينه، ومعها أرقام الأحاديث المفحوصة في كل باب.
    # و«بلا بابٍ مسجَّل» بابٌ ظاهرٌ رقمه ‎-1 لِما لم يذكر المصدرُ بابَه،
    # فلا يُنسب حديثٌ إلى بابٍ لم يُذكر، ولا يُخفى عن الاختيار.
    bk = q.g("book", "")
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
    return {"book": bk, "chapters": out}, 200

def chapter_hadiths(c, q):
    bk, ch = q.g("book", ""), q.gi("chapter", 0)
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
    return {"book": bk, "chapter": ch, "hadiths": [dict(r) for r in rows]}, 200

def templates(c, q):
    # تصفّح القوالب الجاهزة: مفلترةً بالنوع والموضوع والطول والملحقات
    kind = q.g("kind"); topic = q.g("topic"); term = q.g("q")
    where, args = ["1=1"], []
    if kind:  where.append("kind=?"); args.append(kind)
    if topic: where.append("(','||topics||',') LIKE ?"); args.append(f"%,{topic},%")
    if term:  where.append("(text LIKE ? OR title LIKE ?)"); args += [f"%{term}%"] * 2
    if q.g("with_tafsir") == "1": where.append("has_tafsir=1")
    if q.g("with_translation") == "1": where.append("has_tr=1")
    lim = min(q.gi("limit", 20), 200); off = q.gi("offset", 0)
    sql = "FROM templates WHERE " + " AND ".join(where)
    total = c.execute("SELECT COUNT(*) " + sql, args).fetchone()[0]
    rows = c.execute("SELECT ref,kind,title,text,chars,checks,has_tafsir,has_tr,topics "
                     + sql + " ORDER BY chars LIMIT ? OFFSET ?",
                     args + [lim, off]).fetchall()
    return {"total": total, "limit": lim, "offset": off,
            "templates": [dict(r) for r in rows]}, 200

def template(c, q):
    r = c.execute("SELECT payload FROM templates WHERE ref=?", (q.g("ref"),)).fetchone()
    return ((json.loads(r["payload"]) if r else {"error": "لا قالب بهذا المرجع"}),
            (200 if r else 404))

def series(c, q):
    # خطة سلسلة بطاقات: ما اجتاز الفحص فقط، ومعه وصفٌ مبنيّ من القاعدة
    import carousel as CR
    try:
        P = CR.plan(topic=q.gi("topic"), items=q.g("items"),
                    kind=q.g("kind", "mixed"), count=q.gi("count", 5),
                    title=q.g("title"), title_en=q.g("title_en", ""))
    except SystemExit as e:
        return {"error": str(e)}, 404
    total = len(P["cards"]) + 2
    slides = [{"slide": 1, "role": "cover", "title": P["title"],
               "title_en": P["title_en"], "kicker": "سلسلة",
               "lines": [f"{P['what']} — {arabic_num(len(P['cards']))} بطاقات",
                         "كلُّ نصٍّ بسنده ودرجته"],
               "badge": f"١ / {arabic_num(total)}"}]
    for i, (k, cd, rep, tag) in enumerate(P["cards"], start=2):
        slides.append({"slide": i, "role": "card", "kind": k, "ref": CR.ref_line(cd),
                       "sanad": CR.sanad_line(cd),
                       "checks": f"{rep['passed']}/{rep['total']}",
                       "badge": f"{arabic_num(i)} / {arabic_num(total)}",
                       "card": cd})
    slides.append({"slide": total, "role": "sources", "heading": "المصادر",
                   "entries": P["sources_slide"],
                   "note": f"كل نصٍّ في هذه السلسلة اجتاز {arabic_num(P['checks'])} فحصًا قبل عرضه",
                   "badge": f"{arabic_num(total)} / {arabic_num(total)}"})
    return {"title": P["title"], "title_en": P["title_en"],
            "slides": slides, "caption": P["caption"], "sources": P["sources"],
            "dropped": [{"ref": a, "why": b} for a, b in P["dropped"]]}, 200

def verify(c, q):
    text = q.g("text", "")
    got = fingerprint(text)
    if q.gi("surah") and q.gi("ayah"):
        r = c.execute("SELECT text,fingerprint FROM ayat WHERE surah=? AND ayah=?",
                      (q.gi("surah"), q.gi("ayah"))).fetchone()
        return {"ok": bool(r) and r["fingerprint"] == got,
                "expected": r["fingerprint"] if r else None,
                "got": got, "source_text": r["text"] if r else None}, 200
    r = c.execute("SELECT surah,ayah FROM ayat WHERE fingerprint=?", (got,)).fetchone()
    if r: return {"ok": True, "matched": {"surah": r["surah"], "ayah": r["ayah"]}}, 200
    r = c.execute("""SELECT b.code,h.number_in_book FROM hadiths h JOIN books b ON b.id=h.book_id
                     WHERE h.fingerprint=? OR h.matn_fp=?""", (got, got)).fetchone()
    if r: return {"ok": True, "matched": {"book": r["code"], "no": r["number_in_book"]}}, 200
    return {"ok": False, "reason": "لا يطابق أي نص في المصادر المعتمدة", "got": got}, 200

# ───────────────────────── الجدول ─────────────────────────
# مطابقةٌ تامّة بالمسار. وما ليس هنا ٤٠٤ — المنعُ أصلٌ هنا كما في الإذن.

ROUTES = {
    "/health":           health,
    "/review":           review,
    "/reciters":         reciters,
    "/audio":            audio,
    "/enc/search":       enc_search,
    "/enc":              enc,
    "/sources":          sources,
    "/topics":           topics,
    "/quran/search":     quran_search,
    "/hadith/search":    hadith_search,
    "/quran/ayah":       quran_ayah,
    "/hadith":           hadith,
    "/card":             card,
    "/options":          options,
    "/chapters":         chapters,
    "/chapter/hadiths":  chapter_hadiths,
    "/templates":        templates,
    "/template":         template,
    "/series":           series,
    "/verify":           verify,
}

def dispatch(c, path, qs):
    """يختار المعالِج ويناديه. يعيد (الجسم، رمزُ الحالة).

    `/topics/{id}` وحدَه ذو جزءٍ متغيّر، فيُطابَق بعد الجدول لا قبله —
    وإلا حجب `/topics/…` مسارَ `/topics` أو العكس.
    """
    h = ROUTES.get(path)
    if h is not None:
        return h(c, Query(qs))
    if path.startswith("/topics/"):
        return topic_items(c, Query(qs), int(path.split("/")[2]))
    return {"error": "مسار غير معروف"}, 404

def declared():
    """المساراتُ المعلَنة — يقرؤها فحصُ العقد وفحصُ تمرير التطبيق."""
    return sorted(ROUTES) + ["/topics/{id}"]
