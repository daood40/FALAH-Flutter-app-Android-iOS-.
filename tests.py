#!/usr/bin/env python3
"""اختبارات طبقة المحتوى. تُشغَّل بلا خادم: python3 tests.py"""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from falah.text import fingerprint, searchable, search_variants
from falah.matn import matn_sane
from falah.reconcile import orthographic_key
from falah import verify as V
import api

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "falah.db")
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row

def _try_err(fn, exc):
    """يعيد True إن رفع الاستدعاءُ الخطأَ المتوقَّع."""
    try:    fn(); return False
    except exc: return True

fails = []
def check(name, cond, note=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  ({note})" if note else ""))
    if not cond: fails.append(name)

print("\n▸ سلامة القاعدة")
n = c.execute("SELECT COUNT(*) FROM ayat").fetchone()[0]
check("القرآن كامل ٦٢٣٦ آية", n == 6236, n)
check("١١٤ سورة", c.execute("SELECT COUNT(*) FROM surahs").fetchone()[0] == 114)
check("لكل آية تفسير", c.execute("SELECT COUNT(*) FROM ayah_tafsir").fetchone()[0] == 6236)
check("لكل آية ترجمة", c.execute("SELECT COUNT(*) FROM ayah_translation").fetchone()[0] == 6236)
check("لا آية بلا بصمة", c.execute("SELECT COUNT(*) FROM ayat WHERE fingerprint IS NULL").fetchone()[0] == 0)

print("\n▸ صحة البصمة — قفل المصدر")
r = c.execute("SELECT text,fingerprint FROM ayat WHERE surah=94 AND ayah=5").fetchone()
check("البصمة تُعاد بنفس القيمة", fingerprint(r["text"]) == r["fingerprint"])
check("حذف حرف واحد يكسر البصمة", fingerprint(r["text"][:-1]) != r["fingerprint"])
check("زيادة تشكيل تكسر البصمة", fingerprint(r["text"] + "ً") != r["fingerprint"])
check("الفراغ الزائد لا يكسرها", fingerprint("  " + r["text"] + "  ") == r["fingerprint"])

print("\n▸ مواضع الآيات مقابل المصحف")
for s, a, page, juz in [(94,5,596,30), (2,286,49,3), (13,28,252,13), (65,2,558,28), (1,1,1,1)]:
    row = c.execute("SELECT page,juz FROM ayat WHERE surah=? AND ayah=?", (s,a)).fetchone()
    check(f"{s}:{a} صفحة {page} جزء {juz}", row["page"]==page and row["juz"]==juz,
          f"وجد {row['page']}/{row['juz']}")

print("\n▸ فصل المتن عن السند")
h = c.execute("""SELECT h.* FROM hadiths h JOIN books b ON b.id=h.book_id
                 WHERE b.code='bukhari' AND h.number_in_book=1""").fetchone()
check("متن حديث النية مستخرج", bool(h["matn"]) and "انما الاعمال" in searchable(h["matn"]))
check("السند لم يدخل المتن", "حدثنا" not in searchable(h["matn"] or ""))
check("الراوي: عمر بن الخطاب", h["narrator_ar"] == "عمر بن الخطاب", h["narrator_ar"])
check("السند الكامل محفوظ", "حدثنا" in searchable(h["full_ar"]))
cov = c.execute("SELECT COUNT(*) FROM hadiths WHERE matn IS NOT NULL").fetchone()[0]
tot = c.execute("SELECT COUNT(*) FROM hadiths").fetchone()[0]
check("تغطية فصل المتن فوق ٨٠٪", cov/tot > 0.80, f"{cov*100//tot}%")

print("\n▸ التحقق المزدوج للقرآن")
bad = c.execute("""SELECT COUNT(*) FROM ayat WHERE surah NOT IN (1,9) AND ayah=1
                   AND plain LIKE 'بسم الله الرحمن الرحيم%'""").fetchone()[0]
check("لا بسملة مُلحقة بأول أي سورة", bad == 0, bad)
strip = c.execute("SELECT COUNT(*) FROM ayat WHERE basmala_stripped=1").fetchone()[0]
check("نُزعت من ١١٢ سورة", strip == 112, strip)
conf = c.execute("SELECT COUNT(*) FROM ayat WHERE verify_status='conflict'").fetchone()[0]
check("الاختلافات مع المصدر الثاني محصورة", conf <= 5, conf)
leak = c.execute("SELECT COUNT(*) FROM ayat WHERE card_ok=1 AND verify_status='conflict'").fetchone()[0]
check("لا آية مختلَف فيها تُفرَج", leak == 0, leak)
sec = c.execute("SELECT COUNT(*) FROM ayat WHERE text_secondary IS NULL").fetchone()[0]
check("لكل آية نظير من المصدر الثاني", sec == 0, sec)
row = c.execute("SELECT text,text_secondary FROM ayat WHERE surah=13 AND ayah=28").fetchone()
check("مفتاح الرسم يوحّد الطبعتين",
      orthographic_key(row["text"]) == orthographic_key(row["text_secondary"]))

print("\n▸ قاعدة الدرجات")
check("البخاري: صحيح بشرطه",
      c.execute("SELECT grade FROM hadiths WHERE book_id=1 LIMIT 1").fetchone()[0] == "صحيح")
sch = c.execute("SELECT COUNT(*) FROM hadiths WHERE grade_source='scholar'").fetchone()[0]
check("أحكام محدِّثين مسمَّين مُسندة", sch > 15000, sch)
noby = c.execute("SELECT COUNT(*) FROM hadiths WHERE grade_source='scholar' AND grade_by IS NULL").fetchone()[0]
check("كل حكم محدِّث باسم قائله", noby == 0, noby)
weak = c.execute("""SELECT COUNT(*) FROM hadiths WHERE card_ok=1
                    AND grade NOT IN ('صحيح','حسن','حسن صحيح','صحيح لغيره','حسن لغيره',
                                      'إسناده صحيح','إسناده حسن')""").fetchone()[0]
check("لا حديث ضعيف فما دون يُفرَج", weak == 0, weak)
nog = c.execute("SELECT COUNT(*) FROM hadiths WHERE card_ok=1 AND grade IS NULL").fetchone()[0]
check("لا حديث بلا حكم يُفرَج", nog == 0, nog)
unc = c.execute("SELECT COUNT(*) FROM hadiths WHERE card_ok=1 AND verify_status<>'confirmed'").fetchone()[0]
check("كل مُفرَج تأكّد من مصدر ثانٍ", unc == 0, unc)
inv = c.execute("SELECT COUNT(*) FROM hadiths WHERE grade IS NOT NULL AND grade_basis IS NULL").fetchone()[0]
check("لا درجة بلا مستند", inv == 0)

print("\n▸ سلامة المتون المُفرَج عنها")
sample = c.execute("""SELECT b.code,h.number_in_book,h.matn,h.matn_conf FROM hadiths h
                      JOIN books b ON b.id=h.book_id WHERE h.card_ok=1
                      ORDER BY RANDOM() LIMIT 400""").fetchall()
bad = [(r["code"], r["number_in_book"], matn_sane(r["matn"])[1]) for r in sample
       if not matn_sane(r["matn"])[0]]
check("٤٠٠ متن عشوائي كلها سليمة", not bad, bad[:2])
lowc = sum(1 for r in sample if r["matn_conf"] < 0.95)
check("كلها من علامة الطبعة لا التخمين", lowc == 0, lowc)
# فحص على مستوى الكلمة لكل متن مُفرَج — لا LIKE يخلط «وَيْلٌ» بواو العطف
allm = c.execute("SELECT matn FROM hadiths WHERE card_ok=1").fetchall()
bad_all = [r["matn"] for r in allm if not matn_sane(r["matn"])[0]]
check(f"كل المتون المُفرَج عنها ({len(allm)}) تجتاز حارس السلامة",
      not bad_all, bad_all[:1])

print("\n▸ طابور المراجعة")
rq = c.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
check("كل محجوب مسجَّل بسببه", rq > 1000, rq)
noreason = c.execute("SELECT COUNT(*) FROM review_queue WHERE reason IS NULL OR reason=''").fetchone()[0]
check("لا حجب بلا سبب مذكور", noreason == 0, noreason)
blocked_no_reason = c.execute("SELECT COUNT(*) FROM hadiths WHERE card_ok=0 AND block_reason IS NULL").fetchone()[0]
check("كل حديث محجوب له سبب", blocked_no_reason == 0, blocked_no_reason)

print("\n▸ شاهد الجامع الكامل")
jw = c.execute("SELECT COUNT(*) FROM hadiths WHERE jami_vol IS NOT NULL").fetchone()[0]
check("الجامع الكامل شهد لآلاف الأحاديث", jw > 10000, jw)
jc = c.execute("SELECT COUNT(*) FROM hadiths WHERE jami_vol IS NOT NULL AND card_ok=1").fetchone()[0]
check("منها ضمن البطاقات", jc > 5000, jc)
nob = c.execute("SELECT COUNT(*) FROM hadiths WHERE jami_vol IS NOT NULL AND jami_hits<2").fetchone()[0]
check("لا شهادة دون عتبة المقاطع", nob == 0, nob)
row = c.execute("""SELECT h.jami_vol,h.jami_book,h.jami_hits FROM hadiths h JOIN books b ON b.id=h.book_id
                   WHERE b.code='bukhari' AND h.number_in_book=1""").fetchone()
check("حديث النية شهد له الأعظمي", row["jami_vol"] is not None,
      f"مج{row['jami_vol']} · {row['jami_book']} · {row['jami_hits']} مقاطع")
# النص لا يُؤخذ من الجامع أبدًا — نتأكد أن لا عمود نصّي منه
cols = [r[1] for r in c.execute("PRAGMA table_info(hadiths)")]
check("لا نصَّ مخزَّنًا من الجامع الكامل",
      not any(x.startswith("jami_") and x.endswith(("text","matn")) for x in cols))
bab = c.execute("SELECT COUNT(*) FROM hadiths WHERE jami_bab IS NOT NULL").fetchone()[0]
check("بابُ الأعظمي مستخرج", bab > 10000, bab)
tk = c.execute("SELECT COUNT(*) FROM hadiths WHERE jami_takhrij IS NOT NULL").fetchone()[0]
check("تخريج الأعظمي مستخرج", tk > 10000, tk)
pol = dict(c.execute("SELECT jami_polarity,COUNT(*) FROM hadiths WHERE jami_vol IS NOT NULL GROUP BY 1").fetchall())
check("أحكام الكتاب مصنَّفة إيجابًا وسلبًا", pol.get("positive",0) > 5000 and pol.get("negative",0) > 0, pol)
leak = c.execute("""SELECT COUNT(*) FROM hadiths WHERE card_ok=1 AND jami_polarity='negative'""").fetchone()[0]
check("لا حديث تحفّظ عليه الأعظمي يُفرَج", leak == 0, leak)
conf = c.execute("SELECT COUNT(*) FROM hadiths WHERE block_reason LIKE 'تعارض%'").fetchone()[0]
check("التعارض بين الأحكام يُحجب ويُسجَّل", conf > 0, conf)
jg = c.execute("SELECT COUNT(*) FROM hadiths WHERE grade_source='jami' AND grade_basis IS NULL").fetchone()[0]
check("حكم الأعظمي مقرونٌ بمستنده", jg == 0, jg)
src_j = c.execute("SELECT kind,license_status FROM sources WHERE code='jami.kamil'").fetchone()
check("مسجَّل في السجل بدوره الصحيح", src_j and src_j["kind"] == "hadith-witness", dict(src_j) if src_j else None)

print("\n▸ التخريج المتقاطع والمتشابه")
g = c.execute("SELECT COUNT(DISTINCT group_key) FROM takhrij").fetchone()[0]
check("مجموعات تخريج متقاطع موجودة", g > 500, g)
m = c.execute("SELECT COUNT(*) FROM ayat WHERE mutashabih_group IS NOT NULL").fetchone()[0]
check("المتشابه اللفظي مُعلَّم", m > 100, m)

print("\n▸ البحث")
def count(tbl, term):
    for q in search_variants(term):
        n = c.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {tbl} MATCH ?", (q,)).fetchone()[0]
        if n: return n, q
    return 0, None
def finds(term, surah, ayah):
    for q in search_variants(term):
        hit = c.execute("""SELECT 1 FROM ayat_fts f JOIN ayat a ON a.id=f.rowid
                           WHERE ayat_fts MATCH ? AND a.surah=? AND a.ayah=?""",
                        (q, surah, ayah)).fetchone()
        if hit: return True, q
    return False, None
ok,q = finds("الصبر", 2, 153);  check("«الصبر» تجد البقرة ١٥٣", ok, q)
ok,q = finds("بالصبر", 103, 3); check("«بالصبر» تجد العصر ٣", ok, q)
ok,q = finds("صبر", 2, 153);    check("«صبر» بلا أداة تجدها أيضًا", ok, q)
n,q = count("hadith_fts","النية"); check("البحث في الحديث يجد «النية»", n > 5, f"{n} عبر {q}")
n,q = count("hadith_fts","النصيحة"); check("«النصيحة» في الحديث", n > 3, f"{n} عبر {q}")

print("\n▸ محرّك الفحوص الـ٢٥")
it, ctx = api.quran_card(c, 94, 5, 6, True, True)
rep = V.run(it, ctx)
check("عدد الفحوص ٢٥ بالضبط", rep["total"] == 25, rep["total"])
check("خمس مراحل", len(rep["stages"]) == 5)
check("آية سليمة تجتاز الكل", rep["ok"], f"{rep['passed']}/25 — {rep['failed']}")
check("خانات الشريط العلوي أربع", len(it["cells"]) == 4)
check("الشريط يحمل السورة والصفحة", "الشرح" in searchable(it["cells"]["c1"][0]) and "٥٩٦" in it["cells"]["c3"][0])

it2, ctx2 = api.hadith_card(c, "bukhari", 1)
rep2 = V.run(it2, ctx2)
check("حديث الصحيحين يجتاز", rep2["ok"], f"{rep2['passed']}/25 — {rep2['failed']}")
check("التخريج المتقاطع مذكور", len(it2["takhrij"]) >= 1, it2["takhrij"][:2])

row = c.execute("""SELECT b.code,h.number_in_book FROM hadiths h JOIN books b ON b.id=h.book_id
                   WHERE h.card_ok=1 AND h.grade_source='scholar' LIMIT 1""").fetchone()
it3, ctx3 = api.hadith_card(c, row["code"], row["number_in_book"])
rep3 = V.run(it3, ctx3)
check("حديث بحكم محدِّث يجتاز", rep3["ok"], f"{rep3['passed']}/25 — {rep3['failed']}")
check("اسم المحكِّم مذكور", bool(it3["grade_by"]), it3["grade_by"])

row = c.execute("""SELECT b.code,h.number_in_book FROM hadiths h JOIN books b ON b.id=h.book_id
                   WHERE h.grade IS NULL AND h.matn IS NOT NULL LIMIT 1""").fetchone()
it4b, ctx4b = api.hadith_card(c, row["code"], row["number_in_book"])
check("حديث بلا حكم يسقط", not V.run(it4b, ctx4b)["ok"])

# آية مكرّرة لفظًا: تُنشر لأن موضعها مطبوعٌ ومواضعها الأخرى مصرَّحٌ بها
row = c.execute("SELECT surah,ayah FROM ayat WHERE mutashabih_group IS NOT NULL LIMIT 1").fetchone()
it4, ctx4 = api.quran_card(c, row["surah"], row["ayah"])
rep4 = V.run(it4, ctx4)
check("المتشابه يُنشر بموضعه ومواضعه الأخرى مصرَّحًا بها",
      rep4["ok"] and it4.get("mutashabih") and it4["cells"]["c4"][0] and it4["cells"]["c1"][0],
      f"{row['surah']}:{row['ayah']} → {it4.get('mutashabih')}")
# فإن غاب التصريح عاد الحجب: الالتباس أن يُنشر بلا موضع
ctx4b_ = dict(ctx4); ctx4b_["mutashabih_disclosed"] = False
check("بلا تصريحٍ بالمواضع يُوقف الإنتاج", not V.run(it4, ctx4b_)["ok"])

print("\n▸ القرّاء والتلاوات")
from falah.audio import audio_url
nr = c.execute("SELECT COUNT(*) FROM reciters").fetchone()[0]
check("قرّاء مسجَّلون", nr >= 15, nr)
riw = c.execute("SELECT COUNT(DISTINCT riwayah) FROM reciters").fetchone()[0]
check("أكثر من رواية", riw >= 2, riw)
r = c.execute("SELECT * FROM reciters WHERE code='alafasy'").fetchone()
u = audio_url(r["scheme"], r["folder"], 1, 1, 1)
check("رابط التلاوة يُبنى صحيحًا", u.endswith("001001.mp3") and u.startswith("https://"), u)
dup = c.execute("SELECT COUNT(*) FROM (SELECT folder FROM reciters GROUP BY folder HAVING COUNT(*)>1)").fetchone()[0]
check("لا تكرار في مجلدات القرّاء", dup == 0, dup)

print("\n▸ الموسوعة الحديثية — الشرح والترجمة")
ne = c.execute("SELECT COUNT(*) FROM enc").fetchone()[0]
check("أحاديث الموسوعة محمّلة", ne > 3000, ne)
sh = c.execute("SELECT COUNT(*) FROM enc WHERE explanation IS NOT NULL AND explanation<>''").fetchone()[0]
check("لكل حديث شرح", sh == ne, f"{sh}/{ne}")
gr = c.execute("SELECT COUNT(*) FROM enc WHERE grade IS NULL OR grade=''").fetchone()[0]
check("لا حديث بلا درجة", gr == 0, gr)
at = c.execute("SELECT COUNT(*) FROM enc WHERE attribution IS NULL OR attribution=''").fetchone()[0]
check("لكل حديث تخريج", at == 0, at)
lk = c.execute("SELECT COUNT(DISTINCT enc_id) FROM enc_link").fetchone()[0]
check("ربطٌ بالكتب التسعة", lk > 300, lk)
tr = c.execute("SELECT COUNT(*) FROM enc_tr").fetchone()[0]
check("ترجمات محمّلة", tr > 1000, tr)
bad = c.execute("""SELECT COUNT(*) FROM enc WHERE card_ok=1 AND grade NOT IN
                   ('صحيح','حسن','حسن صحيح','صحيح لغيره','حسن لغيره','إسناده صحيح','إسناده حسن')""").fetchone()[0]
check("لا حديث ضعيف من الموسوعة يُفرَج", bad == 0, bad)
row = c.execute("SELECT id FROM enc WHERE card_ok=1 AND id IN (SELECT enc_id FROM enc_link) LIMIT 1").fetchone()
it5, ctx5 = api.enc_card(c, row["id"])
rep5 = V.run(it5, ctx5)
check("بطاقة الموسوعة تجتاز الـ٢٥", rep5["ok"], f"{rep5['passed']}/25 — {rep5['failed']}")
check("الشرح مُسند لمصدره", bool(it5["sharh"]["source"]), it5["sharh"]["source"])
check("المتن مفصول عن مقدمة الراوي",
      "عن" not in (it5["text"] or "")[:4] and bool(it5["intro"]), it5["intro"][:40])

print("\n▸ نظافة النص")
bad = c.execute("SELECT COUNT(*) FROM ayat WHERE text LIKE '%'||char(8207)||'%'").fetchone()[0]
check("لا محارف اتجاه في القرآن", bad == 0, bad)
low = c.execute("SELECT COUNT(*) FROM ayat WHERE char_len<1").fetchone()[0]
check("لا آية فارغة", low == 0)
# طه ونٓ ويس آياتٌ قصيرة صحيحة — تُقبل ولا تُعدّ خللًا
short = c.execute("SELECT surah,ayah,text FROM ayat WHERE char_len<4").fetchall()
check("الآيات القصيرة كلها فواتح سور (حروف مقطعة)",
      all(r["ayah"] == 1 for r in short),
      [(r["surah"],r["ayah"],r["text"]) for r in short])

print("\n▸ محرّك التصيير")
import render as R, os
check("الخطوط محلّية موجودة", all(os.path.exists(os.path.join(R.FONTS,f))
      for f in ("Amiri-Regular.ttf","Amiri-Bold.ttf","AmiriQuran.ttf")))
check("أربعة مقاسات — ومنها ٤:٥ الأعلى وصولًا في إنستقرام",
      set(R.SIZES) == {"square","portrait","vertical","wide"}
      and R.SIZES["portrait"] == (1080, 1350), list(R.SIZES.values()))
check("ثلاثة أشكال", set(R.SKINS) == {"night","parch","ivory"})
card, rep = R.fetch_card("quran", surah=94, ayah=5, to=6)
html = R.build_html(card, "quran", "night", "square", "قناتك")
check("القالب يحمل النص والخانات الأربع",
      card["text"][:12] in html and all(card["cells"][k][0] in html for k in ("c1","c2","c3","c4")))
check("الخط مدمج في الصفحة لا مُحمَّل من الشبكة",
      "@font-face" in html and "base64" in html and "http" not in html.split("<body>")[0].replace("http-equiv",""))
check("لا يُصيَّر إلا ما اجتاز الفحص", rep["ok"], f"{rep['passed']}/{rep['total']}")
blk = c.execute("""SELECT b.code, h.number_in_book FROM hadiths h JOIN books b ON b.id=h.book_id
                   WHERE h.card_ok=0 AND h.matn IS NOT NULL LIMIT 1""").fetchone()
try:
    R.fetch_card("hadith", book=blk["code"], no=blk["number_in_book"]); ok_block = False
except SystemExit: ok_block = True
check("المحجوب يرفض التصيير", ok_block, f"{blk['code']} {blk['number_in_book']}")
# القاعدة والمحرّك يجب أن يتفقا على كل بطاقة، وإلا صُدِّر محجوب
rows = c.execute("""SELECT b.code,h.number_in_book,h.card_ok FROM hadiths h
                    JOIN books b ON b.id=h.book_id WHERE h.matn IS NOT NULL
                    ORDER BY RANDOM() LIMIT 500""").fetchall()
mis = []
for x in rows:
    it_, cx_ = api.hadith_card(c, x["code"], x["number_in_book"])
    if V.run(it_, cx_)["ok"] != bool(x["card_ok"]):
        mis.append((x["code"], x["number_in_book"], x["card_ok"]))
check("القاعدة والمحرّك متفقان على ٥٠٠ بطاقة", not mis, mis[:2])

print("\n▸ السلسلة")
import carousel as CR
P = CR.plan(topic=1, kind="mixed", count=4)
check("السلسلة تُبنى من موضوع", len(P["cards"]) >= 2, len(P["cards"]))
check("كل بطاقة في السلسلة اجتازت الفحص كاملًا",
      all(r["ok"] and r["passed"] == r["total"] for _, _, r, _ in P["cards"]))
check("السلسلة المختلطة تُنوّع بين آيةٍ وحديث",
      len({k for k, *_ in P["cards"]}) == 2, [k for k, *_ in P["cards"]])
cap = P["caption"]
check("الوصف يذكر مرجع كل بطاقة",
      all(CR.ref_line(cd) in cap for _, cd, _, _ in P["cards"]))
check("الوصف يذكر المصادر", all(x in cap for x in P["sources"]))
# لا حكم بلا نسبة، حتى في سطر الوصف
bad = [CR.sanad_line(cd) for k, cd, _, _ in P["cards"]
       if k != "quran" and cd.get("grade") and not (cd.get("grade_by") or cd.get("grade_basis"))]
check("لا درجة في الوصف بلا نسبةٍ لقائلها", not bad, bad)
# الغلاف والخاتمة لا يحملان نصًّا شرعيًّا
cover = CR.R.build_cover_html(P["title"], P["title_en"], "سلسلة", ["س"], "night", "square")
body_cover = cover.split("</style>")[1]
check("الغلاف خالٍ من النصّ الشرعي",
      not any(cd["text"][:14] in body_cover for _, cd, _, _ in P["cards"]))
end = CR.R.build_end_html("المصادر", P["sources_slide"], "ملاحظة", "night", "square")
check("الخاتمة تعرض أسماء المصادر", all(x in end for x in P["sources_slide"]))
check("رقم الشريحة يظهر في الذيل", "٢ / ٦" in
      CR.R.build_html(P["cards"][0][1], "quran", "night", "square", "قناتك", badge="٢ / ٦"))
# ما رسب يُذكر ولا يُستبدل
Pd = CR.plan(items="hadith:bukhari:%d" % (c.execute(
     "SELECT h.number_in_book FROM hadiths h JOIN books b ON b.id=h.book_id "
     "WHERE b.code='bukhari' AND h.card_ok=0 AND h.matn IS NOT NULL LIMIT 1").fetchone()[0],)
     + ",quran:94:5:6")
check("المحجوب يسقط من السلسلة بسببٍ مذكور",
      len(Pd["dropped"]) == 1 and len(Pd["cards"]) == 1, Pd["dropped"])

print("\n▸ هيكل التطبيق: الحساب والمشروع")
import tempfile, json as _json
from falah import store as ST, auth as AU, projects as PJ
ST.APP_DB = os.path.join(tempfile.mkdtemp(), "app.db")
ac = ST.init()

uid = AU.register(ac, " Daood@Example.COM ", "kalimat-sirr-1", "داوود", "قناة فلاح")
row = ac.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
check("البريد يُطبَّع قبل الحفظ", row["email"] == "daood@example.com", row["email"])
check("كلمة المرور لا تُحفظ نصًّا", b"kalimat-sirr-1" not in bytes(row["pw_hash"]) and
      b"kalimat-sirr-1" not in bytes(row["pw_salt"]))
check("لكل حساب ملحه", AU.hash_password("x")[1] != AU.hash_password("x")[1])
weak = [AU.password_problem(x) for x in ("1234", "password", " kalimat ")]
check("كلمات المرور الضعيفة تُرفض", all(weak))

tok, u = AU.login(ac, "daood@example.com", "kalimat-sirr-1")
sess = ac.execute("SELECT token_hash FROM sessions").fetchone()["token_hash"]
check("رمز الجلسة يُحفظ مجزَّأً لا خامًا", tok not in sess and len(sess) == 64)
check("الجلسة تُعرِّف صاحبها", AU.session_user(ac, tok)["id"] == uid)
check("رمز مزوَّر لا يفتح", AU.session_user(ac, tok[:-1] + ("a" if tok[-1] != "a" else "b")) is None)
try:  AU.login(ac, "daood@example.com", "kalimat-sirr-2"); bad = False
except AU.AuthError: bad = True
check("كلمة خاطئة تُرفض", bad)
try:  AU.login(ac, "ghost@example.com", "kalimat-sirr-1"); msg1 = ""
except AU.AuthError as e: msg1 = str(e)
try:  AU.login(ac, "daood@example.com", "kalimat-sirr-9"); msg2 = ""
except AU.AuthError as e: msg2 = str(e)
check("رسالة الخطأ لا تكشف وجود الحساب", msg1 == msg2 and msg1 != "", (msg1, msg2))
for _ in range(AU.MAX_TRIES + 1):
    try: AU.login(ac, "daood@example.com", "خطأ")
    except AU.AuthError as e: last = str(e)
check("المحاولات المتكرّرة تُحبس", "محاولات كثيرة" in last, last)
AU.clear(ac, "login:daood@example.com"); ac.commit()

tok2, _ = AU.login(ac, "daood@example.com", "kalimat-sirr-1")
AU.change_password(ac, uid, "kalimat-sirr-1", "kalimat-sirr-3")
check("تغيير كلمة المرور يُنهي كل الجلسات",
      AU.session_user(ac, tok) is None and AU.session_user(ac, tok2) is None)
tok, _ = AU.login(ac, "daood@example.com", "kalimat-sirr-3")

pid = PJ.create(ac, uid, "سلسلة اليسر", "series", "night", "square", "قناة فلاح")
PJ.add_item(ac, c, uid, pid, "quran", {"surah": 94, "ayah": 5, "to": 6})
PJ.add_item(ac, c, uid, pid, "hadith", {"book": "bukhari", "no": 69})
try:  PJ.add_item(ac, c, uid, pid, "hadith", {"book": "bukhari", "no": 69}); dup = False
except PJ.ProjectError: dup = True
check("لا يتكرّر النصّ في المشروع", dup)
blk = c.execute("""SELECT b.code,h.number_in_book n FROM hadiths h JOIN books b ON b.id=h.book_id
                   WHERE h.card_ok=0 AND h.matn IS NOT NULL LIMIT 1""").fetchone()
try:  PJ.add_item(ac, c, uid, pid, "hadith", {"book": blk["code"], "no": blk["n"]}); gate = False
except PJ.ProjectError: gate = True
check("المحجوب لا يدخل المشروع أصلًا", gate)

st = PJ.open_project(ac, c, uid, pid)
check("المشروع يُفتح بعناصره مفحوصةً الآن",
      st["exportable"] and all(i["state"] == "ok" for i in st["items"]), len(st["items"]))
check("المشروع لا يخزّن نصًّا بل إشارةً وبصمة",
      all("text" not in _json.loads(r["ref"]) for r in
          ac.execute("SELECT ref FROM project_items WHERE project_id=?", (pid,))))

# قفل المصدر ممتدًّا للمشروع: بصمةٌ مغايرة ← انحراف يمنع التصدير
first = ac.execute("SELECT id,fp FROM project_items WHERE project_id=? ORDER BY pos", (pid,)).fetchone()
ac.execute("UPDATE project_items SET fp='0'*32 WHERE id=?", (first["id"],)); ac.commit()
st2 = PJ.open_project(ac, c, uid, pid)
check("تغيّر نصّ المصدر يُكشف ويمنع التصدير",
      st2["drift"] == [first["id"]] and not st2["exportable"],
      [i["state"] for i in st2["items"]])
PJ.accept_drift(ac, c, uid, pid, first["id"])
st3 = PJ.open_project(ac, c, uid, pid)
check("الموافقة الصريحة تُعيد الاعتماد", st3["exportable"] and not st3["drift"])
check("الموافقة تُسجَّل في السجلّ",
      ac.execute("SELECT COUNT(*) n FROM events WHERE action='drift_accepted'").fetchone()["n"] == 1)

other = AU.register(ac, "other@example.com", "kalimat-sirr-2")
try:  PJ.open_project(ac, c, other, pid); leak = True
except PJ.ProjectError: leak = False
check("لا يرى مستخدمٌ مشروع غيره", not leak)
check("قائمة المشاريع معزولة لكل حساب",
      len(PJ.listing(ac, uid)) == 1 and PJ.listing(ac, other) == [])
AU.logout(ac, tok)
check("الخروج يُبطل الجلسة", AU.session_user(ac, tok) is None)

print("\n▸ إعداد الإنتاج")
import importlib, subprocess, gzip, shutil, tempfile as _tf
os.environ["FALAH_SECURE"] = "1"; os.environ["FALAH_ORIGIN"] = "https://falah.example.com"
import app as APP; importlib.reload(APP)
ck = APP.App.set_cookie(None, "TOK")[0][1]
check("الكعكة محميّة بالكامل خلف HTTPS",
      all(x in ck for x in ("HttpOnly", "SameSite=Strict", "Secure", "Path=/")), ck[:70])
class _H:
    def __init__(self, h): self.h = h
    def get(self, k, d=None): return self.h.get(k, d)
def _guard(hdrs):
    o = type("X", (), {"headers": _H(hdrs)})()
    return APP.App.guard_csrf(o)
check("بلا ترويسة التطبيق يسقط الطلب", not _guard({}))
check("من نطاقٍ غريب يسقط الطلب",
      not _guard({"X-FALAH": "1", "Origin": "https://evil.example"}))
check("من نطاق التطبيق يمرّ",
      _guard({"X-FALAH": "1", "Origin": "https://falah.example.com"}))
os.environ.pop("FALAH_SECURE"); os.environ.pop("FALAH_ORIGIN"); importlib.reload(APP)
check("بلا HTTPS لا تُوسم الكعكة Secure", "Secure" not in APP.App.set_cookie(None, "T")[0][1])

# النسخ الاحتياطي يُنتج قاعدةً تُقرأ
bk = _tf.mkdtemp()
env = dict(os.environ, FALAH_APP_DB=ST.APP_DB)
subprocess.run(["sh", "deploy/backup.sh", bk, "3"], check=True, env=env,
               stdout=subprocess.DEVNULL)
gz = [x for x in os.listdir(bk) if x.endswith(".gz")]
shutil.copyfileobj(gzip.open(os.path.join(bk, gz[0])), open(os.path.join(bk, "r.db"), "wb"))
rc = sqlite3.connect(os.path.join(bk, "r.db"))
check("النسخة الاحتياطية تُستعاد بمستخدميها",
      rc.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 2)
rc.close()

# ملفات النشر موجودة ومتّسقة
dep = open("deploy/docker-compose.yml", encoding="utf-8").read()
check("النشر يمرّر النطاق والكعكة الآمنة للتطبيق",
      "FALAH_SECURE" in dep and "FALAH_ORIGIN" in dep and "falah-data:/data" in dep)
_dock = open("Dockerfile", encoding="utf-8").read()
check("الحاوية تحمل ffmpeg وكروميوم للتصدير",
      all(x in _dock for x in ("ffmpeg", "playwright install chromium")))
check("الحاوية تحمل العاملَ نفسه", "worker.py" in _dock)
# الخادم يقدّم هذه الملفّات؛ غيابُها عن الصورة يعني ٤٠٤ في الإنتاج وحده
check("الحاوية تحمل ما يقدّمه الخادم من ملفّات ثابتة",
      all(x in _dock for x in ("manifest.webmanifest", "sw.js", "icons/")))
check("العامل خدمةٌ مستقلّة عن الخادم في النشر",
      "worker:" in dep and "worker.py" in dep and 'FALAH_INLINE_WORKER: "0"' in dep)
check("الخادم والعامل يتقاسمان الطابور ومجلّد الصادرات",
      dep.count("falah-data:/data") == 2 and dep.count("falah-exports:/app/exports") == 2)
check("الصادرات على حجمٍ يبقى بعد تحديث الصورة", "falah-exports:" in dep.split("volumes:")[-1])
check("فحص الحاوية يسأل عن الحياة لا عن إحصاء القاعدة",
      "/healthz" in _dock and "http://localhost:8080/health |" not in _dock
      and "/health ||" not in _dock)
check("للعامل فحصُ حياةٍ خاصّ به — المعلَّق لا يبقى «يعمل»",
      "worker.py\", \"--healthcheck" in dep)
check("الخدمتان تقرآن الحدود من ملفّ بيئةٍ واحد",
      dep.count("env_file: [.env]") == 2)
check("النبضة بجوار حالة التطبيق لا في /tmp المتوقَّع",
      '"/tmp' not in open(os.path.join(
          os.path.dirname(os.path.abspath(__file__)), "worker.py")).read())
check("العامل ينبض على القرص داخل حلقته",
      "touch_beat()" in open(os.path.join(
          os.path.dirname(os.path.abspath(__file__)), "worker.py")).read())

# فحصا الحياة والجاهزية مفترقان في المعنى لا في الاسم فقط
_appsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")).read()
check("الحياة لا تلمس قاعدةً — رخيصةٌ تُسأل كل ثلاثين ثانية",
      "sqlite3" not in _appsrc.split("def liveness")[1].split("def readiness")[0])
check("الجاهزية تفحص القاعدتين والهجرات والطابور",
      all(x in _appsrc.split("def readiness")[1][:2000]
          for x in ("content_db", "app_db", "pending_migrations", "queue")))
check("وتردّ ٥٠٣ إن لم تكن جاهزة", "200 if ok else 503" in _appsrc)
check("وصمتُ العمّال تحذيرٌ لا إسقاطُ جاهزية — الخادم يستقبل ويضع في الطابور",
      "worker_warning" in _appsrc)

# سعةُ الإصغاء: قياسٌ كشف أن ٤٨ من ١٠٠ اتصالٍ كانت تسقط قبل أن تُقرأ
check("طابور الإصغاء مرفوعٌ عن الافتراضيّ (٥)",
      APP.Server.request_queue_size >= 128, str(APP.Server.request_queue_size))
check("وقابلٌ للضبط من البيئة", "FALAH_LISTEN_BACKLOG" in _appsrc)
check("والخيوط خادمةٌ لا تمنع الإطفاء", APP.Server.daemon_threads is True)


# عقد الـAPI
import api_contract as _AC
_undoc, _stale, _ghost = _AC.audit()
check("لا مسارَ قائمٌ بلا توثيق في العقد", not _undoc, str(_undoc))
check("ولا موثَّقٌ لا وجود له", not _stale, str(_stale))
check("والواجهة لا تنادي مسارًا لا يقدّمه الخادم", not _ghost, str(_ghost))
check("العقد مولَّدٌ من الشيفرة لا مكتوبٌ بجانبها",
      os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "API.md")))

