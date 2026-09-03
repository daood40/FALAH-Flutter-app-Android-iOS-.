#!/usr/bin/env python3
"""يصدّر لقطة من القاعدة الحقيقية ليعمل عليها النموذج التفاعلي.

كل ما في اللقطة مأخوذ من falah.db ومن محرّك الفحص نفسه — لا نصَّ مكتوبًا
باليد ولا نتيجةَ فحصٍ مُفتعلة.
"""
import sqlite3, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api
from falah import verify as V

DB  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "falah.db")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "falah-snapshot.json")
PER_TOPIC = 5          # مادة لكل موضوع من كل نوع

c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row
one = lambda s: c.execute(s).fetchone()[0]

# ── عناوين الفحوص تُخزَّن مرة واحدة، وكل بطاقة تحمل النتائج فقط ──
def report_shape(rep):
    return {"passed": rep["passed"], "total": rep["total"],
            "stages": [{"name": s["name"], "passed": s["passed"], "count": s["count"],
                        "checks": [[c["title"], 1 if c["ok"] else 0, c["detail"]]
                                   for c in s["checks"]]} for s in rep["stages"]],
            "failed": rep["failed"]}

def slim_quran(surah, ayah):
    it, ctx = api.quran_card(c, surah, ayah, None, True, True)
    if not it: return None
    rep = V.run(it, ctx)
    if not rep["ok"]: return None
    return {"kind": "quran", "ref": f"{surah}:{ayah}",
            "cells": it["cells"], "text": it["text"],
            "tafsir": it.get("tafsir"), "translation": it.get("translation"),
            "provenance": it["provenance"], "sources": it["verification"],
            "context": it.get("context"), "report": report_shape(rep)}

def slim_hadith(code, no):
    it, ctx = api.hadith_card(c, code, no)
    if not it: return None
    rep = V.run(it, ctx)
    if not rep["ok"]: return None
    return {"kind": "hadith", "ref": f"{code}:{no}",
            "cells": it["cells"], "text": it["text"],
            "narrator": it.get("narrator"), "grade": it.get("grade"),
            "grade_by": it.get("grade_by"), "grade_raw": it.get("grade_raw"),
            "grade_basis": it.get("grade_basis"), "grade_all": it.get("grade_all"),
            "takhrij": it.get("takhrij"), "jami": it.get("jami"),
            "translation": it.get("translation"),
            "provenance": it["provenance"], "sources": it["verification"],
            "report": report_shape(rep)}

topics, n_items = [], 0
for t in c.execute("SELECT * FROM topics ORDER BY id"):
    q_items, h_items = [], []
    for r in c.execute("""SELECT a.surah,a.ayah FROM topic_items ti JOIN ayat a ON a.id=ti.ref_id
                          WHERE ti.topic_id=? AND ti.kind='quran' AND a.card_ok=1
                          ORDER BY a.char_len LIMIT ?""", (t["id"], PER_TOPIC * 2)):
        card = slim_quran(r["surah"], r["ayah"])
        if card: q_items.append(card)
        if len(q_items) >= PER_TOPIC: break
    for r in c.execute("""SELECT b.code,h.number_in_book FROM topic_items ti
                          JOIN hadiths h ON h.id=ti.ref_id JOIN books b ON b.id=h.book_id
                          WHERE ti.topic_id=? AND ti.kind='hadith' AND h.card_ok=1
                          ORDER BY (h.jami_vol IS NULL), h.char_len LIMIT ?""",
                       (t["id"], PER_TOPIC * 2)):
        card = slim_hadith(r["code"], r["number_in_book"])
        if card: h_items.append(card)
        if len(h_items) >= PER_TOPIC: break
    if q_items or h_items:
        topics.append({"id": t["id"], "name": t["name_ar"], "name_en": t["name_en"],
                       "quran": q_items, "hadith": h_items})
        n_items += len(q_items) + len(h_items)

# ── أمثلة حقيقية على الحجب، بأسبابها كما سجّلتها القاعدة ──
blocked = []
for r in c.execute("""SELECT b.code,b.name_ar,h.number_in_book,h.matn,h.grade,h.grade_by,
                             h.block_reason,h.jami_conflict,h.jami_book
                      FROM hadiths h JOIN books b ON b.id=h.book_id
                      WHERE h.card_ok=0 AND h.matn IS NOT NULL
                        AND h.block_reason IN ('الحكم: ضعيف — لا يُنشر','الحكم: منكر — لا يُنشر')
                      LIMIT 2"""):
    blocked.append({"case": "weak", "book": r["name_ar"], "no": r["number_in_book"],
                    "text": r["matn"][:220], "grade": r["grade"], "by": r["grade_by"],
                    "reason": r["block_reason"]})
for r in c.execute("""SELECT b.name_ar,h.number_in_book,h.matn,h.grade,h.grade_by,
                             h.block_reason,h.jami_conflict
                      FROM hadiths h JOIN books b ON b.id=h.book_id
                      WHERE h.block_reason LIKE 'تعارض%' LIMIT 2"""):
    blocked.append({"case": "conflict", "book": r["name_ar"], "no": r["number_in_book"],
                    "text": r["matn"][:220], "grade": r["grade"], "by": r["grade_by"],
                    "jami": r["jami_conflict"], "reason": r["block_reason"]})
for r in c.execute("""SELECT ref, detail FROM review_queue WHERE kind='quran' LIMIT 2"""):
    s, a = r["ref"].split(":")
    row = c.execute("SELECT text,text_secondary FROM ayat WHERE surah=? AND ayah=?", (s, a)).fetchone()
    blocked.append({"case": "quran-conflict", "ref": r["ref"],
                    "a": row["text"], "b": row["text_secondary"],
                    "reason": "اختلف المصدران في النص"})

snap = {
    "generated_from": "falah.db",
    "stats": {
        "ayat": one("SELECT COUNT(*) FROM ayat"),
        "ayat_ready": one("SELECT COUNT(*) FROM ayat WHERE card_ok=1"),
        "hadiths": one("SELECT COUNT(*) FROM hadiths"),
        "hadiths_ready": one("SELECT COUNT(*) FROM hadiths WHERE card_ok=1"),
        "jami": one("SELECT COUNT(*) FROM hadiths WHERE jami_vol IS NOT NULL"),
        "jami_ready": one("SELECT COUNT(*) FROM hadiths WHERE card_ok=1 AND jami_vol IS NOT NULL"),
        "graded": one("SELECT COUNT(*) FROM hadiths WHERE grade IS NOT NULL"),
        "takhrij": one("SELECT COUNT(DISTINCT group_key) FROM takhrij"),
        "review": one("SELECT COUNT(*) FROM review_queue"),
        "basmala_fixed": one("SELECT COUNT(*) FROM ayat WHERE basmala_stripped=1"),
        "quran_conflicts": one("SELECT COUNT(*) FROM ayat WHERE verify_status='conflict'"),
        "snapshot_cards": n_items,
    },
    "sources": [dict(r) for r in c.execute("SELECT code,name,kind,origin,edition,riwayah,license_status FROM sources ORDER BY id")],
    "review_summary": [dict(r) for r in c.execute(
        "SELECT reason, COUNT(*) n FROM review_queue GROUP BY reason ORDER BY n DESC LIMIT 10")],
    "topics": topics,
    "blocked_examples": blocked,
}

json.dump(snap, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"البطاقات: {n_items} في {len(topics)} موضوعًا")
print(f"أمثلة الحجب: {len(blocked)}")
print(f"الحجم: {os.path.getsize(OUT)/1024:.0f} KB → {OUT}")
