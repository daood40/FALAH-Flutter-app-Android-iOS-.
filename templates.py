#!/usr/bin/env python3
"""القوالب الجاهزة — كل آيةٍ وكل حديثٍ مفحوصٍ في قالبٍ مكتملٍ لا ينقصه إلا التعديل.

    python3 templates.py            # يبني جدول templates داخل falah.db ويصدّر JSONL
    python3 templates.py --export   # يكتفي بتصدير الملفات من الجدول القائم

القالب الواحد يحمل: نصَّ البطاقة، وخاناتها الأربع، وكل ملحقاته (تفسيرٌ أو
شرح، ترجمة، حكمٌ ومستنده، تخريجٌ، شاهد الجامع الكامل، القرّاء للآيات)،
واقتراحَ مقاسٍ وهيئةٍ مبنيًّا على طول النصّ، ووصفًا جاهزًا للنشر.

ولا يدخل القوالبَ إلا ما اجتاز الفحوص الخمسة والعشرين. فما ظهر في القالب
منشورٌ بسنده، وما حُجب فمكانه طابور المراجعة لا القوالب.
"""
import argparse, json, os, sqlite3, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api, carousel as CR
from api import arabic_num
from falah import verify as V

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "falah.db")
OUT  = os.path.join(HERE, "templates")

SCHEMA = """
CREATE TABLE IF NOT EXISTS templates(
  ref        TEXT PRIMARY KEY,      -- quran:2:45 · hadith:bukhari:1260 · enc:5907
  kind       TEXT NOT NULL,
  title      TEXT NOT NULL,         -- سطر المرجع كما يُكتب في الوصف
  text       TEXT NOT NULL,         -- نصّ البطاقة كما يُطبع
  chars      INTEGER NOT NULL,
  checks     INTEGER NOT NULL,      -- عدد الفحوص المجتازة (٢٥ دائمًا هنا)
  has_tafsir INTEGER NOT NULL,      -- تفسيرٌ للآية أو شرحٌ للحديث
  has_tr     INTEGER NOT NULL,
  has_audio  INTEGER NOT NULL,      -- تلاوةٌ متاحة (للآيات)
  topics     TEXT,                  -- أرقام الموضوعات مفصولةً بفاصلة
  payload    TEXT NOT NULL          -- القالب كاملًا JSON
);
CREATE INDEX IF NOT EXISTS ix_tpl_kind  ON templates(kind, chars);
CREATE INDEX IF NOT EXISTS ix_tpl_ready ON templates(kind, has_tafsir, has_tr);
"""