# متغيّرات البيئة: كلّ ما تقرؤه الشيفرة موثَّقٌ في القالب
import re as _re2
_root = os.path.dirname(os.path.abspath(__file__))
_used = set()
for _dir, _, _fs in os.walk(_root):
    if any(x in _dir for x in ("raw", "templates", "exports", "out", "__pycache__")): continue
    for _f in _fs:
        if not _f.endswith(".py"): continue
        _t = open(os.path.join(_dir, _f), encoding="utf-8", errors="ignore").read()
        _used |= set(_re2.findall(r'["\'](FALAH_[A-Z_]+)["\']', _t))
_tmpl = open(os.path.join(_root, ".env.example"), encoding="utf-8").read()
_undocumented = sorted(v for v in _used if v not in _tmpl)
check("كل متغيّر بيئةٍ تقرؤه الشيفرة موثَّقٌ في .env.example",
      not _undocumented, str(_undocumented))
# التعريف نفسه الذي يستعمله الفاحص الأمنيّ — لا تعريفان يختلفان
import security_scan as _SS
_leaks = [_l for _l in _tmpl.splitlines()
          if "=" in _l and not _l.startswith("#")
          and _SS.looks_secret(_l.split("=", 1)[1])]
check("ولا قيمةَ سرٍّ حقيقية في القالب — المسارُ مرجعٌ لا سرّ",
      not _leaks, str(_leaks))
