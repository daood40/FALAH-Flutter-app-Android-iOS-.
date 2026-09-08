#!/usr/bin/env python3
"""يبني مادّة المعاينة: كل السور وكل الأبواب وكل الأرقام الجاهزة، ومعها
النصوص كما هي في القاعدة — لا يُختصر منها إلا التفسير والترجمة عند حدّ
ما يظهر في البطاقة. المخرج مضغوطٌ ومرمَّز حتى تبقى الصفحة خفيفة.

    python3 preview_data.py            → preview-data.json + preview-data.b64
"""
import base64, gzip, json, os, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "falah.db")

def build():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row

    surahs = [{"n": r["number"], "ar": r["name_ar"], "en": r["name_en"],
               "rev": r["revelation_ar"], "reve": r["revelation_en"],
               "count": r["c"]}
              for r in c.execute("""SELECT s.number, s.name_ar, s.name_en, s.revelation_ar,
                                      s.revelation_en,
                                      (SELECT COUNT(*) FROM ayat a WHERE a.surah=s.number) c
                                    FROM surahs s ORDER BY s.number""")]

    # الآيات مجموعةً بسورها: [نص, صفحة, جاهزة؟]
    ayat = {}
    for r in c.execute("SELECT surah, ayah, text, page, card_ok FROM ayat ORDER BY surah, ayah"):
        ayat.setdefault(str(r["surah"]), {})[str(r["ayah"])] = [r["text"], r["page"], r["card_ok"]]

    taf, taf_src = {}, {}
    for r in c.execute("""SELECT t.surah, t.ayah, substr(t.text,1,330) t, s.name
                          FROM ayah_tafsir t JOIN sources s ON s.id=t.source_id"""):
        taf.setdefault(str(r["surah"]), {})[str(r["ayah"])] = r["t"]
        taf_src[str(r["surah"])] = r["name"]

    tr, tr_src = {}, {}
    for r in c.execute("""SELECT t.surah, t.ayah, substr(t.text,1,230) t, s.name
                          FROM ayah_translation t JOIN sources s ON s.id=t.source_id"""):
        tr.setdefault(str(r["surah"]), {})[str(r["ayah"])] = r["t"]
        tr_src[str(r["surah"])] = r["name"]

    books = [{"code": r["code"], "ar": r["name_ar"], "en": r["name_en"], "ready": r["n"]}
             for r in c.execute("""SELECT b.code, b.name_ar, b.name_en,
                                     (SELECT COUNT(*) FROM hadiths h
                                       WHERE h.book_id=b.id AND h.card_ok=1) n
                                   FROM books b ORDER BY b.id""") if r["n"]]
    codes = {b["code"] for b in books}

    chapters = {}
    for r in c.execute("""SELECT b.code, ch.chapter_id, ch.name_ar, ch.name_en,
                            (SELECT COUNT(*) FROM hadiths h WHERE h.book_id=b.id
                              AND h.chapter_id=ch.chapter_id AND h.card_ok=1) n
                          FROM chapters ch JOIN books b ON b.id=ch.book_id
                          ORDER BY b.id, ch.chapter_id"""):
        if r["code"] in codes and r["n"]:
            chapters.setdefault(r["code"], []).append(
                [r["chapter_id"], r["name_ar"], r["name_en"], r["n"]])
    # ما لم يذكر المصدرُ بابَه يُعرض في بابٍ ظاهرٍ رقمه ‎-1، ولا يُنسب إلى باب
    for r in c.execute("""SELECT b.code, COUNT(*) n FROM hadiths h JOIN books b ON b.id=h.book_id
                          WHERE h.card_ok=1 AND (h.chapter_id IS NULL
                            OR NOT EXISTS (SELECT 1 FROM chapters ch
                               WHERE ch.book_id=h.book_id AND ch.chapter_id=h.chapter_id))
                          GROUP BY b.code"""):
        if r["code"] in codes:
            chapters.setdefault(r["code"], []).append(
                [-1, "بلا بابٍ مسجَّل في المصدر", "No chapter recorded in source", r["n"]])

    # الأحاديث: كتاب ← باب ← [رقم, درجة, متن, راوٍ, تخريج, شرح]
    hadiths = {}
    for r in c.execute("""SELECT b.code, h.chapter_id, h.number_in_book no, h.grade,
                            h.matn, h.narrator_ar, h.grade_by, h.id,
                            (SELECT COUNT(*) FROM chapters ch WHERE ch.book_id=h.book_id
                              AND ch.chapter_id=h.chapter_id) has_ch
                          FROM hadiths h JOIN books b ON b.id=h.book_id
                          WHERE h.card_ok=1 ORDER BY b.id, h.chapter_id, h.number_in_book"""):
        key = str(r["chapter_id"]) if r["has_ch"] else "-1"
        hadiths.setdefault(r["code"], {}).setdefault(key, []).append(
            [r["no"], r["grade"] or "", r["matn"] or "", r["narrator_ar"] or "",
             r["grade_by"] or "", r["id"]])

    # الشروح المسندة — لا يُكتب منها شيء، إنما يُنقل بنصّه وباسم مصدره
    sharh = {}
    for r in c.execute("""SELECT l.hadith_id, substr(e.explanation,1,330) t, s.name
                          FROM enc_link l JOIN enc e ON e.id=l.enc_id
                          JOIN sources s ON s.id=e.source_id
                          WHERE e.explanation IS NOT NULL"""):
        sharh.setdefault(str(r["hadith_id"]), [r["t"], r["name"]])

    tafsirs = [{"value": r["code"], "label": r["name"]} for r in c.execute(
        "SELECT code,name FROM sources WHERE kind='tafsir' AND enabled=1")]
    trs = [{"value": r["code"], "label": r["name"]} for r in c.execute(
        "SELECT code,name FROM sources WHERE kind='translation' AND enabled=1")]
    reciters = [{"value": r["code"], "label": r["name"], "riwayah": r["riwayah"]}
                for r in c.execute("SELECT code,name,riwayah FROM reciters ORDER BY riwayah,name")]

    stat = {k: c.execute(q).fetchone()[0] for k, q in {
        "ayat": "SELECT COUNT(*) FROM ayat",
        "ayat_ready": "SELECT COUNT(*) FROM ayat WHERE card_ok=1",
        "hadiths": "SELECT COUNT(*) FROM hadiths",
        "hadiths_ready": "SELECT COUNT(*) FROM hadiths WHERE card_ok=1",
        "templates": "SELECT COUNT(*) FROM templates",
        "sources": "SELECT COUNT(*) FROM sources"}.items()}
    c.close()

    return {"surahs": surahs, "ayat": ayat, "tafsir": taf, "tafsir_src": taf_src,
            "tr": tr, "tr_src": tr_src, "books": books, "chapters": chapters,
            "hadiths": hadiths, "sharh": sharh, "tafsirs": tafsirs,
            "translations": trs, "reciters": reciters, "stat": stat}

if __name__ == "__main__":
    data = build()
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    open(os.path.join(HERE, "preview-data.json"), "wb").write(raw)
    packed = base64.b64encode(gzip.compress(raw, 9)).decode()
    open(os.path.join(HERE, "preview-data.b64"), "w").write(packed)
    print(f"خام {len(raw)/1e6:.2f}م.ب → مضغوطًا مرمَّزًا {len(packed)/1e6:.2f}م.ب")
    print("سور:", len(data["surahs"]), "· كتب:", len(data["books"]),
          "· أحاديث:", sum(len(v) for b in data["hadiths"].values() for v in b.values()),
          "· شروح:", len(data["sharh"]))
