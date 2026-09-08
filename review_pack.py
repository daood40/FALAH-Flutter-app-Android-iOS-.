#!/usr/bin/env python3
"""حزمة المراجعة — ملفٌّ يُسلَّم لعالِمٍ ليحكم فيما حُجب.

    python3 review_pack.py --reason تعارض --limit 200
    python3 review_pack.py --reason "لا حكم" --out review/

يُخرج ثلاثة ملفات في مجلّد الحزمة:
  • review.html   صفحةٌ للقراءة والطباعة، فيها كل ما يحتاجه المراجع
  • review.csv    جدولٌ يفتحه بإكسل ويكتب قراره في عموده
  • rulings.template.json  قالب القرارات جاهزًا للتعبئة أو التوليد من الجدول

ولا يُدرَج في الحزمة إلا **الحجب الحُكمي** — التعارض وانعدام الحكم — لأن
الحجب الآليّ (متنٌ مقطوع، نصٌّ بمصدرٍ واحد) علّته في سلامة النصّ لا في
الحكم، فلا يرفعه توقيع.
"""
import argparse, csv, html, json, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api import arabic_num
from falah import rulings as RU

HERE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(HERE, "falah.db")

def gather(c, reason, limit):
    rows = c.execute("""
        SELECT h.id, h.matn, h.matn_fp, h.full_ar, h.grade, h.grade_all, h.grade_basis,
               h.block_reason, h.verify_status, h.narrator_ar,
               h.jami_vol, h.jami_book, h.jami_bab, h.jami_grade, h.jami_takhrij,
               b.name_ar bn, b.code bcode, h.number_in_book no,
               (SELECT GROUP_CONCAT(b2.name_ar || ' ' || t.number_in_book, ' · ')
                  FROM takhrij t JOIN books b2 ON b2.id=t.book_id
                 WHERE t.group_key=h.core_key) takhrij
        FROM hadiths h JOIN books b ON b.id=h.book_id
        WHERE h.card_ok=0 AND h.matn IS NOT NULL AND h.block_reason LIKE ?
        ORDER BY h.book_id, h.number_in_book LIMIT ?""", (reason + "%", limit)).fetchall()
    return rows