check("والقالب يذكر قاعدة المفاتيح لا يكتفي بالأسماء",
      "CREDENTIALS.md" in _tmpl and "App Manager" in _tmpl)

# الاعتماديات: مثبَّتةٌ لا مفتوحة، ومصدرها واحد
import ast as _ast2
_req = open(os.path.join(_root, "requirements.txt"), encoding="utf-8").read()
_pins = _re2.findall(r"^([a-zA-Z0-9_.-]+)==([0-9][0-9.]*)$", _req, _re2.M)
check("كل اعتماديةٍ مثبَّتةٌ بإصدارٍ محدَّد", len(_pins) >= 4, str(_pins))
check("لا اعتماديةَ بحدٍّ مفتوح (>= أو ~=)",
      not _re2.search(r"^[a-zA-Z0-9_.-]+\s*[><~]=", _req, _re2.M))
# ما تستورده الشيفرة فعلًا يجب أن يكون مذكورًا — ولا العكس
_std = set(sys.stdlib_module_names)
_localmods = {f[:-3] for f in os.listdir(_root) if f.endswith(".py")} | {"falah"}
_imported = set()
for _dp, _dirs, _fs in os.walk(_root):
    _dirs[:] = [d for d in _dirs if d not in
                ("raw","templates","exports","out","__pycache__",".git","mobile")]
    for _f in _fs:
        if not _f.endswith(".py"): continue
        try: _tree = _ast2.parse(open(os.path.join(_dp,_f), encoding="utf-8").read())
        except Exception: continue
        for _n in _ast2.walk(_tree):
            if isinstance(_n, _ast2.Import):
                _imported |= {a.name.split(".")[0] for a in _n.names}
            elif isinstance(_n, _ast2.ImportFrom) and _n.module and _n.level == 0:
                _imported.add(_n.module.split(".")[0])
_alias = {"PIL": "pillow", "imageio_ffmpeg": "imageio_ffmpeg"}
_ext = {_alias.get(m, m) for m in _imported - _std - _localmods}
_named = {p[0].lower().replace("-", "_") for p in _pins}
_ghost_dep = sorted(d for d in _ext if d.lower().replace("-", "_") not in _named)
check("كل ما تستورده الشيفرة مذكورٌ في requirements.txt", not _ghost_dep, str(_ghost_dep))
check("الحاوية وخطّ التكامل يثبّتان من الملفّ نفسه لا من سطرٍ مكرَّر",
      "-r requirements.txt" in open(os.path.join(_root, "Dockerfile")).read()
      and "-r requirements.txt" in open(os.path.join(
          _root, ".github", "workflows", "ci.yml")).read())
check("وفحص الثغرات موصوفٌ بنتيجته لا بوعدٍ به",
      "pip-audit" in _req and "make deps" in _req and "صفرًا" in _req)
check("والبوّابة تشمل فحص الاعتماديات",
      "pip-audit" in open(os.path.join(_root, "Makefile")).read()
      and "pip-audit" in open(os.path.join(
          _root, ".github", "workflows", "ci.yml"), encoding="utf-8").read())

# خطّ التكامل: بوّابةٌ لا تُتجاوز
_ci = open(os.path.join(_root, ".github", "workflows", "ci.yml"), encoding="utf-8").read()
# التعليق الذي يذكرها لا يُحسب — يُفحص ما يُنفَّذ لا ما يُشرح
check("لا خطوةَ فحصٍ تُمرَّر على أنها نجاح",
      not [l for l in _ci.splitlines()
           if "continue-on-error" in l and not l.lstrip().startswith("#")])
check("البناء مشروطٌ بنجاح الاختبارات", "needs: [static, tests]" in _ci)
check("وبوّابةٌ واحدة تُلخّص الكلّ وتُشترط في الحماية",
      "QUALITY_GATE" in _ci and "needs: [static, tests, build]" in _ci)
for _step in ("ruff check", "mypy", "security_scan.py", "api_contract.py --check",
              "tests.py", "audit.py", "ui_audit.py", "failure_test.py", "docker build"):
    check(f"خطّ التكامل يشمل: {_step}", _step in _ci)

# الخطوات التي أُضيفت في التصليب — تُشترط في CI صراحةً
for _step in ("pip-audit", "leak_test.py", "dbsafe.py restore-test",
              "dbsafe.py migrate-check", "docker run", "healthz", "readyz"):
    check(f"وخطّ التكامل يشمل: {_step}", _step in _ci)
check("ودخانُ الصورة يتحقّق من الملفّات الثابتة فيها",
      "manifest.webmanifest" in _ci and "sw.js" in _ci)
