#!/usr/bin/env python3
"""تصدير دفعة: كل بطاقات موضوعٍ ما بمقاسٍ وشكل."""
import sys, os, sqlite3, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R
p = argparse.ArgumentParser()
p.add_argument("--topic", type=int, default=2); p.add_argument("--kind", default="quran")
p.add_argument("--skin", default="parch"); p.add_argument("--ratio", default="square")
p.add_argument("--limit", type=int, default=5); p.add_argument("--wm", default="قناتك")
p.add_argument("--dir", default="out")
n = p.parse_args()
os.makedirs(n.dir, exist_ok=True)
c = sqlite3.connect(f"file:{R.DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row
if n.kind == "quran":
    rows = c.execute("""SELECT a.surah,a.ayah FROM topic_items ti JOIN ayat a ON a.id=ti.ref_id
                        WHERE ti.topic_id=? AND ti.kind='quran' AND a.card_ok=1
                        ORDER BY a.char_len LIMIT ?""", (n.topic, n.limit)).fetchall()
    jobs = [("quran", dict(surah=r["surah"], ayah=r["ayah"]), f"{r['surah']}-{r['ayah']}") for r in rows]
else:
    rows = c.execute("""SELECT b.code,h.number_in_book FROM topic_items ti
                        JOIN hadiths h ON h.id=ti.ref_id JOIN books b ON b.id=h.book_id
                        WHERE ti.topic_id=? AND ti.kind='hadith' AND h.card_ok=1
                        ORDER BY h.char_len LIMIT ?""", (n.topic, n.limit)).fetchall()
    jobs = [("hadith", dict(book=r["code"], no=r["number_in_book"]), f"{r['code']}-{r['number_in_book']}") for r in rows]
name = c.execute("SELECT name_ar FROM topics WHERE id=?", (n.topic,)).fetchone()[0]
c.close()
ok = 0
for kind, kw, tag in jobs:
    try:
        card, rep = R.fetch_card(kind, **kw)
        html = R.build_html(card, kind, n.skin, n.ratio, n.wm)
        out = os.path.join(n.dir, f"{tag}.png")
        R.render(html, out, n.ratio); ok += 1
        print(f"  ✓ {out}  ({rep['passed']}/{rep['total']})")
    except SystemExit as e:
        print(f"  ✗ {tag}: {e}")
print(f"\n{name}: صُدِّر {ok} من {len(jobs)}")