def html_page(rows, reason):
    def esc(x): return html.escape(str(x or ""))
    cards = []
    for i, r in enumerate(rows, 1):
        ev = []
        if r["grade"]:      ev.append(("الحكم المسجَّل", r["grade"] + (f" — {r['grade_basis']}" if r["grade_basis"] else "")))
        if r["grade_all"]:
            try:  ev.append(("أحكام أخرى", "، ".join(f"{k}: {v}" for k, v in
                             json.loads(r["grade_all"]).items())))
            except Exception: pass
        if r["jami_vol"]:
            ev.append(("الجامع الكامل", f"مج {r['jami_vol']} · {r['jami_book'] or ''} · "
                                        f"{r['jami_bab'] or ''} · لفظ الحكم عنده: {r['jami_grade'] or '—'}"))
        if r["jami_takhrij"]: ev.append(("تخريج الأعظمي", r["jami_takhrij"][:300]))
        if r["takhrij"]:      ev.append(("مواضع أخرى", r["takhrij"]))
        if r["narrator_ar"]:  ev.append(("الراوي", r["narrator_ar"]))
        ev.append(("سبب الحجب", r["block_reason"]))
        ev.append(("بصمة المتن", r["matn_fp"]))
        rowsh = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in ev)
        cards.append(f"""<article>
  <header><span class="n">{arabic_num(i)}</span>
    <b>{esc(r['bn'])} — رقم {arabic_num(r['no'])}</b></header>
  <p class="matn">«{esc(r['matn'])}»</p>
  <details><summary>النصّ بسنده</summary><p class="isnad">{esc(r['full_ar'])}</p></details>
  <table>{rowsh}</table>
  <div class="verdict">القرار: <span></span> &nbsp;&nbsp; الحكم: <span></span>
    &nbsp;&nbsp; المستند: <span class="wide"></span><br>المراجع: <span></span>
    &nbsp;&nbsp; التاريخ: <span></span></div>
</article>""")
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<title>حزمة مراجعة — {esc(reason)}</title><style>
body{{font-family:'Amiri','Times New Roman',serif;max-width:900px;margin:0 auto;padding:24px;
  line-height:1.9;color:#1c1c1c}}
h1{{font-size:26px;margin-bottom:4px}} .lead{{color:#555;margin-bottom:22px}}
article{{border:1px solid #ccc;border-radius:8px;padding:16px 18px;margin-bottom:18px;
  page-break-inside:avoid}}
header{{display:flex;gap:10px;align-items:center;border-bottom:1px solid #eee;padding-bottom:8px}}
.n{{background:#123;color:#fff;border-radius:99px;padding:1px 10px;font-size:14px}}
.matn{{font-size:21px;margin:14px 0}}
.isnad{{color:#444;font-size:15px}}
table{{width:100%;border-collapse:collapse;font-size:15px;margin-top:8px}}
th{{text-align:right;color:#666;font-weight:400;width:150px;vertical-align:top;padding:3px 0}}
td{{padding:3px 0;word-break:break-word}}
.verdict{{margin-top:14px;border-top:1px dashed #bbb;padding-top:10px;font-size:15px;color:#333}}
.verdict span{{display:inline-block;border-bottom:1px solid #999;min-width:120px;height:20px}}
.verdict span.wide{{min-width:320px}}
@media print{{article{{border-color:#999}}}}
</style></head><body>
<h1>حزمة مراجعة — {esc(reason)}</h1>
<p class="lead">{arabic_num(len(rows))} حديثًا محجوبًا لسببٍ حُكميّ، مع كل ما في القاعدة من
شواهدها وأحكامها. القرار لفضيلتكم، ويُسجَّل باسمكم وتاريخه، ويُربط ببصمة
المتن فيسقط إن تغيّر حرفٌ منه.</p>
{''.join(cards)}
</body></html>"""

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--reason", default="تعارض", help="بادئة سبب الحجب")
    a.add_argument("--limit", type=int, default=200)
    a.add_argument("--out", default="review")
    n = a.parse_args()

    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    rows = gather(c, n.reason, n.limit); c.close()
    if not rows: raise SystemExit("لا محجوب بهذا السبب")
    # لا تُحزَم إلا الأسباب الحُكمية
    if not n.reason.startswith(RU.GRADE_BLOCKS):
        raise SystemExit("هذا حجبٌ آليّ لا يرفعه قرار مراجع — انظر falah/rulings.py")

    os.makedirs(n.out, exist_ok=True)
    open(os.path.join(n.out, "review.html"), "w", encoding="utf-8").write(html_page(rows, n.reason))

    cols = ["الكتاب", "الرقم", "المتن", "سبب الحجب", "الحكم المسجَّل", "لفظ الأعظمي",
            "تخريج الأعظمي", "مواضع أخرى", "بصمة المتن",
            "القرار (release/block)", "الحكم", "المستند", "المراجع", "التاريخ", "ملاحظة"]
    with open(os.path.join(n.out, "review.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for r in rows:
            w.writerow([r["bn"], r["no"], r["matn"], r["block_reason"], r["grade"] or "",
                        r["jami_grade"] or "", (r["jami_takhrij"] or "")[:200],
                        r["takhrij"] or "", r["matn_fp"], "", "", "", "", "", ""])

    tmpl = [RU.template(r["matn_fp"], f"{r['bcode']} {r['no']}", r["matn"], r["block_reason"])
            for r in rows]
    json.dump({"rulings": tmpl}, open(os.path.join(n.out, "rulings.template.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"✓ {n.out}/  — {arabic_num(len(rows))} حديثًا للمراجعة")
    print("   review.html · review.csv · rulings.template.json")

if __name__ == "__main__":
    main()