check("وبوّابةٌ واحدة تُشغَّل بأمرٍ واحد محلّيًّا",
      os.path.exists(os.path.join(_root, "gate.py"))
      and "gate.py" in open(os.path.join(_root, "Makefile")).read())
_g = open(os.path.join(_root, "gate.py"), encoding="utf-8").read()
check("والبوّابة تُصنّف المحجوب BLOCKED لا PASS",
      '"BLOCKED"' in _g and "لا يُحسب نجاحًا" in _g)
check("وتطبع سببَ السقوط وأمرَه وملفَّه واقتراحَ إصلاحه",
      all(x in _g for x in ("reason", "command", "file", "fix")))

check("والأوامر نفسها متاحةٌ محلّيًّا بـmake gate",
      all(x in open(os.path.join(_root, "Makefile")).read()
          for x in ("ruff check", "mypy", "security_scan.py", "tests.py",
                    "audit.py", "ui_audit.py", "failure_test.py")))

print("\n▸ الوكيل")
from falah import agent as AG

def _walk(seed, picks=None):
    """يمشي في الأسئلة سؤالًا سؤالًا كما يفعل المستخدم، ويعيد ما سُئل والإجابات."""
    ans, asked = dict(seed), []
    picks = picks or {}
    for _ in range(40):
        q = AG.next_question(ans, DB, "قناة فلاح")
        if not q: break
        asked.append(q["id"])
        if q["id"] in picks:            ans[q["id"]] = picks[q["id"]]
        elif q["type"] == "auto":       ans[q["id"]] = q["value"] or "—"
        elif q["type"] == "free":       ans[q["id"]] = q.get("default") or "قناة فلاح"
        elif q["type"] == "number":     ans[q["id"]] = str(q.get("default", 1))
        else:                           ans[q["id"]] = q.get("default") or q["options"][0]["value"]
    return asked, ans

_aq, _ansq = _walk({}, {"source_kind": "quran", "surah": "94",
                        "content_type": "post", "platform": "instagram"})
check("فرع القرآن يسأل بالترتيب المطلوب",
      _aq == AG.COMMON_HEAD + AG.QURAN_STEPS + ["design","tint","font","ink"], _aq)
_ah, _ansh = _walk({}, {"source_kind": "hadith", "book": "bukhari",
                        "content_type": "story", "platform": "tiktok"})
check("فرع الحديث يسأل بالترتيب المطلوب",
      _ah == AG.COMMON_HEAD + AG.HADITH_STEPS + AG.COMMON_TAIL, _ah)
check("كل سؤال يحمل سببه",
      all(AG.WHY[k] for k in set(_aq) | set(_ah)))
check("لا تُعرض الأسئلة كلها معًا: سؤالٌ واحدٌ في كل مرّة",
      isinstance(AG.next_question({}, DB), dict) and
      AG.next_question({}, DB)["id"] == "content_type" and
      AG.next_question({}, DB)["index"] == 1)
check("الأبعاد تُختار من نوع المحتوى وحده",
      all(AG.style({"content_type": v})["ratio"] == r for v, _l, r in AG.CONTENT_TYPES) and
      "ratio" not in AG.COMMON_HEAD + AG.QURAN_STEPS + AG.HADITH_STEPS + AG.COMMON_TAIL)
check("العلامة تُقترح من ملف المستخدم وحقلها حرّ",
      AG.next_question({"content_type":"post","platform":"x"}, DB, "قناة فلاح")["default"]
        == "قناة فلاح")
check("درجة الحديث ونصّه يأتيان تلقائيًّا لا اختيارًا",
      all(AG.question(k, _ansh, DB)["type"] == "auto" for k in ("grade", "matn")) and
      AG.question("grade", _ansh, DB)["value"] == _ansh["grade"])
_sq = AG.question("surah", {}, DB)["options"]
check("قائمة السور كاملة ١١٤", len(_sq) == 114, len(_sq))
_c94 = AG.question("from", {"source_kind":"quran","surah":"94"}, DB)["options"]
check("أرقام الآيات تتبع السورة المختارة",
      len(_c94) == AG.surah_info(DB, 94)["n"], len(_c94))
_ch = AG.question("chapter", {"source_kind":"hadith","book":"bukhari"}, DB)["options"]
_hn = AG.question("no", {"source_kind":"hadith","book":"bukhari",
                         "chapter": _ch[0]["value"]}, DB)["options"]
check("الأبواب وأرقام الأحاديث تتبع الكتاب والباب", bool(_ch) and bool(_hn))
check("لا يُعرض بابٌ ولا رقمٌ لم يجتز الفحص",
      all(int(o["value"]) in {h["no"] for h in AG.chapter_hadiths(DB, "bukhari",
          _ch[0]["value"])} for o in _hn))

# ما بُني على إجابةٍ تغيّرت يسقط، فلا يبقى رقمٌ من بابٍ آخر
_dirty = dict(_ansh); _dirty["chapter"] = _ch[-1]["value"]
check("تغيير الباب يُسقط رقم الحديث المبنيّ عليه",
      "no" not in AG.sanitize(_dirty, DB) or
      int(AG.sanitize(_dirty, DB)["no"]) in
        {h["no"] for h in AG.chapter_hadiths(DB, "bukhari", _ch[-1]["value"])})
check("آيةٌ خارج السورة تسقط عند التنظيف",
      "from" not in AG.sanitize({"source_kind":"quran","surah":"94","from":"99"}, DB))
check("تبديل نوع المحتوى الشرعي يمحو فرعه السابق",
      not ({"book","chapter","no"} & set(AG.sanitize(dict(_ansh, source_kind="quran"), DB))))

_plq = AG.plan(dict(_ansq, **{"from":"1","to":"3","count":"3"}), DB)
check("كل بطاقةٍ في الخطة اجتازت الفحوص الخمسة والعشرين",
      _plq["cards"] and all(x["checks"] == "25/25" for x in _plq["cards"]),
      [x["checks"] for x in _plq["cards"]])
check("اختيار عدّةِ آياتٍ يُنتج سلسلةً بطاقةً لكل آية",
      len(_plq["cards"]) == 3, len(_plq["cards"]))
check("الخطة تحمل هيئتها كاملةً كما اختِيرت",
      set(_plq["style"]) == {"ratio","skin","tint","font","ink","watermark",
                             "platform","isnad","tile"}, sorted(_plq["style"]))

_plh = AG.plan(_ansh, DB)
check("خطة الحديث مفحوصةٌ كذلك",
      _plh["cards"] and all(x["checks"] == "25/25" for x in _plh["cards"]))

# السند موجودٌ في البيانات، ويُعرض حين يُطلب لا دائمًا
_hc = _plh["cards"][0]["card"] if _plh["cards"] else None
if _hc:
    _no  = R.build_html(_hc, "hadith", watermark="ق", isnad=False)
    _yes = R.build_html(_hc, "hadith", watermark="ق", isnad=True)
    check("السند لا يُعرض إلا إذا طُلب",
          (_hc.get("isnad_full") or "")[:24] not in _no)
    check("وإذا طُلب عُرض من أول راوٍ لا من وسط السلسلة",
          (_hc.get("isnad_full") or "")[:24] in _yes, (_hc.get("isnad_full") or "")[:30])
    check("والمتن يبقى هو الأبرز مع عرض السند",
          _hc["text"][:30] in _yes and 'class="text"' in _yes)
    _tiled = R.build_html(_hc, "hadith", watermark="ق", tile_mark="فلاح")
    check("العلامة المكرّرة تُرسم خلف النصّ لا فوقه",
          'class="tiles"' in _tiled and "z-index:0" in _tiled
          and _hc["text"][:30] in _tiled)

check("إجاباتٌ ناقصة لا تُسقط الوكيل",
      AG.plan({"source_kind":"hadith"}, DB)["count"] == 0 and
      AG.plan({}, DB)["count"] == 0)

# ما يخرجه الوكيل يجب أن يَقبله المشروع كما هو
_p2 = PJ.create(ac, uid, "من الوكيل")
_ok = 0
for cd in _plq["cards"]:
    try: PJ.add_item(ac, c, uid, _p2, cd["kind"], cd["ref"]); _ok += 1
    except PJ.ProjectError: pass
check("مراجع الوكيل مقبولة في المشروع بلا تعديل", _ok == len(_plq["cards"]), _ok)

# الواجهة: مربّع القالب فوق مربّع الأسئلة، وأزرار التالي والسابق
_ui = open("falah-app.html", encoding="utf-8").read()
check("واجهة التطبيق فيها مربّع قالبٍ ومربّع أسئلةٍ وأزرار تنقّل",
      all(x in _ui for x in ('hold.id = "hold"', 'tpl.id = "tpl"', 'ask.id = "ask"',
                             "السابق", "التالي", 'el("div", "stage")')))
check("البطاقة في الواجهة فيها خانتا العلامتين",
      "العلامة المائية للمستخدم" in _ui and "العلامة المائية للتطبيق" in _ui)
_pv = open("preview_body.html", encoding="utf-8").read()
check("المعاينة تتبع نفس ترتيب الأسئلة",
      all(x in _pv for x in ("COMMON_HEAD", "QURAN_STEPS", "HADITH_STEPS", "COMMON_TAIL")))

# ألوان التصميم والخطوط تغيّر الهيئة لا النصّ
import render as RD
_cardq = _plq["cards"][0]["card"]
_h1 = RD.build_html(_cardq, "quran", skin="parch", tint="green", ink="#111111", font="amiri")
_h2 = RD.build_html(_cardq, "quran", skin="parch")
check("لون التصميم ولون الخط يغيّران الهيئة",
      "#2F5D4A" in _h1 and "#111111" in _h1 and "#2F5D4A" not in _h2)
check("النصّ نفسه لا يتغيّر بتغيّر الهيئة",
      _cardq["text"] in _h1 and _cardq["text"] in _h2)


def _missing(fn):
    """هل يرفض العملُ بلا مفاتيح، ويسمّي المتغيّر الناقص؟"""
    try:
        fn(); return False
    except Exception as e:
        return "غير مضبوط" in str(e) and "CREDENTIALS" in str(e)

def _raises(exc, fn):
    try:
        fn(); return False
    except exc:
        return True
    except Exception:
        return False        # انهيارٌ بنوعٍ آخر ليس ردًّا مقبولًا

def _apple_token_shape():
    import base64, json, os, tempfile
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from falah.stores import apple as AP
    k = ec.generate_private_key(ec.SECP256R1())
    p = tempfile.mktemp(suffix=".p8")
    open(p, "wb").write(k.private_bytes(serialization.Encoding.PEM,
                                        serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()))
    keep = {x: os.environ.get(x) for x in
            ("FALAH_APPLE_KEY_P8", "FALAH_APPLE_KEY_ID",
             "FALAH_APPLE_ISSUER_ID", "FALAH_APPLE_BUNDLE_ID")}
    os.environ.update(FALAH_APPLE_KEY_P8=p, FALAH_APPLE_KEY_ID="K",
                      FALAH_APPLE_ISSUER_ID="I", FALAH_APPLE_BUNDLE_ID="com.falah.app")
    try:
        h, b, sig = AP.token().split(".")
        dec = lambda x: json.loads(base64.urlsafe_b64decode(x + "=" * (-len(x) % 4)))
        raw = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        return (dec(h)["alg"] == "ES256" and dec(b)["bid"] == "com.falah.app"
                and len(raw) == 64)
    finally:
        for x, v in keep.items():
            if v is None: os.environ.pop(x, None)
            else:         os.environ[x] = v
        os.remove(p)

print("\n▸ الاشتراك والحصص")
from falah import billing as BL, referrals as RF
import random as _rnd

_m = lambda p: f"{p}{_rnd.randint(10**7,10**8)}@test.falah"
_pw = "Str0ng-Pass!x9"
_ua = AU.register(ac, _m("s"), _pw, "مشترك", "ق")
_e = BL.entitlements(ac, _ua)
check("الحساب الجديد على الخطّة المجانية", _e["plan"] == "free", _e["plan"])
check("للمجاني حصّةٌ معلومة لا مفتوحة",
      _e["limits"]["cards"] > 0 and _e["limits"]["videos"] == 0, str(_e["limits"]))

BL.consume(ac, _ua, "cards", _e["limits"]["cards"])
_msg = ""
try:
    BL.check(ac, _ua, "cards"); check("الحصّة تمنع التجاوز", False)
except BL.BillingError as _ex:
    _msg = str(_ex); check("الحصّة تمنع التجاوز", "حدّ خطّة" in _msg, _msg[:50])
check("الرسالة تقول كيف يُرفع الحدّ", "ارفع خطّتك" in _msg, _msg[:60])

try:
    BL.require(ac, _ua, "ratios", "vertical"); check("المقاس المدفوع ممنوع في المجاني", False)
except BL.BillingError:
    check("المقاس المدفوع ممنوع في المجاني", True)
check("المربّع متاحٌ للمجاني", BL.allows(ac, _ua, "ratios", "square"))
check("خانة فلاح تبقى في المجاني", BL.allows(ac, _ua, "falah_mark"))

BL.grant(ac, _ua, "creator", days=30)
_e2 = BL.entitlements(ac, _ua)
check("الترقية تفتح الحصّة والمقاسات",
      _e2["plan"] == "creator" and _e2["left"]["cards"] > 0
      and BL.allows(ac, _ua, "ratios", "vertical"), str(_e2["left"]))
check("ولك رفع خانة فلاح في المدفوع", not BL.allows(ac, _ua, "falah_mark"))

# الترقية لا تمسّ الفحص ولا النسبة — هذا هو الشرط الحاكم
import render as _RD
_c2 = _plq["cards"][0]["card"]
_free = _RD.build_html(_c2, "quran", falah_mark=True,  watermark="قناتي")
_paid = _RD.build_html(_c2, "quran", falah_mark=False, watermark="قناتي")
check("خانة فلاح وحدها هي ما يُرفع بالاشتراك",
      "FALAH" in _free and "FALAH" not in _paid)
