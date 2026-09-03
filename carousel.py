#!/usr/bin/env python3
"""محرّك السلسلة — من موضوعٍ في القاعدة إلى سلسلة بطاقات (carousel) جاهزة للنشر.

    python3 carousel.py --topic 1 --kind hadith --count 5
    python3 carousel.py --topic 2 --kind mixed --count 6 --skin parch --ratio vertical
    python3 carousel.py --items quran:94:5:6,hadith:bukhari:1 --title "سلسلة مختارة"

السلسلة = غلاف + بطاقات + خاتمة سند. ولا يدخلها إلا ما اجتاز الفحوص الخمسة
والعشرين؛ ما رسب يُسقَط من السلسلة ويُذكر سببه، ولا يُستبدل بنصٍّ من عندنا.
الغلاف والخاتمة لا يحملان نصًّا شرعيًّا، فلا يُنسب إليهما ما ليس منهما.
"""
import argparse, json, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api, render as R
from api import arabic_num

DB = R.DB

# ــــــــــــــــــــ اختيار المادة ــــــــــــــــــــ

def topic_jobs(c, topic, kind, count):
    """أقصر النصوص أولًا: أوضحها على الشاشة وأسلمها من القطع."""
    jobs = []
    if kind in ("quran", "mixed"):
        n = count if kind == "quran" else max(1, count // 2)
        for r in c.execute("""SELECT a.surah,a.ayah FROM topic_items ti JOIN ayat a ON a.id=ti.ref_id
                              WHERE ti.topic_id=? AND ti.kind='quran' AND a.card_ok=1
                              ORDER BY a.char_len LIMIT ?""", (topic, n)):
            jobs.append(("quran", dict(surah=r["surah"], ayah=r["ayah"]),
                         f"q{r['surah']}-{r['ayah']}"))
    if kind in ("hadith", "mixed"):
        n = count if kind == "hadith" else count - len(jobs)
        for r in c.execute("""SELECT b.code,h.number_in_book FROM topic_items ti
                              JOIN hadiths h ON h.id=ti.ref_id JOIN books b ON b.id=h.book_id
                              WHERE ti.topic_id=? AND ti.kind='hadith' AND h.card_ok=1
                              ORDER BY h.char_len LIMIT ?""", (topic, n)):
            jobs.append(("hadith", dict(book=r["code"], no=r["number_in_book"]),
                         f"h{r['code']}-{r['number_in_book']}"))
    if kind == "mixed":                      # آية ثم حديث ثم آية… تنويعًا للعين
        q = [j for j in jobs if j[0] == "quran"]; h = [j for j in jobs if j[0] == "hadith"]
        jobs = [x for pair in zip(q + [None]*len(h), h + [None]*len(q)) for x in pair if x][:count]
    return jobs[:count]

def parse_items(spec):
    """quran:94:5:6,hadith:bukhari:1,enc:5907"""
    jobs = []
    for part in spec.split(","):
        p = part.strip().split(":")
        if p[0] == "quran":
            jobs.append(("quran", dict(surah=int(p[1]), ayah=int(p[2]),
                                       to=int(p[3]) if len(p) > 3 else None),
                         f"q{p[1]}-{p[2]}"))
        elif p[0] == "hadith":
            jobs.append(("hadith", dict(book=p[1], no=int(p[2])), f"h{p[1]}-{p[2]}"))
        elif p[0] == "enc":
            jobs.append(("enc", dict(id=int(p[1])), f"e{p[1]}"))
    return jobs

# ــــــــــــــــــــ سطور المرجع والسند ــــــــــــــــــــ

def ref_line(card):
    """سطر المرجع كما يُكتب في الوصف: من خانات البطاقة نفسها، لا من إنشائنا."""
    c = card["cells"]
    if card["type"] == "quran":
        return f"{c['c1'][0]} — {c['c4'][0]}"
    book = c["c1"][0]; num = c["c3"][0]
    grade = card.get("grade")
    return f"{book} — {num}" + (f" — {grade}" if grade else "")

def sanad_line(card):
    """الحكم ومَن حكم به، أو المصحف وروايته — لا حكم بلا نسبة."""
    if card["type"] == "quran":
        p = card["provenance"]
        return f"{p['source']} — {p.get('riwayah') or ''}".strip(" —")
    by = card.get("grade_by") or card.get("grade_basis")
    g  = card.get("grade") or "الدرجة غير مسجّلة"
    return f"{g}" + (f" — {by}" if by else "")

def source_lines(cards, edition=True):
    """أسماء المصادر كما سُجّلت. رمز الطبعة يفيد في الوصف ويُشوّه الشريحة، فيُفصل."""
    out = []
    for card in cards:
        p = card["provenance"]
        line = p["source"] + (f" ({p['edition']})" if edition and p.get("edition") else "")
        if line not in out: out.append(line)
        j = card.get("jami")
        if j:
            line = f"شاهدٌ: {j['book']} — {j['author']}"
            if line not in out: out.append(line)
    return out

# ــــــــــــــــــــ البناء ــــــــــــــــــــ

def plan(topic=None, items=None, kind="mixed", count=5, title=None, title_en=""):
    """خطة السلسلة قبل التصيير: البطاقات المجتازة، وما سقط ولماذا، والوصف.
    تُستعمل من سطر الأوامر ومن الخادم معًا، فالنتيجة واحدة في الموضعين."""
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    if items:
        jobs = parse_items(items)
        t_ar, t_en = title or "سلسلة مختارة", title_en
    else:
        t = c.execute("SELECT name_ar,name_en FROM topics WHERE id=?", (topic,)).fetchone()
        if not t: raise SystemExit("الموضوع غير موجود")
        jobs = topic_jobs(c, topic, kind, count)
        t_ar, t_en = title or t["name_ar"], title_en or t["name_en"]
    c.close()
    if not jobs: raise SystemExit("لا مادة مفحوصة في هذا الموضوع")

    cards, dropped = [], []
    for k, kw, tag in jobs:
        try:
            card, rep = R.fetch_card(k, **kw)
            cards.append((k, card, rep, tag))
        except SystemExit as e:
            dropped.append((tag, str(e)))
    if not cards: raise SystemExit("سقطت كل البطاقات في الفحص")

    return plan_of(cards, dropped, t_ar, t_en)

def plan_of(cards, dropped, t_ar, t_en=""):
    """الخطة محسوبةً من بطاقاتٍ جاهزة — تُستدعى من الموضوع ومن مشروع المستخدم."""
    used   = [cd for _, cd, _, _ in cards]
    checks = cards[0][2]["total"]
    srcs   = source_lines(used)                      # للوصف: بالطبعة
    kinds  = {k for k, *_ in cards}
    what   = ("آياتٌ وأحاديث" if len(kinds) > 1 else
              ("آيات" if "quran" in kinds else "أحاديث"))
    cap = [t_ar, ""]
    for i, card in enumerate(used, start=1):
        cap.append(f"{arabic_num(i)}) {ref_line(card)}")
        cap.append(f"   {sanad_line(card)}")
    cap += ["", "المصادر:"] + [f"• {s}" for s in srcs]
    cap += ["", f"كل نصٍّ مرَّ بـ{arabic_num(checks)} فحصًا في تطبيق فلاح."]

    return {"title": t_ar, "title_en": t_en, "cards": cards, "dropped": dropped,
            "sources": srcs, "sources_slide": source_lines(used, edition=False),
            "checks": checks, "what": what, "caption": "\n".join(cap)}

def build(topic=None, items=None, kind="mixed", count=5, skin="parch", ratio="square",
          wm="قناتك", swap=False, outdir="out/carousel", title=None, title_en=""):
    return render_plan(plan(topic, items, kind, count, title, title_en),
                       skin, ratio, wm, swap, outdir)

def render_plan(P, skin="parch", ratio="square", wm="قناتك", swap=False,
                outdir="out/carousel", falah_mark=True):
    os.makedirs(outdir, exist_ok=True)
    cards, total = P["cards"], len(P["cards"]) + 2      # غلاف + بطاقات + خاتمة
    files, manifest = [], []

    def shot(html, name):
        p = os.path.join(outdir, name)
        R.render(html, p, ratio); files.append(p); return p

    # ١) الغلاف
    cover = R.build_cover_html(
        P["title"], P["title_en"], "سلسلة",
        [f"{P['what']} — {arabic_num(len(cards))} بطاقات", "كلُّ نصٍّ بسنده ودرجته"],
        skin, ratio, wm, swap, f"١ / {arabic_num(total)}")
    shot(cover, "01_cover.png")
    manifest.append({"slide": 1, "role": "cover", "file": "01_cover.png"})

    # ٢) البطاقات
    for i, (k, card, rep, tag) in enumerate(cards, start=2):
        html = R.build_html(card, "quran" if k == "quran" else "hadith",
                            skin, ratio, wm, swap, falah_mark=falah_mark,
                            badge=f"{arabic_num(i)} / {arabic_num(total)}")
        shot(html, f"{i:02d}_{tag}.png")
        manifest.append({"slide": i, "role": "card", "file": f"{i:02d}_{tag}.png",
                         "kind": k, "ref": ref_line(card), "sanad": sanad_line(card),
                         "checks": f"{rep['passed']}/{rep['total']}",
                         "source": card.get("provenance", {}).get("source")})

    # ٣) الخاتمة — سند ما عُرض
    end = R.build_end_html(
        "المصادر", P["sources_slide"],
        f"كل نصٍّ في هذه السلسلة اجتاز {arabic_num(P['checks'])} فحصًا قبل عرضه",
        skin, ratio, wm, swap, f"{arabic_num(total)} / {arabic_num(total)}")
    shot(end, f"{total:02d}_end.png")
    manifest.append({"slide": total, "role": "sources", "file": f"{total:02d}_end.png",
                     "sources": P["sources"]})

    # ٤) الوصف — مبنيٌّ من القاعدة، لا سطر إنشاءٍ فيه
    open(os.path.join(outdir, "caption.txt"), "w", encoding="utf-8").write(P["caption"])
    json.dump({"title": P["title"], "title_en": P["title_en"], "ratio": ratio, "skin": skin,
               "slides": manifest,
               "dropped": [{"ref": a, "why": b} for a, b in P["dropped"]],
               "caption": P["caption"]},
              open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return files, P["dropped"], P["title"]

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--topic", type=int); p.add_argument("--items")
    p.add_argument("--kind", default="mixed", choices=["quran", "hadith", "mixed"])
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--skin", default="parch", choices=list(R.SKINS))
    p.add_argument("--ratio", default="square", choices=list(R.SIZES))
    p.add_argument("--wm", default="قناتك"); p.add_argument("--swap", action="store_true")
    p.add_argument("--title"); p.add_argument("--title-en", default="")
    p.add_argument("--dir", default="out/carousel")
    n = p.parse_args()
    if not n.topic and not n.items: raise SystemExit("حدّد --topic أو --items")
    files, dropped, title = build(n.topic, n.items, n.kind, n.count, n.skin, n.ratio,
                                  n.wm, n.swap, n.dir, n.title, n.title_en)
    w, h = R.SIZES[n.ratio]
    print(f"✓ {title} — {arabic_num(len(files))} شرائح {w}×{h} في {n.dir}")
    for f in files: print("   " + os.path.basename(f))
    for tag, why in dropped: print(f"   ✗ {tag}: {why}")