def suggest(text, kind, has_tafsir, has_tr):
    """اقتراحٌ أوّليّ للمحرِّر: المقاس والهيئة والتقسيم — كلها قابلة للتغيير."""
    n = len(text or "")
    cap = 260 if kind == "quran" else 320
    slides = max(1, -(-n // cap))
    ratio = "square" if n <= 120 else ("vertical" if n <= 240 else "wide")
    skin  = "parch"      # هيئةٌ واحدة لكل البطاقات: الرقّ
    return {"ratio": ratio, "skin": skin, "watermark": "قناتك",
            "layout": "single" if slides == 1 else "split",
            "slides": slides,
            "show_tafsir": bool(has_tafsir) and n <= 200,
            "show_translation": bool(has_tr) and n <= 200,
            "swap_marks": False}

def caption_of(card):
    """وصفٌ جاهزٌ للنشر: مرجعٌ وسندٌ ومصدر — بلا سطر إنشاءٍ واحد."""
    lines = [CR.ref_line(card), CR.sanad_line(card)]
    src = card["provenance"]
    lines.append(src["source"] + (f" ({src['edition']})" if src.get("edition") else ""))
    j = card.get("jami")
    if j: lines.append(f"شاهدٌ: {j['book']} — {j['author']}")
    lines.append("مرَّ بخمسةٍ وعشرين فحصًا في تطبيق فلاح.")
    return "\n".join(lines)

def appendages(card, kind):
    """كل ما يفيد المحرِّر مما في القاعدة، مرتَّبًا لا مبعثرًا."""
    a = {}
    if kind == "quran":
        a["locus"]      = card["locus"]
        a["context"]    = card.get("context")
        a["mutashabih"] = card.get("mutashabih")
        a["verification"] = card["verification"]
    else:
        a["grade"]       = {"value": card.get("grade"), "basis": card.get("grade_basis"),
                            "by": card.get("grade_by"), "raw": card.get("grade_raw"),
                            "all": card.get("grade_all")}
        a["narrator"]    = card.get("narrator")
        a["takhrij"]     = card.get("takhrij")
        a["isnad_full"]  = card.get("isnad_full")
        a["jami"]        = card.get("jami")
        a["hints"]       = card.get("hints")
        a["words"]       = card.get("words")
        a["reference"]   = card.get("reference")
        a["verification"] = card.get("verification")
    return {k: v for k, v in a.items() if v not in (None, [], {}, "")}

def build_one(c, kind, ref, key):
    if kind == "quran":
        it, ctx = api.quran_card(c, ref["surah"], ref["ayah"], ref.get("to"), True, True)
    elif kind == "enc":
        it, ctx = api.enc_card(c, ref["id"])
    else:
        it, ctx = api.hadith_card(c, ref["book"], ref["no"])
    if not it: return None
    rep = V.run(it, ctx)
    if not rep["ok"]: return None

    tafsir = it.get("tafsir") or it.get("sharh")
    tr     = it.get("translation")
    tpl = {
        "ref": key, "kind": kind, "locator": ref,
        "title": CR.ref_line(it),
        "text": it["text"],
        "cells": it["cells"],                    # الخانات الأربع كما تُطبع
        "sanad": CR.sanad_line(it),
        "tafsir": tafsir, "translation": tr,
        "attribution": it.get("narrator") or it.get("intro"),
        "appendages": appendages(it, kind),
        "provenance": it["provenance"],
        "verification": {"checks": f"{rep['passed']}/{rep['total']}",
                         "stages": [s["name"] for s in rep.get("stages", [])]},
        "caption": caption_of(it),
        "edit": suggest(it["text"], kind, tafsir, tr),
    }
    return tpl, it, rep, tafsir, tr

def topics_of(c, kind, rid, cache):
    if kind not in cache:
        m = {}
        for r in c.execute("SELECT topic_id, kind, ref_id FROM topic_items WHERE kind=?",
                           ("quran" if kind == "quran" else "hadith",)):
            m.setdefault(r["ref_id"], []).append(str(r["topic_id"]))
        cache[kind] = m
    return ",".join(cache[kind].get(rid, []))

def build(db=DB):
    c = sqlite3.connect(db); c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.execute("DELETE FROM templates")
    cache, n = {}, {"quran": 0, "hadith": 0, "enc": 0}
    t0 = time.time()

    rows = c.execute("SELECT id,surah,ayah FROM ayat WHERE card_ok=1 ORDER BY surah,ayah").fetchall()
    for r in rows:
        key = f"quran:{r['surah']}:{r['ayah']}"
        got = build_one(c, "quran", {"surah": r["surah"], "ayah": r["ayah"]}, key)
        if not got: continue
        tpl, it, rep, tafsir, tr = got
        c.execute("INSERT OR REPLACE INTO templates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (key, "quran", tpl["title"], tpl["text"], len(tpl["text"]),
                   rep["passed"], int(bool(tafsir)), int(bool(tr)), 1,
                   topics_of(c, "quran", r["id"], cache),
                   json.dumps(tpl, ensure_ascii=False)))
        n["quran"] += 1
    print(f"  الآيات: {n['quran']:,} قالبًا  ({time.time()-t0:.0f}ث)", flush=True)

    rows = c.execute("""SELECT h.id, b.code, h.number_in_book n FROM hadiths h
                        JOIN books b ON b.id=h.book_id WHERE h.card_ok=1
                        ORDER BY h.book_id, h.number_in_book""").fetchall()
    for r in rows:
        key = f"hadith:{r['code']}:{r['n']}"
        got = build_one(c, "hadith", {"book": r["code"], "no": r["n"]}, key)
        if not got: continue
        tpl, it, rep, tafsir, tr = got
        c.execute("INSERT OR REPLACE INTO templates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (key, "hadith", tpl["title"], tpl["text"], len(tpl["text"]),
                   rep["passed"], int(bool(tafsir)), int(bool(tr)), 0,
                   topics_of(c, "hadith", r["id"], cache),
                   json.dumps(tpl, ensure_ascii=False)))
        n["hadith"] += 1
    print(f"  الأحاديث: {n['hadith']:,} قالبًا  ({time.time()-t0:.0f}ث)", flush=True)

    for r in c.execute("SELECT id FROM enc WHERE card_ok=1 ORDER BY id").fetchall():
        key = f"enc:{r['id']}"
        got = build_one(c, "enc", {"id": r["id"]}, key)
        if not got: continue
        tpl, it, rep, tafsir, tr = got
        c.execute("INSERT OR REPLACE INTO templates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (key, "enc", tpl["title"], tpl["text"], len(tpl["text"]),
                   rep["passed"], int(bool(tafsir)), int(bool(tr)), 0, "",
                   json.dumps(tpl, ensure_ascii=False)))
        n["enc"] += 1
    print(f"  الموسوعة: {n['enc']:,} قالبًا  ({time.time()-t0:.0f}ث)", flush=True)

    c.commit()
    return c, n

def export(c=None, outdir=OUT):
    close = False
    if c is None:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row; close = True
    os.makedirs(outdir, exist_ok=True)
    counts = {}
    for kind in ("quran", "hadith", "enc"):
        path = os.path.join(outdir, kind + ".jsonl")
        k = 0
        with open(path, "w", encoding="utf-8") as f:
            for r in c.execute("SELECT payload FROM templates WHERE kind=? ORDER BY ref", (kind,)):
                f.write(r["payload"] + "\n"); k += 1
        counts[kind] = (k, os.path.getsize(path))
    if close: c.close()
    return counts

if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--export", action="store_true", help="تصدير فقط من جدولٍ مبنيّ")
    n = a.parse_args()
    if n.export:
        counts = export()
    else:
        print("بناء القوالب الجاهزة…", flush=True)
        c, built = build()
        counts = export(c)
        c.close()
    total = sum(k for k, _ in counts.values())
    print(f"\n✓ {arabic_num(total)} قالبًا جاهزًا")
    for kind, (k, size) in counts.items():
        print(f"   templates/{kind}.jsonl — {arabic_num(k)} قالبًا · {size/1048576:.1f} م.ب")