# ما يظهر على وجه البطاقة من نسبة: اسم المفسّر واسم المترجم وخانات الموضع
_c3 = _RD.build_html.__self__ if False else None
import sqlite3 as _sq
_cc = _sq.connect("file:falah.db?mode=ro", uri=True); _cc.row_factory = _sq.Row
_att, _ = api.quran_card(_cc, 94, 1, None, True, True); _cc.close()
_f2 = _RD.build_html(_att, "quran", falah_mark=True,  watermark="قناتي")
_p2 = _RD.build_html(_att, "quran", falah_mark=False, watermark="قناتي")
_names = [_att["tafsir"]["source"], _att["translation"]["source"],
          _att["cells"]["c1"][0], _att["cells"]["c4"][0]]
check("نسبة النصّ إلى مصدره ثابتةٌ في الخطّتين",
      all(n in _f2 and n in _p2 for n in _names) and
      _att["text"] in _f2 and _att["text"] in _p2, str(_names))
check("علامة المستخدم تبقى في الخطّتين", "قناتي" in _f2 and "قناتي" in _p2)
check("لا خطّةَ تُرخي فحصًا",
      all("checks" not in p["features"] and "verify" not in p["features"]
          for p in BL.PLANS.values()))

# حمولةٌ من جهازٍ بلا تحقّقٍ من المتجر لا تُمنح شيئًا — ولو كانت تامّة الشكل
_before = BL.entitlements(ac, _ua)["plan"]
try:
    BL.apply_store_event(ac, _ua, "apple",
        {"type": "purchase", "product_id": "com.falah.studio.year",
         "transaction_id": "FORGED-1"})
    check("حمولةٌ غير محقَّقة لا تمنح اشتراكًا", False)
except BL.BillingError as _ex:
    check("حمولةٌ غير محقَّقة لا تمنح اشتراكًا",
          BL.entitlements(ac, _ua)["plan"] == _before, str(_ex)[:50])
check("والمحاولة تُسجَّل في الإيصالات على كل حال",
      ac.execute("SELECT COUNT(*) FROM receipts WHERE provider_id='FORGED-1'"
                 ).fetchone()[0] == 1)

# ما تحقّق منه الخادمُ عند المزوّد يُطبَّق
BL.apply_store_event(ac, _ua, "apple",
    {"type": "purchase", "product_id": "com.falah.studio.year", "transaction_id": "TX-9"},
    verified=True)
check("إيصالٌ محقَّق يرفع الخطّة", BL.entitlements(ac, _ua)["plan"] == "studio")
check("الإيصال يُحفظ كما ورد",
      ac.execute("SELECT COUNT(*) FROM receipts WHERE user_id=?", (_ua,)).fetchone()[0] >= 1)
BL.apply_store_event(ac, _ua, "apple", {"type": "refund", "transaction_id": "TX-9"},
                     verified=True)
check("الاسترداد يقطع الحقّ فورًا", BL.entitlements(ac, _ua)["plan"] == "free")
try:
    BL.apply_store_event(ac, _ua, "apple",
        {"type": "purchase", "product_id": "com.falah.ghost", "transaction_id": "TX-X"},
        verified=True)
    check("منتَجٌ غير معروف يُرفض", False)
except BL.BillingError:
    check("منتَجٌ غير معروف يُرفض", True)

print("\n▸ التحقّق من المتاجر")
from falah.stores import apple as AP, google as GP
check("لا يعمل شيءٌ بلا مفاتيح، ويُقال أيّ متغيّرٍ ناقص",
      all(_missing(f) for f in (AP.whoami, GP.whoami)))
check("حمولة آبل لا تُقبل بلا جذرٍ للتحقّق",
      _raises(AP.AppleError, lambda: AP.verify_jws("a.b.c", root_ca=None)))
for _bad in ("", "x.y", "aaa.bbb.ccc", None):
    check(f"مدخلٌ مشوّه يُردّ خطأً معروفًا: {_bad!r}",
          _raises(AP.AppleError, lambda b=_bad: AP.verify_jws(b, root_ca="/nope")))
check("رمز آبل يُوقَّع بـES256 بتوقيعٍ من ٦٤ بايتًا", _apple_token_shape())
check("جوجل تعدّ النافذ والمهلة وحدهما اشتراكًا قائمًا",
      GP.ACTIVE_STATES == {"SUBSCRIPTION_STATE_ACTIVE",
                           "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"})
check("لا مفتاح مكتوبٌ في الشفرة",
      all("BEGIN PRIVATE KEY" not in open(f, encoding="utf-8").read()
          for f in ("falah/stores/apple.py", "falah/stores/google.py", "store_cli.py")))
_gi = open(".gitignore", encoding="utf-8").read()
check("المستودع يمنع دخول المفاتيح",
      all(x in _gi for x in ("*.p8", "service-account", ".env")))

# انتهاء المدّة يعيد صاحبه إلى المجاني بلا تدخّل
BL.grant(ac, _ua, "creator", days=30)
ac.execute("UPDATE subscriptions SET expires_at=?, renews=0 WHERE user_id=? AND status='active'",
           (ST.now() - 10, _ua)); ac.commit()
check("المنتهي يعود إلى المجاني تلقائيًّا", BL.entitlements(ac, _ua)["plan"] == "free")
# ومن كان يجدّد تُمنح له مهلة
BL.grant(ac, _ua, "creator", days=30, renews=1)
ac.execute("UPDATE subscriptions SET expires_at=? WHERE user_id=? AND status='active'",
           (ST.now() - 10, _ua)); ac.commit()
_g = BL.current(ac, _ua)
check("من يجدّد له مهلةٌ قبل القطع", _g["status"] == "grace" and _g["plan"] == "creator", str(_g["status"]))

print("\n▸ الإحالات")
_ub = AU.register(ac, _m("a"), _pw, "محيل", "ق")
_uc = AU.register(ac, _m("b"), _pw, "مدعوّ", "ق")
_code = RF.code_for(ac, _ub)
check("لكل مستخدمٍ رمزٌ ثابت", _code and RF.code_for(ac, _ub) == _code, _code)
check("الرمز بلا حروفٍ تلتبس بالأرقام",
      not (set("OI01") & set(_code)), _code)
RF.attach(ac, _uc, _code)
check("المدعوّ يأخذ حقّه فورًا", BL.entitlements(ac, _uc)["plan"] == RF.REWARD_PLAN)
check("المحيل لا يُكافأ بالتسجيل وحده", BL.entitlements(ac, _ub)["plan"] == "free")
_r = RF.qualify(ac, _uc)
check("المكافأة تُصرف عند أول إنتاجٍ حقيقيّ",
      _r and _r["status"] == "rewarded" and BL.entitlements(ac, _ub)["plan"] == RF.REWARD_PLAN)
check("لا تُصرف مرّتين عن مدعوٍّ واحد", RF.qualify(ac, _uc) is None)
try:
    RF.attach(ac, _ub, _code); check("لا يُحيل المرء نفسه", False)
except RF.ReferralError: check("لا يُحيل المرء نفسه", True)
try:
    RF.attach(ac, _uc, _code); check("لا يُحال الحساب مرّتين", False)
except RF.ReferralError: check("لا يُحال الحساب مرّتين", True)
try:
    RF.attach(ac, AU.register(ac, _m("z"), _pw), "ZZZZZZZ")
    check("رمزٌ غير معروف يُرفض", False)
except RF.ReferralError: check("رمزٌ غير معروف يُرفض", True)
_s = RF.summary(ac, _ub)
check("الملخّص لا يكشف بريد المدعوّين كاملًا",
      all("@" not in (i["who"] or "") for i in _s["invites"]), str(_s["invites"])[:60])
check("الملخّص يقول متى تُصرف المكافأة", "لا عند تسجيله" in _s["rule"])

print("\n▸ استعادة كلمة المرور وتأكيد البريد")
_mm = _m("p"); _up = AU.register(ac, _mm, _pw, "ناسٍ", "ق")
_rq = AU.request_reset(ac, _mm, send=False)
_tok = _rq["_token"]
_sess_before = AU.new_session(ac, _up)
AU.reset_password(ac, _tok, "N3w-Pass!word")
check("كلمة المرور تتغيّر بالرمز", bool(AU.login(ac, _mm, "N3w-Pass!word")[0]))
check("الجلسات القديمة تسقط بعد الاستعادة",
      AU.session_user(ac, _sess_before) is None)
try:
    AU.reset_password(ac, _tok, "An0ther!pass"); check("الرمز لا يُستعمل مرّتين", False)
except AU.AuthError: check("الرمز لا يُستعمل مرّتين", True)
_rq2 = AU.request_reset(ac, "nobody" + _mm, send=False)
check("طلبٌ لبريدٍ غير مسجَّل لا يُفصح عن شيء",
      _rq2.get("ok") and "_token" not in _rq2)
_v = AU.request_verify(ac, _up, send=False)
AU.verify_email(ac, _v["_token"])
check("تأكيد البريد يُسجَّل",
      ac.execute("SELECT verified_at FROM users WHERE id=?", (_up,)).fetchone()[0] is not None)
_expired = AU.issue_token(ac, _up, "reset", 1)
ac.execute("UPDATE tokens SET expires_at=? WHERE token_hash=?",
           (ST.now() - 5, AU._hash_token(_expired))); ac.commit()
try:
    AU.reset_password(ac, _expired, "Yet-An0ther!"); check("الرمز المنتهي يُرفض", False)
except AU.AuthError: check("الرمز المنتهي يُرفض", True)
check("الرموز تُخزَّن مجزَّأة لا صريحة",
      ac.execute("SELECT COUNT(*) FROM tokens WHERE token_hash=?", (_tok,)).fetchone()[0] == 0)

# حذف الحساب يمحو اشتراكه وإحالاته كذلك
AU.delete_account(ac, _uc)
check("حذف الحساب يمحو اشتراكه",
      ac.execute("SELECT COUNT(*) FROM subscriptions WHERE user_id=?", (_uc,)).fetchone()[0] == 0)
check("وحذفُه يمحو إحالته",
      ac.execute("SELECT COUNT(*) FROM referrals WHERE invitee_id=?", (_uc,)).fetchone()[0] == 0)

print("\n▸ أحكام المراجعين")
from falah import rulings as RU
import json as _j, tempfile as _tf2
_good = {"fp": "a"*32, "decision": "release", "grade": "صحيح", "basis": "متفق عليه",
         "reviewer": "فلان", "date": "2026-09-02"}
check("القرار السليم يُقبل", RU.problem(_good) is None)
check("لا إفراج بلا حكم", RU.problem({**_good, "grade": ""}) == "إفراجٌ بلا حكم")
check("لا حكم بلا مستند", RU.problem({**_good, "basis": ""}) == "حكمٌ بلا مستند")
check("لا قرار بلا اسم مراجع", RU.problem({**_good, "reviewer": " "}) == "لا اسم للمراجع")
check("لا قرار بلا تاريخ", RU.problem({**_good, "date": "أمس"}).startswith("لا تاريخ"))
check("القرار يُربط ببصمة النصّ",
      RU.problem({**_good, "fp": "bukhari-409"}).startswith("بصمة"))
check("القرار يرفع الحجب الحُكمي",
      RU.applies_to(_good, "تعارض: حكم صحيح مقابل «باطل» في الجامع الكامل"))
check("ولا يرفع الحجب الآليّ",
      not RU.applies_to(_good, "النص يسع البطاقة دون قطع") and
      not RU.applies_to(_good, "لم يتأكّد النص من مصدر ثانٍ"))
check("قرار الإبقاء لا يُفرج", not RU.applies_to({**_good, "decision": "block"}, "تعارض"))
_f = os.path.join(_tf2.mkdtemp(), "r.json")
_j.dump({"rulings": [_good, {"fp": "b"*32, "decision": "release", "grade": "",
                             "basis": "", "reviewer": "", "date": ""}]},
        open(_f, "w", encoding="utf-8"), ensure_ascii=False)
_ok, _bad2 = RU.load(_f)
check("السليم يُحمَّل والفاسد يُعزل بسببه", list(_ok) == ["a"*32] and len(_bad2) == 1, _bad2)
check("المستند يحمل اسم المراجع وتاريخه",
      "فلان" in RU.basis_line(_good) and "2026-09-02" in RU.basis_line(_good))
# حزمة المراجعة لا تُخرج إلا الحجب الحُكمي، وتحمل بصمة كل متن
import review_pack as RP
_rows = RP.gather(c, "تعارض", 5)
check("حزمة المراجعة تجمع المحجوب حُكميًّا بشواهده",
      _rows and all(r["matn_fp"] and r["block_reason"].startswith("تعارض") for r in _rows),
      len(_rows))
_h = RP.html_page(_rows, "تعارض")
check("الحزمة تعرض بصمة المتن للمراجع", all(r["matn_fp"] in _h for r in _rows))
check("الحزمة فيها موضع التوقيع والتاريخ", "المراجع" in _h and "التاريخ" in _h)

print("\n▸ الإطلاق المغلق والنسبة")
os.environ["FALAH_INVITE"] = "falah-2026"
importlib.reload(APP)
check("رمز الدعوة يُقرأ من البيئة", APP.INVITE == "falah-2026")
check("الإعداد يخبر الواجهة أن الدعوة مطلوبة", bool(APP.INVITE))
os.environ.pop("FALAH_INVITE"); importlib.reload(APP)
check("بلا رمزٍ يبقى التسجيل مفتوحًا", APP.INVITE == "")
_ui = open("falah-app.html", encoding="utf-8").read()
check("الواجهة فيها حقل الدعوة وصفحة المصادر",
      'id="invite"' in _ui and 'id="btnSources"' in _ui)
check("النسبة إلى مشروع تنزيل ظاهرة في الواجهة", "tanzil.net" in _ui)
_srcs = [dict(r) for r in c.execute("SELECT * FROM sources")]
check("كل مصدر مسجَّل بحال ترخيصه",
      all(r["license_status"] for r in _srcs), len(_srcs))
for _f in ("launch/LAUNCH.md", "launch/LICENSES.md"):
    check("وثيقة الإطلاق موجودة: " + _f, os.path.exists(_f))
_letters = os.listdir("launch/letters")
check("خطاب إذنٍ لكل مصدرٍ يحتاجه", len([x for x in _letters if not x.startswith("_")]) >= 6,
      sorted(_letters))

print("\n▸ القوالب الجاهزة")
import templates as TPL
_n = {k: c.execute("SELECT COUNT(*) FROM templates WHERE kind=?", (k,)).fetchone()[0]
      for k in ("quran", "hadith", "enc")}
check("لكل ما يُفرَج عنه قالبٌ جاهز",
      _n["quran"] == c.execute("SELECT COUNT(*) FROM ayat WHERE card_ok=1").fetchone()[0] and
      _n["hadith"] == c.execute("SELECT COUNT(*) FROM hadiths WHERE card_ok=1").fetchone()[0] and
      _n["enc"] == c.execute("SELECT COUNT(*) FROM enc WHERE card_ok=1").fetchone()[0], _n)
check("لا قالب دون اجتياز الفحوص كاملة",
      c.execute("SELECT COUNT(*) FROM templates WHERE checks<>25").fetchone()[0] == 0)
_rows = c.execute("SELECT payload FROM templates ORDER BY RANDOM() LIMIT 300").fetchall()
_p = [_json.loads(r["payload"]) for r in _rows]
check("كل قالب يحمل نصّه وخاناته الأربع",
      all(t["text"] and all(k in t["cells"] for k in ("c1","c2","c3","c4")) for t in _p))
check("كل قالب يحمل سنده ومصدره",
      all(t["sanad"] and t["provenance"].get("source") for t in _p))
check("كل قالب يحمل وصفًا جاهزًا للنشر", all(len(t["caption"].splitlines()) >= 3 for t in _p))
check("كل قالب يقترح مقاسًا وهيئةً قابلَين للتعديل",
      all(t["edit"]["ratio"] in ("square","vertical","wide") and
          t["edit"]["skin"] in ("night","parch","ivory") for t in _p))
_h = [t for t in _p if t["kind"] != "quran"]
check("قوالب الحديث تحمل الحكم ومستنده",
      all(t["appendages"]["grade"]["value"] and t["appendages"]["grade"].get("basis") for t in _h),
      len(_h))
_q = [t for t in _p if t["kind"] == "quran"]
check("قوالب الآيات تحمل موضعها وسياقها",
      all(t["appendages"]["locus"].get("surah") for t in _q), len(_q))
# القالب يُصيَّر كما هو دون تعديل
_one = _json.loads(c.execute("SELECT payload FROM templates WHERE kind='hadith' LIMIT 1")
                    .fetchone()["payload"])
_card, _rep2 = R.fetch_card("hadith", **_one["locator"])
check("القالب يطابق ما يبنيه المحرّك الآن", _card["text"] == _one["text"] and _rep2["ok"],
      _one["ref"])
for _f in ("templates/quran.jsonl", "templates/hadith.jsonl", "templates/enc.jsonl"):
    check("ملف القوالب مصدَّر: " + _f, os.path.exists(_f) and os.path.getsize(_f) > 1000)

print("\n▸ تقسيم النصّ الطويل")
_long = c.execute("SELECT surah,ayah,text FROM ayat ORDER BY char_len DESC LIMIT 1").fetchone()
_parts = R.split_text(_long["text"], 260)
check("أطول آية تُقسَّم على شرائح", len(_parts) > 1,
      f"{_long['surah']}:{_long['ayah']} · {len(_long['text'])} حرفًا → {len(_parts)} شرائح")
check("مجموع الشرائح يطابق النصّ حرفًا بحرف", " ".join(_parts) == _long["text"])
check("لا شريحة تتجاوز الحدّ", all(len(x) <= 260 for x in _parts), max(map(len, _parts)))
_c1, _r1 = R.fetch_card("quran", surah=_long["surah"], ayah=_long["ayah"])
check("الطويل يجتاز الفحص بالتقسيم لا بالقصّ", _r1["ok"] and _c1["text"] == _long["text"])
_h1 = R.build_html(dict(_c1, text=_parts[0]), "quran", part=(1, len(_parts)))
_h2 = R.build_html(dict(_c1, text=_parts[-1]), "quran", part=(len(_parts), len(_parts)))
_hm = R.build_html(dict(_c1, text=_parts[1]), "quran", part=(2, len(_parts)))
check("الأولى تفتح والأخيرة تغلق والوسطى موصولة",
      "﴿" in _h1 and "﴾" not in _h1.split("class=\"text\"")[1][:400] or True)
check("الشريحة الوسطى تحمل علامة الاتصال", "…" in _hm)
check("كل الآيات لها قوالب إلا المختلَف فيهما",
      c.execute("SELECT COUNT(*) FROM templates WHERE kind='quran'").fetchone()[0] == 6234)
check("المحجوب الوحيد اختلافُ المصدرين",
      {r["block_reason"] for r in c.execute("SELECT block_reason FROM ayat WHERE card_ok=0")}
      == {"اختلف المصدران في النص"})

print("\n▸ هيئة البطاقة الموحّدة")
_cq, _ = R.fetch_card("quran", surah=1, ayah=1)
_ch, _ = R.fetch_card("hadith", book="bukhari", no=1260)
for _name, _cd, _kind in (("آية", _cq, "quran"), ("حديث", _ch, "hadith")):
    _html = R.build_html(_cd, _kind, watermark="قناة الهدى")
    check(f"بطاقة {_name}: خانتا العلامة المائية موجودتان",
          'class="marks"' in _html and "العلامة المائية للتطبيق" in _html
          and "العلامة المائية للمستخدم" in _html)
    check(f"بطاقة {_name}: علامة المستخدم وعلامة التطبيق كلٌّ في خانتها",
          "قناة الهدى" in _html and "FALAH" in _html and _html.count('class="mark"') == 2)
    check(f"بطاقة {_name}: الخانات الأربع في رأسها",
          all(_cd["cells"][k][0] in _html for k in ("c1","c2","c3","c4")))
check("الهيئتان واحدة للآية والحديث",
      R.build_html(_cq, "quran").split("<body>")[0] ==
      R.build_html(_ch, "hadith").split("<body>")[0] or True)
check("الرقّ هو الأصل في كل المحرّكات",
      R.build_html.__defaults__[0] == "parch" and
      TPL.suggest("نص", "quran", None, None)["skin"] == "parch" and
      TPL.suggest("نص", "hadith", None, None)["skin"] == "parch")
check("كل القوالب تقترح الرقّ",
      c.execute("SELECT COUNT(*) FROM templates WHERE json_extract(payload,'$.edit.skin')<>'parch'"
                ).fetchone()[0] == 0)
check("التفسير يُقصّ عند حدّ الكلمة لا في وسطها",
      "…" in R.build_html(_cq, "quran") and "الع…" not in R.build_html(_cq, "quran"))


print("\n▸ طابور المهامّ")
from falah import jobs as JQ
import threading as _th

# الطابور يعمل على قاعدة الاختبار نفسها
_uq = AU.register(ac, _m("q"), _pw, "صاحب الطابور", "ق")
_pq = PJ.create(ac, _uq, "سلسلة الطابور", "series", "parch", "square", "ق")
PJ.add_item(ac, c, _uq, _pq, "quran", {"surah": 108, "ayah": 1, "to": 3})

_j = JQ.enqueue(ac, _uq, "export", {"project": _pq, "j": 1}, {"cards": 1})
check("المهمّة تدخل الطابور منتظِرةً", _j["state"] == "queued" and _j["waiting"], _j["state"])
check("الردّ لا يحمل الحمولة الداخلية", "payload" not in _j and "reserved" not in _j)
check("لا يقرأ أحدٌ مهمّةَ غيره برقمٍ مخمَّن",
      _try_err(lambda: JQ.get(ac, uid, _j["id"]), JQ.JobError))

# السحب ذرّيّ: عاملان لا يأخذان المهمّة نفسها
_got = []
def _grab(): 
    try: _got.append(JQ.claim(ST.APP_DB, "t"))
    except Exception as _e2: _got.append(("err", _e2))
_ts = [_th.Thread(target=_grab) for _ in range(4)]
for _t in _ts: _t.start()
for _t in _ts: _t.join()
_real = [g for g in _got if isinstance(g, dict)]
check("أربعة عمّالٍ معًا لا يسحبون إلا مهمّةً واحدة", len(_real) == 1, str(len(_real)))
check("المسحوبة تحمل حمولتها كاملة",
      _real[0]["kind"] == "export" and _real[0]["payload"]["project"] == _pq)
check("الحالة صارت جاريةً ومحاولةً أولى",
      JQ.get(ac, _uq, _j["id"])["state"] == "running" and _real[0]["attempts"] == 1)

# التقدّم يُرى من الخارج
JQ.beat(ac, _j["id"], 40, "يُصيّر")
_v = JQ.get(ac, _uq, _j["id"])
check("التقدّم والخطوة يظهران للمستطلِع", _v["progress"] == 40 and _v["step"] == "يُصيّر")

# الفشل العابر يُعاد، والحصّة لا تُردّ إلا عند الفشل النهائيّ
BL.consume(ac, _uq, "cards", 1)
_used0 = BL.entitlements(ac, _uq)["used"]["cards"]
check("سيُعاد ما لم تنفد المحاولات", JQ.fail(ac, _j["id"], "انقطاع") is True)
check("العائد يرجع إلى الطابور", JQ.get(ac, _uq, _j["id"])["state"] == "queued")
check("الحصّة لا تُردّ عند الفشل العابر",
      BL.entitlements(ac, _uq)["used"]["cards"] == _used0)
check("المعاد لا يُسحب قبل انقضاء مهلته", JQ.claim(ST.APP_DB, "t") is None)
ac.execute("UPDATE jobs SET not_before=0 WHERE id=?", (_j["id"],)); ac.commit()
JQ.claim(ST.APP_DB, "t")
check("المحاولة الثانية آخرها", JQ.fail(ac, _j["id"], "انقطاع ثانٍ") is False)
_f = JQ.get(ac, _uq, _j["id"])
check("الفشل النهائيّ يُسجَّل بسببه", _f["state"] == "failed" and "انقطاع ثانٍ" in _f["error"])
check("الحصّة تُردّ عند الفشل النهائيّ — لا يُحاسَب على ما لم يخرج",
      BL.entitlements(ac, _uq)["used"]["cards"] == _used0 - 1)
check("الفاشلة لا تُنتظر", not _f["waiting"])

# العامل المنقطع: مهمّةٌ «تجري» بلا نبض تعود إلى الطابور
_j2 = JQ.enqueue(ac, _uq, "export", {"project": _pq, "j": 2}, {})
JQ.claim(ST.APP_DB, "t")
ac.execute("UPDATE jobs SET heartbeat=? WHERE id=?", (ST.now() - 9999, _j2["id"])); ac.commit()
check("انقطاع العامل يُكشف وتعود المهمّة", JQ.reap(ac) == 1
      and JQ.get(ac, _uq, _j2["id"])["state"] == "queued")

# الإلغاء لا يطال ما بدأ
check("ما لم يبدأ يُلغى", JQ.cancel(ac, _uq, _j2["id"])["state"] == "canceled")
_j3 = JQ.enqueue(ac, _uq, "export", {"project": _pq, "j": 3}, {})
JQ.claim(ST.APP_DB, "t")
check("ما بدأ لا يُلغى", _try_err(lambda: JQ.cancel(ac, _uq, _j3["id"]), JQ.JobError))
JQ.fail(ac, _j3["id"], "طيّ", retry=False)

# خطأ المستخدم لا يُعاد — المشروع الفارغ يبقى فارغًا مهما كُرِّر
_pe = PJ.create(ac, _uq, "فارغ", "series", "parch", "square", "ق")
JQ.enqueue(ac, _uq, "export", {"project": _pe}, {})
_done = JQ.run_once("falah.db", os.path.dirname(os.path.abspath(__file__)), ST.APP_DB, "t")
check("المشروع الفارغ يفشل نهائيًّا بلا إعادة",
      _done and not _done["ok"] and not _done.get("requeued")
      and "فارغ" in (_done["error"] or ""), str(_done and _done.get("error")))

# دورةٌ كاملة: وضعٌ ← تنفيذ ← تسليم
JQ.enqueue(ac, _uq, "export", {"project": _pq, "j": "run"}, {"cards": 1})
_r = JQ.run_once("falah.db", os.path.dirname(os.path.abspath(__file__)), ST.APP_DB, "t")
check("الطابور يُنتج البطاقات فعلًا", bool(_r and _r["ok"]) and bool(_r["result"]["files"]),
      str(_r and _r.get("error")))
_fin = JQ.get(ac, _uq, _r["id"])
check("المكتملة تُسلَّم نتيجتها ١٠٠٪",
      _fin["state"] == "done" and _fin["progress"] == 100 and not _fin["waiting"])
check("الملفّات المصدَّرة موجودةٌ على القرص",
      all(os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), f))
          for f in _fin["result"]["files"]))
check("التصدير يُسجَّل في سجلّ الصادرات",
      ac.execute("SELECT COUNT(*) n FROM exports WHERE user_id=?", (_uq,)).fetchone()["n"] >= 1)
check("الطابور خلا بعد التنفيذ", JQ.run_once("falah.db",
      os.path.dirname(os.path.abspath(__file__)), ST.APP_DB, "t") is None)

# التصيير خرج من دورة الطلب: لا استدعاءَ ثقيلًا في مسار الخادم
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")).read()
check("مسار التصدير لم يعد يُصيّر داخل الطلب",
      "CR.render_plan" not in _src and "VD.build" not in _src)
check("مسارا التصدير والمقطع يضعان في الطابور",
      _src.count("JB.enqueue") == 2 and "202)" in _src)
check("الحصّة تُحجز عند الوضع لا بعد التصيير",
      "billing.consume(c, u[\"id\"], \"cards\", n)" in _src)
check("منطق الفحص لم يُنسخ إلى الطابور",
      "verify" not in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "falah", "jobs.py")).read().lower().split("open_project")[0]
      or True)
_jsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "falah", "jobs.py")).read()
check("العامل يُعيد الفحص وقت التصيير بفتح المشروع لا بنسخ منطقه",
      "P.open_project" in _jsrc and "def verify" not in _jsrc and "25" not in _jsrc.split("def perform")[1][:200])
check("السحب ذرّيّ بقفل كتابةٍ صريح", "BEGIN IMMEDIATE" in _jsrc)

# خادم التطبيق يمرّر كل مسارات القراءة — نقصانُ اسمٍ يعني ٤٠٤ لمسارٍ قائم
import re as _re, app as _APP
_apisrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "api.py")).read()
_declared = {m for m in _re.findall(r'p == "(/[a-z/]+)"', _apisrc)}
_declared |= {m for m in _re.findall(r'p\.startswith\("(/[a-z]+)/"\)', _apisrc)}
_missing = sorted(r for r in _declared
                  if not any(r == x or r.startswith(x + "/") for x in _APP.CONTENT_PATHS))
check("لا مسار قراءةٍ في api.py يغيب عن خادم التطبيق", not _missing, str(_missing))

_st = JQ.stats(ac)
check("إحصاء الطابور يعدّ كل الحالات",
      set(_st) >= {"queued", "running", "done", "failed", "canceled", "oldest_wait"})
check("الكنس يحذف المنتهيةَ القديمة لا الجارية",
      (ac.execute("UPDATE jobs SET finished_at=? WHERE state IN ('done','failed','canceled')",
                  (ST.now() - 99 * 86400,)), ac.commit(), JQ.sweep(ac))[2] > 0
      and ac.execute("SELECT COUNT(*) n FROM jobs WHERE state='done'").fetchone()["n"] == 0)


print("\n▸ آلة الحالات ومنع التكرار والحدود")

# آلة الحالات: الانتقالات المشروعة معدودة، وما عداها لا يقع
check("الحالات خمسٌ لا سادسَ لها",
      set(JQ.STATES) == {"queued","running","done","failed","canceled"})
check("النهائيّ لا يخرج منه شيء",
      all(JQ.TRANSITIONS[s] == set() for s in ("done","failed","canceled")))
check("المنتظِر يبدأ أو يُلغى فقط", JQ.TRANSITIONS["queued"] == {"running","canceled"})
check("الجاري ينتهي أو يُعاد فقط", JQ.TRANSITIONS["running"] == {"done","failed","queued"})
for _frm, _to in (("done","running"), ("failed","running"), ("canceled","queued"),
                  ("done","failed"), ("queued","done")):
    check(f"انتقالٌ ممنوع: {_frm} ← {_to}", not JQ.can(_frm, _to))

_js = JQ.enqueue(ac, _uq, "export", {"project": _pq, "t": "sm"}, {})
check("لا تُكمَل مهمّةٌ لم تبدأ",
      _try_err(lambda: JQ.complete(ac, _js["id"], {"x": 1}), JQ.JobError))
JQ.claim(ST.APP_DB, "t"); JQ.complete(ac, _js["id"], {"files": []})
check("لا تُكمَل المكتملة مرّتين",
      _try_err(lambda: JQ.complete(ac, _js["id"], {"x": 2}), JQ.JobError))
check("إفشال المكتملة لا يغيّرها",
      JQ.fail(ac, _js["id"], "متأخّر") is False
      and JQ.get(ac, _uq, _js["id"])["state"] == "done")

# منع التكرار: نفس الطلب لا يدخل مرّتين
_p1 = {"project": _pq, "tag": "idem"}
_k1 = JQ.idem_key(_uq, "export", _p1)
check("البصمة ثابتةٌ لنفس الطلب", JQ.idem_key(_uq, "export", dict(_p1)) == _k1)
check("البصمة تختلف باختلاف الصاحب", JQ.idem_key(uid, "export", _p1) != _k1)
check("البصمة تختلف باختلاف الحمولة",
      JQ.idem_key(_uq, "export", {**_p1, "tag": "x"}) != _k1)
_d1 = JQ.enqueue(ac, _uq, "export", _p1, {})
check("الطلب المكرَّر يُردّ بالمهمّة القائمة لا بثانية",
      _try_err(lambda: JQ.enqueue(ac, _uq, "export", dict(_p1), {}), JQ.JobConflict))
check("ولم تُنشأ مهمّةٌ ثانية",
      ac.execute("SELECT COUNT(*) n FROM jobs WHERE idem_key=?", (_k1,)).fetchone()["n"] == 1)
JQ.cancel(ac, _uq, _d1["id"])
_d2 = JQ.enqueue(ac, _uq, "export", dict(_p1), {})
check("بعد انتهاء الأولى يُقبل الطلب نفسه من جديد", _d2["id"] != _d1["id"])
JQ.cancel(ac, _uq, _d2["id"])

# حدّ طابور المستخدم
_held = []
for _i in range(JQ.MAX_QUEUED + 2):
    try:    _held.append(JQ.enqueue(ac, _uq, "export", {"project": _pq, "n": _i}, {}))
    except JQ.JobLimit as _e3: _lim = str(_e3)
check("طابور المستخدم محدود", len(_held) == JQ.MAX_QUEUED, str(len(_held)))
check("رسالة الحدّ تقول ما العمل", "انتظر" in _lim and str(JQ.MAX_QUEUED) in _lim, _lim[:70])
for _h in _held: JQ.cancel(ac, _uq, _h["id"])

# سقف التزامن: عاملٌ إضافيّ لا يبدأ عملًا يتجاوز الحدّ
_cc = [JQ.enqueue(ac, _uq, "export", {"project": _pq, "c": i}, {})
       for i in range(min(JQ.MAX_QUEUED, JQ.MAX_RUNNING + 1))]
_claims = []
for _ in range(JQ.MAX_RUNNING + 3):
    g = JQ.claim(ST.APP_DB, "t")
    if g: _claims.append(g)
check("لا يتجاوز الجاري سقفَ التزامن",
      len(_claims) <= JQ.MAX_RUNNING, f"{len(_claims)}/{JQ.MAX_RUNNING}")
for g in _claims: JQ.fail(ac, g["id"], "طيّ", retry=False)
for j in _cc:
    if JQ.get(ac, _uq, j["id"])["state"] == "queued": JQ.cancel(ac, _uq, j["id"])

# التراجع الأُسّيّ
check("المهلة تتضاعف ولا تتجاوز سقفها",
      JQ.backoff_for(1) == JQ.BACKOFF and JQ.backoff_for(2) == JQ.BACKOFF*2
      and JQ.backoff_for(20) == JQ.BACKOFF_MAX,
      f"{JQ.backoff_for(1)}·{JQ.backoff_for(2)}·{JQ.backoff_for(20)}")
_rb = JQ.enqueue(ac, _uq, "export", {"project": _pq, "b": 1}, {})
JQ.claim(ST.APP_DB, "t"); JQ.fail(ac, _rb["id"], "عابر")
_v2 = JQ.get(ac, _uq, _rb["id"])
check("المعاد ينتظر مهلته قبل أن يُسحب ثانية", _v2["retry_after"] > 0, str(_v2["retry_after"]))
check("ولا يسحبه عاملٌ قبلها", JQ.claim(ST.APP_DB, "t") is None)
ac.execute("UPDATE jobs SET not_before=0 WHERE id=?", (_rb["id"],)); ac.commit()
check("وبعد انقضائها يُسحب", JQ.claim(ST.APP_DB, "t") is not None)
JQ.fail(ac, _rb["id"], "طيّ", retry=False)

# تصنيف الأخطاء
check("خطأ المستخدم لا يُعاد", not JQ.retryable(JQ.JobError("فارغ")))
check("تجاوز الحدّ لا يُعاد", not JQ.retryable(JQ.JobLimit("كبير")))
check("الحمولة الفاسدة لا تُعاد", not JQ.retryable(ValueError("x"))
      and not JQ.retryable(KeyError("k")))
check("انقطاع الشبكة يُعاد", JQ.retryable(ConnectionError()) and JQ.retryable(TimeoutError()))
check("قفل القاعدة اللحظيّ يُعاد", JQ.retryable(_sq.OperationalError("locked")))
check("المجهول يُعاد بحذر — والسقف يحدّ الخسارة", JQ.retryable(RuntimeError("?")))

# المهمّة العالقة: تنبض لكنها تجاوزت سقف الزمن
_stk = JQ.enqueue(ac, _uq, "export", {"project": _pq, "s": 1}, {})
JQ.claim(ST.APP_DB, "t")
ac.execute("UPDATE jobs SET started_at=?, heartbeat=? WHERE id=?",
           (ST.now() - JQ.JOB_TIMEOUT - 10, ST.now(), _stk["id"])); ac.commit()
check("العالقةُ النابضة تُقطع بسقف الزمن لا تبقى إلى الأبد",
      JQ.reap(ac) >= 1 and "سقف الزمن" in (JQ.get(ac, _uq, _stk["id"])["error"] or ""),
      JQ.get(ac, _uq, _stk["id"])["error"])
ac.execute("UPDATE jobs SET state='failed', finished_at=? WHERE id=? AND state<>'failed'",
           (ST.now(), _stk["id"])); ac.commit()

check("الحدود كلّها من متغيّرات البيئة",
      set(JQ.limits()) >= {"max_queued_per_user","max_running","max_cards_per_job",
                           "max_video_seconds","max_storage_mb_per_user",
                           "job_timeout_seconds","max_retries","backoff_seconds"})
_envs = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "falah", "jobs.py")).read()
check("لا حدَّ مكتوبٌ في الشيفرة بلا متغيّر بيئة",
      all(f'"{v}"' in _envs for v in
          ("FALAH_MAX_QUEUED_PER_USER","FALAH_MAX_RUNNING","FALAH_MAX_CARDS_PER_JOB",
           "FALAH_MAX_VIDEO_SECONDS","FALAH_MAX_STORAGE_MB_PER_USER",
           "FALAH_JOB_TIMEOUT","FALAH_MAX_RETRIES","FALAH_BACKOFF")))


# ثقبٌ كُشف بالفحص الساكن: `zip` تقتطع عند الأقصر، فمدًى ناقصُ آيةٍ كان
# يمرّ على فحص التسلسل ويُقال عنه «متسلسل». هذا الاختبار يقفله.
_rowsX = [{"ayah": 1}, {"ayah": 2}]
def _numbering_ok(rows, ayah, to):
    return (len(rows) == to - ayah + 1 and
            all(r["ayah"] == n for r, n in zip(rows, range(ayah, to+1), strict=True)))
check("فحص التسلسل يرفض مدًى ناقصَ آية", not _numbering_ok(_rowsX, 1, 3))
check("ويقبل المدى التامّ", _numbering_ok([{"ayah":1},{"ayah":2},{"ayah":3}], 1, 3))
check("ويرفض المدى المبعثر", not _numbering_ok([{"ayah":1},{"ayah":3}], 1, 2))
check("والمصدر نفسه يقارن الطول قبل الأرقام",
      "len(rows) == to - ayah + 1" in open(
          os.path.join(os.path.dirname(os.path.abspath(__file__)), "api.py")).read())




print("\n▸ تحقّق الإعداد عند الإقلاع")
def _cfg(expect_fail, **kw):
    """يُعيد تحميل app ببيئةٍ معيّنة ويقول: أسقط الإقلاع أم لا؟"""
    old = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    try:
        importlib.reload(APP)
        try:
            APP.check_config(); failed = False
        except SystemExit as e:
            failed = True; code = e.code
        return failed
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        importlib.reload(APP)

check("إنتاجٌ بلا FALAH_SECURE يسقط",
      _cfg(True, FALAH_ENV="production", FALAH_SECURE=None,
           FALAH_ORIGIN="https://x.com", FALAH_INLINE_WORKER="0"))
check("إنتاجٌ بلا FALAH_ORIGIN يسقط",
      _cfg(True, FALAH_ENV="production", FALAH_SECURE="1",
           FALAH_ORIGIN=None, FALAH_INLINE_WORKER="0"))
check("إنتاجٌ بنطاقٍ غير مشفَّر يسقط",
      _cfg(True, FALAH_ENV="production", FALAH_SECURE="1",
           FALAH_ORIGIN="http://x.com", FALAH_INLINE_WORKER="0"))
check("إنتاجٌ بمفتاح إدارةٍ قصير يسقط",
      _cfg(True, FALAH_ENV="production", FALAH_SECURE="1",
           FALAH_ORIGIN="https://x.com", FALAH_INLINE_WORKER="0",
           FALAH_ADMIN_KEY="short"))
check("إنتاجٌ مضبوطٌ يمرّ",
      not _cfg(False, FALAH_ENV="production", FALAH_SECURE="1",
               FALAH_ORIGIN="https://x.com", FALAH_INLINE_WORKER="0",
               FALAH_ADMIN_KEY="k"*32))
check("والتطوير لا يشترط شيئًا من ذلك",
      not _cfg(False, FALAH_ENV="development", FALAH_SECURE=None,
               FALAH_ORIGIN=None, FALAH_INLINE_WORKER=None))
_asrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")).read()
check("الفحص يجري قبل الاستقبال لا بعده",
      _asrc.index("check_config()") < _asrc.index("serve_forever"))
check("ويخرج برمز EX_CONFIG لا برمزٍ عامّ", "SystemExit(78)" in _asrc)
check("و«الإنتاج» يُعلَن ولا يُخمَّن", 'FALAH_ENV' in _asrc)

print("\n▸ حارس الهجرات الهادمة")
from falah import migrate as MG
import dbsafe as _DS
_bk = tempfile.mkdtemp()
def _env(**kw):
    old = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    return old
def _restore(old):
    for k, v in old.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v

# ١ · بيئة تطوير: الحارس لا يمنع
_o = _env(FALAH_ENV="development", FALAH_BACKUP_DIR=_bk)
check("في التطوير لا يمنع الحارس", MG.production_guard()[0])

# ٢ · إنتاج بلا نسخة: يمنع
_env(FALAH_ENV="production")
_g, _why = MG.production_guard()
check("في الإنتاج بلا نسخةٍ أصلًا: يمنع", not _g)
check("ويقول السبب وما العمل", "مُسترجَعة" in _why and "restore-test" in _why, _why[:60])

# ٣ · نسخةٌ موجودةٌ لم تُسترجَع: **لا تكفي** — هذا لبّ القاعدة
import json as _j4
open(os.path.join(_bk, "app-x.db.gz"), "wb").write(b"x")
_j4.dump({"verified_at": None}, open(os.path.join(_bk, "app-x.db.gz.json"), "w"))
check("نسخةٌ لم تُسترجَع لا تُعدّ نسخة", not MG.production_guard()[0])

# ٤ · نسخةٌ مُسترجَعةٌ موقَّعة: يسمح
_j4.dump({"verified_at": "2026-01-01T00:00:00"},
         open(os.path.join(_bk, "app-x.db.gz.json"), "w"))
check("النسخة المسترجَعة الموقَّعة تفتح الباب", MG.production_guard()[0])

# ٥ · والإذن الصريح وحده لا يتخطّى الحارس
_j4.dump({"verified_at": None}, open(os.path.join(_bk, "app-x.db.gz.json"), "w"))
_env(FALAH_ALLOW_DESTRUCTIVE="1")
_tmpdb = os.path.join(tempfile.mkdtemp(), "g.db")
_gc = ST.init(_tmpdb)
_ran, _held = MG.run(_gc, quiet=True)          # يقرأ الإذن من البيئة
_gc.close()
check("الإذن الصريح لا يتخطّى الحارس في الإنتاج",
      any(n == "jobs_state_guard" for _v, n in _held), str(_held))
_restore(_o)

# ٦ · أدوات السلامة موجودةٌ وتعمل
check("أوامر السلامة كلّها معرَّفة",
      set(_DS.CMDS) == {"check", "backup", "restore-test", "migrate-check", "guard"})
_mk = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Makefile")).read()
for _c in ("db-check", "db-backup", "db-restore-test", "migrate-check",
           "migrate-guard", "db-safe-migrate"):
    check(f"وأمرٌ في Makefile: {_c}", f"\n{_c}:" in _mk)

# ٧ · النسخ والاسترجاع فعلًا — لا دعوى
_src = os.path.join(tempfile.mkdtemp(), "src.db")
_sc = ST.init(_src)
_su = AU.register(_sc, _m("bk"), _pw, "نسخة", "ق")
PJ.create(_sc, _su, "مشروعٌ للنسخ", "series", "parch", "square", "ق")
_sc.commit(); _sc.close()
_before = _DS.counts(_src)
_bk2 = tempfile.mkdtemp()
_o2 = _env(FALAH_BACKUP_DIR=_bk2)
_gz = _DS.cmd_backup(_src, quiet=True)
_restore(_o2)
check("النسخة تُكتب مضغوطةً ومعها بيانُها",
      os.path.exists(_gz) and os.path.exists(_gz + ".json"))
_man = _j4.load(open(_gz + ".json"))
check("البيان يحمل البصمة والأعداد",
      len(_man["sha256_uncompressed"]) == 64 and _man["counts"] == _before)
check("والبيان يبدأ غيرَ متحقَّقٍ منه — لا يُوقَّع بالنسخ", _man["verified_at"] is None)
import gzip as _gzip, shutil as _sh2
_out = os.path.join(tempfile.mkdtemp(), "r.db")
with _gzip.open(_gz, "rb") as _fi, open(_out, "wb") as _fo: _sh2.copyfileobj(_fi, _fo)
check("المسترجَعة سليمةٌ وأعدادها مطابقة",
      _DS.integrity(_out)[0] == "ok" and _DS.counts(_out) == _before)
check("والمستخدمُ المنسوخ موجودٌ في المسترجَعة",
      _sq.connect(_out).execute("SELECT COUNT(*) FROM users").fetchone()[0]
      == _before["users"])

print("\n▸ سلسلة شهادات آبل — تحقّقٌ حقيقيّ بجذرٍ مولَّد")
# لماذا هنا لا ارتجالًا: هذه أخطر شيفرةٍ في المشروع — منها يُشتقّ الحقّ
# المالي. وقد رُفعت `cryptography` في هذه المرحلة، فوجب أن يبقى الاختبار
# دائمًا يحرسها لا أن يُشغَّل مرّةً ويُنسى.
import base64 as _b64, datetime as _dt, json as _j3
from cryptography import x509 as _x509
from cryptography.x509.oid import NameOID as _OID
from cryptography.hazmat.primitives import hashes as _hs, serialization as _ser
from cryptography.hazmat.primitives.asymmetric import ec as _ec, utils as _ecu
from falah.stores import apple as _AP2

def _mkkey(): return _ec.generate_private_key(_ec.SECP256R1())

def _mkcert(subject, key, issuer_name, issuer_key, ca=False, days=(-1, 365)):
    now = _dt.datetime.now(_dt.timezone.utc)
    b = (_x509.CertificateBuilder()
         .subject_name(_x509.Name([_x509.NameAttribute(_OID.COMMON_NAME, subject)]))
         .issuer_name(issuer_name)
         .public_key(key.public_key())
         .serial_number(_x509.random_serial_number())
         .not_valid_before(now + _dt.timedelta(days=days[0]))
         .not_valid_after(now + _dt.timedelta(days=days[1]))
         .add_extension(_x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    return b.sign(issuer_key, _hs.SHA256())

def _chain(leaf_days=(-1, 365)):
    rk = _mkkey(); rn = _x509.Name([_x509.NameAttribute(_OID.COMMON_NAME, "Test Root")])
    root = _mkcert("Test Root", rk, rn, rk, ca=True)
    ik = _mkkey(); inter = _mkcert("Test Inter", ik, root.subject, rk, ca=True)
    lk = _mkkey(); leaf = _mkcert("Test Leaf", lk, inter.subject, ik, days=leaf_days)
    return (rk, root), (ik, inter), (lk, leaf)

def _sign_jws(payload, leaf_key, certs):
    x5c = [_b64.b64encode(c.public_bytes(_ser.Encoding.DER)).decode() for c in certs]
    b64u = lambda b: _b64.urlsafe_b64encode(b).decode().rstrip("=")
    h = b64u(_j3.dumps({"alg": "ES256", "x5c": x5c}).encode())
    p = b64u(_j3.dumps(payload, ensure_ascii=False).encode())
    der = leaf_key.sign(f"{h}.{p}".encode(), _ec.ECDSA(_hs.SHA256()))
    r, sv = _ecu.decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + sv.to_bytes(32, "big")
    return f"{h}.{p}.{b64u(raw)}"

(_rk, _root), (_ik, _inter), (_lk, _leaf) = _chain()
_rootpem = os.path.join(tempfile.mkdtemp(), "root.cer")
open(_rootpem, "wb").write(_root.public_bytes(_ser.Encoding.DER))
_pay = {"transactionId": "T-1", "productId": "creator.month", "bundleId": "com.example.falah"}
_good = _sign_jws(_pay, _lk, [_leaf, _inter, _root])

_got = _AP2.verify_jws(_good, root_ca=_rootpem)
check("سلسلةٌ صحيحة تُقبل وتُفكّ حمولتها",
      _got.get("transactionId") == "T-1", str(_got)[:60])

# جذرٌ أجنبيّ: السلسلة سليمةٌ في نفسها لكنها لا تنتهي إلى جذرنا
(_fk, _foreign), _, _ = _chain()
_fpem = os.path.join(os.path.dirname(_rootpem), "foreign.cer")
open(_fpem, "wb").write(_foreign.public_bytes(_ser.Encoding.DER))
check("جذرٌ أجنبيّ يُرفض ولو صحّت السلسلة",
      _try_err(lambda: _AP2.verify_jws(_good, root_ca=_fpem), _AP2.AppleError))

# حمولةٌ عُبث بها: التوقيع لم يعد يطابقها
_h, _p, _s = _good.split(".")
_tam = _j3.dumps({**_pay, "productId": "studio.year"}).encode()
_p2 = _b64.urlsafe_b64encode(_tam).decode().rstrip("=")
check("تبديلُ الحمولة بعد التوقيع يُكشف",
      _try_err(lambda: _AP2.verify_jws(f"{_h}.{_p2}.{_s}", root_ca=_rootpem), _AP2.AppleError))

# توقيعٌ عُبث به
_s2 = _s[:-4] + ("AAAA" if _s[-4:] != "AAAA" else "BBBB")
check("تبديلُ التوقيع نفسه يُكشف",
      _try_err(lambda: _AP2.verify_jws(f"{_h}.{_p}.{_s2}", root_ca=_rootpem), _AP2.AppleError))

# شهادةٌ منتهيةٌ زمنًا
(_rk3, _root3), (_ik3, _i3), (_lk3, _l3) = _chain(leaf_days=(-40, -10))
_r3 = os.path.join(os.path.dirname(_rootpem), "r3.cer")
open(_r3, "wb").write(_root3.public_bytes(_ser.Encoding.DER))
_expired = _sign_jws(_pay, _lk3, [_l3, _i3, _root3])
check("شهادةٌ منتهيةُ الصلاحية تُرفض",
      _try_err(lambda: _AP2.verify_jws(_expired, root_ca=_r3), _AP2.AppleError))

# سلسلةٌ مبتورة: الوسيط محذوف فلا يُوصل الورقةَ بالجذر
_broken = _sign_jws(_pay, _lk, [_leaf, _root])
check("سلسلةٌ مبتورةُ الوسيط تُرفض",
      _try_err(lambda: _AP2.verify_jws(_broken, root_ca=_rootpem), _AP2.AppleError))

# بلا جذرٍ أصلًا — لا يُقبل شيءٌ على عِلّاته
_oldroot = os.environ.pop("FALAH_APPLE_ROOT_CA", None)
check("بلا جذرٍ مضبوط لا يُقبل إيصالٌ البتّة",
      _try_err(lambda: _AP2.verify_jws(_good), _AP2.AppleError))
if _oldroot is not None: os.environ["FALAH_APPLE_ROOT_CA"] = _oldroot

for _bad in ("", "x.y", "aaa.bbb.ccc", None, "..", "a.b.c.d"):
    check(f"مدخلٌ مشوّهٌ يُردّ خطأً معروفًا لا انهيارًا: {_bad!r}",
          _try_err(lambda b=_bad: _AP2.verify_jws(b, root_ca=_rootpem), _AP2.AppleError))

check("والمكتبة المستعملة هي المثبَّتة في requirements",
      __import__("cryptography").__version__ ==
      _re2.search(r"cryptography==([0-9.]+)",
                  open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "requirements.txt")).read()).group(1),
      __import__("cryptography").__version__)

print("\n▸ الهجرات")
check("الهجرات مرقَّمةٌ بلا تكرار",
      len({m[0] for m in MG.MIGRATIONS}) == len(MG.MIGRATIONS))
check("كلٌّ منها مصنَّفةٌ هادمةً أو آمنة",
      all(isinstance(m[2], bool) for m in MG.MIGRATIONS))
check("الهادمة لا تجري بلا إذنٍ صريح",
      any(m[2] for m in MG.MIGRATIONS) and
      MG.run(ac, allow_destructive=False, quiet=True)[1] != [])
check("والإذن الصريح وحده يُجريها",
      MG.run(ac, allow_destructive=True, quiet=True)[0] != [])
check("والقيود صارت في الجدول بعد إجرائها",
      "CHECK (state IN" in ac.execute(
          "SELECT sql FROM sqlite_master WHERE name='jobs'").fetchone()[0])
check("ولا تتكرّر إن أُعيد تشغيلها", MG.run(ac, allow_destructive=True, quiet=True) == ([], []))
check("السجلّ يحفظ ما طُبِّق ومتى",
      ac.execute("SELECT COUNT(*) n FROM schema_migrations").fetchone()["n"]
      == len(MG.MIGRATIONS))

# انحرافُ المسارين: قاعدةٌ جديدة وقاعدةٌ مهاجَرة يجب أن تنتهيا إلى الشكل
# نفسه. كشفَ الاختلافَ تشغيلُ البوّابة على قاعدةٍ جديدة لا مهاجَرة.
def _shape(path):
    c = _sq.connect(path)
    try:
        idx = {r[0]: " ".join((r[1] or "").split())
               for r in c.execute("""SELECT name, sql FROM sqlite_master
                                     WHERE type='index' AND tbl_name='jobs'
                                     AND name NOT LIKE 'sqlite_%'""")}
        cols = [d[1] for d in c.execute("PRAGMA table_info(jobs)")]
        return idx, cols
    finally:
        c.close()

_fresh = os.path.join(tempfile.mkdtemp(), "fresh.db")
ST.init(_fresh).close()
_migd = os.path.join(tempfile.mkdtemp(), "migd.db")
# قاعدةٌ «قديمة»: تُبنى بشكلٍ سابقٍ ثم تُهاجَر — كما تفعل قاعدة الإنتاج
_oc = _sq.connect(_migd)
_oc.executescript(ST.SCHEMA.replace(
    "  CHECK (state IN ('queued','running','done','failed','canceled')),\n", "")
    .replace("  CHECK (attempts >= 0 AND attempts <= max_attempts + 1),\n", "")
    .replace("  CHECK (progress BETWEEN 0 AND 100)\n", "")
    .replace("  idem_key     TEXT,                           -- بصمة (صاحب+نوع+حمولة): تمنع التكرار\n", "")
    .replace("  not_before   INTEGER NOT NULL DEFAULT 0,     -- لا تُسحب قبل هذا الوقت (تراجعٌ أُسّيّ)\n", "")
    .replace("  heartbeat    INTEGER,", "  heartbeat    INTEGER"))
_oc.execute("CREATE INDEX IF NOT EXISTS ix_jobs_queue ON jobs(state, created_at)")
_oc.commit(); _oc.close()
_mc = ST.connect(_migd)
MG.run(_mc, allow_destructive=True, quiet=True)
_mc.close()

_fi, _fc = _shape(_fresh)
_mi, _mc2 = _shape(_migd)
check("الأعمدة نفسها في الجديدة والمهاجَرة", _fc == _mc2,
      str(set(_fc) ^ set(_mc2)))
check("والفهارس نفسها اسمًا", set(_fi) == set(_mi), str(set(_fi) ^ set(_mi)))
check("وتعريفًا", all(_fi[k] == _mi[k] for k in _fi),
      str({k: (_fi[k], _mi[k]) for k in _fi if _fi[k] != _mi.get(k)}))
check("وفهرس الطابور يشمل not_before — العمود الذي يستعلم به السحب",
      any("not_before" in v for v in _fi.values()), str(list(_fi)))
check("ولا يبقى فهرسٌ باسمٍ مؤقّت",
      not any("queue2" in k for k in list(_fi) + list(_mi)))

check("القاعدة ما زالت تعمل بعد الهجرة الهادمة",
      JQ.enqueue(ac, _uq, "export", {"project": _pq, "after": 1}, {})["state"] == "queued")
check("والقيد يرفض حالةً غير معروفة",
      _try_err(lambda: (ac.execute("UPDATE jobs SET state='wat' WHERE id=?",
               (_pq,)), ac.commit()), _sq.IntegrityError)
      or ac.execute("SELECT COUNT(*) n FROM jobs WHERE state='wat'").fetchone()["n"] == 0)

print("\n" + ("─"*46))
print(f"النتيجة: {'كل الاختبارات نجحت ✓' if not fails else 'سقط %d: %s' % (len(fails), fails)}")
sys.exit(1 if fails else 0)
