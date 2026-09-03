#!/usr/bin/env python3
"""FALAH — بناء طبقة المحتوى.

من الملفات الخام في raw/ إلى falah.db جاهزة للخدمة:
القرآن بالرسم العثماني وتفسيره وترجمته، والحديث بمتنه مفصولًا عن سنده،
مع التخريج المتقاطع، وكشف المتشابه اللفظي، وفهرس موضوعات، وبصمة لكل نص.
"""
import json, sqlite3, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from falah.text import fingerprint, searchable, core_key, clean
from falah.matn import extract_matn, extract_narrator, is_card_ready
from falah.reconcile import strip_leading_basmala, compare, releasable as text_released
from falah import grades as G
from falah.jami import Jami
from falah.audio import RECITERS

HERE = os.path.dirname(os.path.abspath(__file__))
RAW, DB = os.path.join(HERE, "raw"), os.path.join(HERE, "falah.db")
AYAH_CARD_MAX = 240      # حد طول الآية لتصلح بطاقةً واحدة

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE sources(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, kind TEXT,
  origin TEXT, edition TEXT, riwayah TEXT,
  license_status TEXT, enabled INTEGER DEFAULT 1);

CREATE TABLE surahs(
  number INTEGER PRIMARY KEY, name_ar TEXT, name_en TEXT,
  revelation_ar TEXT, revelation_en TEXT, ayah_count INTEGER);

CREATE TABLE ayat(
  id INTEGER PRIMARY KEY, surah INTEGER, ayah INTEGER,
  text TEXT, plain TEXT, fingerprint TEXT, plain_fp TEXT,
  page INTEGER, juz INTEGER, hizb INTEGER, sajda INTEGER,
  char_len INTEGER, card_ok INTEGER, mutashabih_group TEXT,
  text_secondary TEXT, verify_status TEXT, basmala_stripped INTEGER DEFAULT 0,
  block_reason TEXT, source_id INTEGER, UNIQUE(surah, ayah));
CREATE INDEX ix_ayat_page ON ayat(page);
CREATE INDEX ix_ayat_card ON ayat(card_ok);
CREATE INDEX ix_ayat_mut  ON ayat(mutashabih_group);

CREATE TABLE ayah_tafsir(
  surah INTEGER, ayah INTEGER, source_id INTEGER, text TEXT, fingerprint TEXT,
  PRIMARY KEY(surah, ayah, source_id));
CREATE TABLE ayah_translation(
  surah INTEGER, ayah INTEGER, source_id INTEGER, lang TEXT, text TEXT, fingerprint TEXT,
  PRIMARY KEY(surah, ayah, source_id));

CREATE TABLE books(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, name_ar TEXT, name_en TEXT,
  author_ar TEXT, hadith_count INTEGER, grade_rule TEXT, source_id INTEGER);
CREATE TABLE chapters(
  book_id INTEGER, chapter_id INTEGER, name_ar TEXT, name_en TEXT,
  PRIMARY KEY(book_id, chapter_id));

CREATE TABLE hadiths(
  id INTEGER PRIMARY KEY, book_id INTEGER, number_in_book INTEGER, chapter_id INTEGER,
  full_ar TEXT, matn TEXT, matn_method TEXT, matn_conf REAL, matn_fp TEXT, core_key TEXT, match_key TEXT,
  text_en TEXT, narrator_ar TEXT, narrator_en TEXT,
  grade TEXT, grade_raw TEXT, grade_by TEXT, grade_all TEXT,
  grade_basis TEXT, grade_source TEXT, verify_status TEXT,
  char_len INTEGER, card_ok INTEGER, block_reason TEXT,
  jami_vol INTEGER, jami_book TEXT, jami_bab TEXT, jami_hits INTEGER,
  jami_grade TEXT, jami_polarity TEXT, jami_takhrij TEXT, jami_conflict TEXT,
  fingerprint TEXT, source_id INTEGER);
CREATE INDEX ix_h_book ON hadiths(book_id, number_in_book);
CREATE INDEX ix_h_book_ch_ok ON hadiths(book_id, chapter_id, card_ok);
CREATE INDEX ix_h_core ON hadiths(core_key);
CREATE INDEX ix_h_card ON hadiths(card_ok);

-- التخريج المتقاطع: الحديث نفسه في أكثر من كتاب
CREATE TABLE takhrij(group_key TEXT, hadith_id INTEGER, book_id INTEGER,
                     number_in_book INTEGER, PRIMARY KEY(group_key, hadith_id));
CREATE INDEX ix_tk ON takhrij(group_key);

-- كل ما حُجب ولماذا — يُقرأ من /review
CREATE TABLE review_queue(
  kind TEXT, ref TEXT, reason TEXT, detail TEXT, PRIMARY KEY(kind, ref, reason));

-- القرّاء: يُخزَّن القارئ وقالب رابطه، ويُبنى الرابط عند الطلب
CREATE TABLE reciters(
  code TEXT PRIMARY KEY, name TEXT, riwayah TEXT, scheme TEXT, folder TEXT,
  verified INTEGER DEFAULT 0);

-- الموسوعة الحديثية: متنٌ نظيف بشرحه وفوائده ودرجته وتخريجه
CREATE TABLE enc(
  id INTEGER PRIMARY KEY, title TEXT, intro TEXT, matn TEXT, matn_fp TEXT, core_key TEXT,
  grade TEXT, attribution TEXT, reference TEXT,
  explanation TEXT, hints TEXT, words TEXT,
  char_len INTEGER, card_ok INTEGER, block_reason TEXT, source_id INTEGER);
CREATE INDEX ix_enc_card ON enc(card_ok);
CREATE INDEX ix_enc_core ON enc(core_key);

CREATE TABLE enc_tr(
  enc_id INTEGER, lang TEXT, title TEXT, matn TEXT, explanation TEXT, hints TEXT,
  PRIMARY KEY(enc_id, lang));

-- ربط الموسوعة بالكتب التسعة عند تطابق المتن
CREATE TABLE enc_link(enc_id INTEGER, hadith_id INTEGER, PRIMARY KEY(enc_id, hadith_id));

CREATE TABLE topics(
  id INTEGER PRIMARY KEY, name_ar TEXT, name_en TEXT, terms TEXT);
CREATE TABLE topic_items(
  topic_id INTEGER, kind TEXT, ref_id INTEGER, rank INTEGER,
  PRIMARY KEY(topic_id, kind, ref_id));

CREATE VIRTUAL TABLE ayat_fts   USING fts5(text, content='', tokenize='trigram');
CREATE VIRTUAL TABLE hadith_fts USING fts5(text, content='', tokenize='trigram');
CREATE VIRTUAL TABLE enc_fts    USING fts5(text, content='', tokenize='trigram');
"""

TOPICS = [
 ("الصبر والابتلاء","Patience & trial","صبر ابتلاء بلاء احتساب"),
 ("اليسر بعد العسر","Ease after hardship","عسر يسر فرج مخرج"),
 ("طمأنينة القلب","Peace of heart","تطمئن القلوب سكينة ذكر"),
 ("التقوى","God-consciousness","تقوى يتق اتقوا"),
 ("الرزق والتوكل","Provision & trust","رزق يرزق توكل حسبنا"),
 ("الاستغفار والتوبة","Repentance","استغفر توبة تاب غفور"),
 ("الدعاء","Supplication","ادعوني دعاء يدعو استجاب"),
 ("بر الوالدين","Kindness to parents","الوالدين احسانا بر امه"),
 ("الصلاة","Prayer","الصلاة اقيموا ركع سجد"),
 ("الزكاة والصدقة","Charity","زكاة صدقة انفقوا ينفقون"),
 ("الصيام","Fasting","صيام صام رمضان"),
 ("العلم","Knowledge","العلم يعلمون علماء تعلم"),
 ("الرحمة","Mercy","رحمة رحيم يرحم راحمين"),
 ("حفظ اللسان","Guarding the tongue","لسان قول خيرا يصمت غيبة"),
 ("النية والإخلاص","Intention & sincerity","النيات نوى مخلصين اخلاص"),
 ("حسن الخلق","Good character","خلق حسن اخلاقا الحياء"),
 ("الصدق والأمانة","Truth & trust","صدق صادقين امانة"),
 ("محبة الخير للناس","Loving good for others","يحب لاخيه يحب لنفسه"),
 ("صلة الرحم","Family ties","رحم قطيعة صلة الارحام"),
 ("الجار والإحسان","Neighbours & kindness","جاره الجار احسان"),
 ("العفو والصفح","Pardon","عفا العفو اصفح تجاوز"),
 ("الشكر","Gratitude","شكر اشكروا شاكرين لئن شكرتم"),
 ("الموت والآخرة","Death & hereafter","الموت الاخرة القبر يوم القيامة"),
 ("النصيحة","Sincere counsel","النصيحه نصح"),
]

import glob as _g
def glob_len(d): return len(_g.glob(os.path.join(d, 'v*.txt')))
def log(*a): print(*a, flush=True)
one = lambda s: db.execute(s).fetchone()[0]
t0 = time.time()
if os.path.exists(DB): os.remove(DB)
for ext in ("-wal","-shm"):
    if os.path.exists(DB+ext): os.remove(DB+ext)
db = sqlite3.connect(DB); db.executescript(SCHEMA)

def src(code, name, kind, origin, edition, lic, riwayah=None):
    return db.execute("INSERT INTO sources(code,name,kind,origin,edition,riwayah,license_status)"
                      " VALUES(?,?,?,?,?,?,?)",
                      (code,name,kind,origin,edition,riwayah,lic)).lastrowid

# ═══════════ القرآن ═══════════
s_q  = src("mushaf.uthmani","القرآن الكريم برسم العثماني","quran","Al Quran Cloud / Tanzil",
           "quran-uthmani","يحتاج مراجعة ترخيص","حفص عن عاصم")
s_tf = src("tafsir.muyassar","التفسير الميسر","tafsir","Al Quran Cloud","ar.muyassar",
           "يحتاج إذنًا للاستخدام التجاري")
s_tr = src("trans.saheeh","Saheeh International","translation","Al Quran Cloud","en.sahih",
           "يحتاج إذنًا للاستخدام التجاري")

s_q2 = src("quran.com.uthmani","القرآن الكريم — النص العثماني (المصدر المرجعي الثاني)","quran",
           "Quran.com API v4","uthmani","يحتاج مراجعة ترخيص","حفص عن عاصم")

q  = json.load(open(f"{RAW}/quran-uthmani.json"))["data"]
q2 = {v["verse_key"]: clean(v["text_uthmani"])
      for v in json.load(open(f"{RAW}/quran-com-uthmani.json"))["verses"]}
plain_map = {}
vstat = {"exact":0, "orthographic":0, "conflict":0, "missing":0}
n_bism = 0
for s in q["surahs"]:
    db.execute("INSERT INTO surahs VALUES(?,?,?,?,?,?)",
               (s["number"], s["name"], s["englishName"],
                "مكية" if s["revelationType"]=="Meccan" else "مدنية",
                s["revelationType"], len(s["ayahs"])))
    for a in s["ayahs"]:
        txt = clean(a["text"])
        # البسملة تُلحق بالآية الأولى في بعض النسخ — تُنزع لأنها ليست منها
        txt, did = strip_leading_basmala(txt, s["number"], a["numberInSurah"], searchable)
        n_bism += did
        pl  = searchable(txt)
        key = f"{s['number']}:{a['numberInSurah']}"
        alt = q2.get(key)
        st  = compare(txt, alt, fingerprint) if alt else "missing"
        vstat[st] = vstat.get(st, 0) + 1
        fits = len(txt) <= AYAH_CARD_MAX
        ok   = fits and text_released(st)
        why  = None if ok else ("اختلف المصدران في النص" if not text_released(st)
                                else "الآية أطول من مساحة البطاقة")
        if not text_released(st):
            db.execute("INSERT OR IGNORE INTO review_queue VALUES('quran',?,?,?)",
                       (key, "اختلاف بين المصدرين", (alt or "")[:300]))
        db.execute("""INSERT INTO ayat(id,surah,ayah,text,plain,fingerprint,plain_fp,page,juz,
                      hizb,sajda,char_len,card_ok,text_secondary,verify_status,
                      basmala_stripped,block_reason,source_id)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (a["number"], s["number"], a["numberInSurah"], txt, pl,
                    fingerprint(txt), fingerprint(pl), a.get("page"), a.get("juz"),
                    a.get("hizbQuarter"), 1 if a.get("sajda") else 0,
                    len(txt), 1 if ok else 0, alt, st, 1 if did else 0, why, s_q))
        db.execute("INSERT INTO ayat_fts(rowid,text) VALUES(?,?)", (a["number"], pl))
        plain_map.setdefault(fingerprint(pl), []).append(a["number"])

# المتشابه اللفظي: آيات نصها المجرّد يتكرر في مواضع أخرى
mut = 0
for fp, ids in plain_map.items():
    if len(ids) > 1:
        for i in ids:
            db.execute("UPDATE ayat SET mutashabih_group=? WHERE id=?", (fp[:12], i)); mut += 1
log(f"القرآن: بسملة نُزعت من {n_bism} سورة · متشابه لفظي {mut} آية")
log("  التحقق المزدوج: " + " · ".join(f"{k} {v}" for k,v in vstat.items() if v))

for path, sid, tbl, lang in [(f"{RAW}/ar.muyassar.json", s_tf, "ayah_tafsir", None),
                             (f"{RAW}/en.sahih.json",    s_tr, "ayah_translation", "en")]:
    d = json.load(open(path))["data"]
    for s in d["surahs"]:
        for a in s["ayahs"]:
            t = clean(a["text"])
            if lang:
                db.execute("INSERT OR IGNORE INTO ayah_translation VALUES(?,?,?,?,?,?)",
                           (s["number"], a["numberInSurah"], sid, lang, t, fingerprint(t)))
            else:
                db.execute("INSERT OR IGNORE INTO ayah_tafsir VALUES(?,?,?,?,?)",
                           (s["number"], a["numberInSurah"], sid, t, fingerprint(t)))

# ═══════════ الحديث ═══════════
# قاعدة الدرجة: لا تُكتب درجة إلا بمستند.
#   • الصحيحان: بشرط صاحبيهما، وهو مستند معلوم.
#   • بقية الكتب: حكم محدِّث مسمّى من المصدر المرجعي الثاني.
#   • ما لا حكم له، أو حكمه ضعيف فما دون: لا يُنتَج.
GRADE_RULE = {"bukhari": ("صحيح", "شرط الإمام البخاري في جامعه الصحيح"),
              "muslim":  ("صحيح", "شرط الإمام مسلم في صحيحه")}
BOOKS = ["bukhari","muslim","abudawud","tirmidhi","nasai","ibnmajah","malik","ahmed"]
s_h  = src("hadith.9books","الكتب التسعة — نصوص مفهرسة","hadith",
           "hadith-json v1.2.0 (Sunnah.com)","v1.2.0","يحتاج مراجعة ترخيص")
s_h3 = src("jami.kamil","الجامع الكامل في الحديث الصحيح الشامل — ضياء الرحمن الأعظمي",
           "hadith-witness","أرشيف الإنترنت — نصّ مستخرج آليًا","١٢ مجلدًا",
           "شاهد لا مصدر نص · يحتاج مراجعة ترخيص")
s_h2 = src("hadith.graded","أحكام المحدِّثين على الكتب الستة","hadith",
           "hadith-api (Sunnah.com)","ara-*","يحتاج مراجعة ترخيص")

hid = 0; stats = []; gstat = {"book":0,"scholar":0,"none":0,"weak":0}
for bid, code in enumerate(BOOKS, 1):
    p = f"{RAW}/hadith/{code}.json"
    if not os.path.exists(p): continue
    d = json.load(open(p)); md = d.get("metadata", {})
    gr = GRADE_RULE.get(code)

    # فهرس الأحكام من المصدر الثاني، مفتاحه نصُّ الحديث لا رقمه
    # (المصدران يرقّمان بطريقتين مختلفتين، فالنص هو الرابط الموثوق)
    GRADES, SECOND = {}, {}
    gp = f"{RAW}/grades/{code}.json"
    if os.path.exists(gp):
        for h in json.load(open(gp))["hadiths"]:
            k = core_key(h.get("text") or "")
            if not k: continue
            SECOND.setdefault(k, h.get("text") or "")
            if h.get("grades"): GRADES.setdefault(k, h["grades"])

    db.execute("INSERT INTO books VALUES(?,?,?,?,?,?,?,?)",
               (bid, code, md.get("arabic",{}).get("title",""), md.get("english",{}).get("title",""),
                md.get("arabic",{}).get("author",""), len(d.get("hadiths",[])),
                gr[1] if gr else "حكم محدِّث مسمّى", s_h))
    for c in d.get("chapters", []):
        db.execute("INSERT OR IGNORE INTO chapters VALUES(?,?,?,?)",
                   (bid, c.get("id"), c.get("arabic",""), c.get("english","")))
    nc = 0
    for h in d.get("hadiths", []):
        hid += 1
        ar = clean(h.get("arabic") or "")
        en = h.get("english") or {}
        en_txt = en.get("text","") if isinstance(en, dict) else (en or "")
        en_nar = en.get("narrator","") if isinstance(en, dict) else ""
        matn, method, conf = extract_matn(ar)
        nar_ar, _ = extract_narrator(ar)
        ck = core_key(ar)          # مفتاح مطابقة المصدر الثاني (النص الكامل)
        mk = core_key(matn) if matn else None   # مفتاح التخريج المتقاطع (المتن وحده)

        # التحقق المزدوج: هل صدر الحديث نفسه موجود في المصدر الثاني؟
        vst = "confirmed" if ck in SECOND else "single-source"

        grade = raw = by = allg = basis = gsrc = None
        if gr:
            grade, basis, gsrc = gr[0], gr[1], "book_condition"; gstat["book"] += 1
        else:
            g = G.pick(GRADES.get(ck, []))
            if g:
                grade, raw, by = g["grade"], g["raw"], g["by"]
                allg  = json.dumps(g["all"], ensure_ascii=False)
                basis = f"حكم {by}"; gsrc = "scholar"
                gstat["scholar" if G.releasable(grade) else "weak"] += 1
            else:
                gstat["none"] += 1

        ready, why = is_card_ready(matn, conf)
        if ready and not grade:
            ready, why = False, "لا حكم موثّق على هذا الحديث"
        if ready and not G.releasable(grade) and gsrc != "book_condition":
            ready, why = False, f"الحكم: {grade} — لا يُنشر"
        if ready and vst != "confirmed":
            ready, why = False, "لم يتأكّد النص من مصدر ثانٍ"
        if ready: nc += 1
        else:
            db.execute("INSERT OR IGNORE INTO review_queue VALUES('hadith',?,?,?)",
                       (f"{code}:{h.get('idInBook')}", why or "غير صالح", (matn or ar)[:200]))

        db.execute("""INSERT INTO hadiths(id,book_id,number_in_book,chapter_id,full_ar,matn,
                      matn_method,matn_conf,matn_fp,core_key,match_key,text_en,narrator_ar,narrator_en,
                      grade,grade_raw,grade_by,grade_all,grade_basis,grade_source,verify_status,
                      char_len,card_ok,block_reason,fingerprint,source_id)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (hid, bid, h.get("idInBook"), h.get("chapterId"), ar,
                    matn, method, conf, fingerprint(matn) if matn else None, mk, ck,
                    en_txt, nar_ar, en_nar,
                    grade, raw, by, allg, basis, gsrc, vst,
                    len(matn) if matn else 0, 1 if ready else 0, why,
                    fingerprint(ar), s_h))
        db.execute("INSERT INTO hadith_fts(rowid,text) VALUES(?,?)",
                   (hid, searchable(matn or ar)))
    stats.append((code, len(d.get("hadiths",[])), nc))
log("الأحكام: بشرط الكتاب %d · بحكم محدِّث %d · ضعيف فما دون %d · بلا حكم %d"
    % (gstat["book"], gstat["scholar"], gstat["weak"], gstat["none"]))

# ═══════════ شاهد الجامع الكامل ═══════════
JD = os.path.join(RAW, "jami")
if os.path.isdir(JD) and glob_len(JD):
    jm = Jami(JD)
    log(f"الجامع الكامل: {jm.word_count:,} كلمة مفهرسة من {len(jm.vols)} مجلدًا")
    hit = pos_g = neg_g = unlocked = conflicted = 0
    rows = db.execute("""SELECT id, matn, grade, grade_source, card_ok, block_reason, verify_status
                         FROM hadiths WHERE matn IS NOT NULL""").fetchall()
    for hid_, matn_, grade_, gsrc_, card_, why_, vst_ in rows:
        f = jm.lookup(matn_)
        if not f: continue
        hit += 1
        conflict = None
        new_grade, new_basis, new_src, new_card, new_why = grade_, None, gsrc_, card_, why_

        if f["grade_polarity"] == "positive":
            pos_g += 1
            ar = "صحيح" if f["grade"] in ("صحيح", "صح") else "حسن"
            if not grade_:
                # كان محجوبًا لانعدام الحكم — إيراد الأعظمي وتصحيحه مستندٌ معلوم
                new_grade, new_src = ar, "jami"
                new_basis = "إيراد ضياء الرحمن الأعظمي في الجامع الكامل مع تصحيحه"
                ok2, why2 = is_card_ready(matn_, 0.95)
                # تصحيح الأعظمي يرفع الحجب عن الحكم وحده — شرط المصدر الثاني باقٍ
                if vst_ != "confirmed":
                    ok2, why2 = False, "لم يتأكّد النص من مصدر ثانٍ"
                if (why_ or "").startswith(("لا حكم", "الحكم")):
                    new_card, new_why = (1, None) if ok2 else (0, why2)
                    unlocked += new_card
        elif f["grade_polarity"] == "negative":
            neg_g += 1
            conflict = f["grade"]
            if grade_ and G.releasable(grade_):
                conflicted += 1
                new_card, new_why = 0, f"تعارض: حكم {grade_} مقابل «{f['grade']}» في الجامع الكامل"
                db.execute("INSERT OR IGNORE INTO review_queue VALUES('hadith',?,?,?)",
                           (f"jami-conflict:{hid_}", "تعارض بين حكمين", (matn_ or "")[:200]))

        db.execute("""UPDATE hadiths SET jami_vol=?, jami_book=?, jami_bab=?, jami_hits=?,
                      jami_grade=?, jami_polarity=?, jami_takhrij=?, jami_conflict=?,
                      grade=COALESCE(?,grade), grade_basis=COALESCE(?,grade_basis),
                      grade_source=?, card_ok=?, block_reason=?
                      WHERE id=?""",
                   (f["vol"], f["book"], f["bab"], f["hits"], f["grade"], f["grade_polarity"],
                    f["takhrij"], conflict, new_grade if new_src == "jami" else None,
                    new_basis, new_src, new_card, new_why, hid_))
    log(f"  شهد الأعظمي لـ {hit} حديثًا · صحّح {pos_g} · تحفّظ على {neg_g}")
    log(f"  فُكّ الحجب عن {unlocked} حديثًا بتصحيحه · حُجب {conflicted} للتعارض")
else:
    log("الجامع الكامل: الملفات غير موجودة — تخطّي")

# التخريج المتقاطع
db.execute("""INSERT INTO takhrij(group_key,hadith_id,book_id,number_in_book)
              SELECT core_key,id,book_id,number_in_book FROM hadiths
              WHERE core_key IS NOT NULL AND core_key<>''
                AND core_key IN (SELECT core_key FROM hadiths
                                 WHERE core_key IS NOT NULL AND core_key<>''
                                 GROUP BY core_key HAVING COUNT(DISTINCT book_id)>1)""")

# ═══════════ أحكام المراجعين — قرارُ عالِمٍ في محجوبٍ حُكميّ ═══════════
from falah import rulings as RU
_rul, _bad = RU.load()
if _rul:
    applied = refused = kept = 0
    q = "SELECT id, matn_fp, block_reason, card_ok, matn, verify_status FROM hadiths " \
        "WHERE matn_fp IN (%s)" % ",".join("?" * len(_rul))
    for hid_, fp_, why_, card_, matn_, vst_ in db.execute(q, tuple(_rul)).fetchall():
        rul = _rul[fp_]
        if rul["decision"] == "block":
            db.execute("UPDATE hadiths SET card_ok=0, block_reason=? WHERE id=?",
                       (f"قرار مراجعة: {rul['reviewer']}", hid_))
            kept += 1
            continue
        if not RU.applies_to(rul, why_):
            refused += 1               # حجبٌ آليّ لا يرفعه توقيع
            continue
        ok2, why2 = is_card_ready(matn_, 0.95)
        if vst_ != "confirmed":        # شرط المصدر الثاني باقٍ فوق كل قرار
            ok2, why2 = False, "لم يتأكّد النص من مصدر ثانٍ"
        db.execute("""UPDATE hadiths SET grade=?, grade_basis=?, grade_source='ruling',
                      card_ok=?, block_reason=? WHERE id=?""",
                   (rul["grade"], RU.basis_line(rul), 1 if ok2 else 0,
                    None if ok2 else why2, hid_))
        applied += int(ok2); refused += int(not ok2)
    log(f"أحكام المراجعين: {len(_rul)} قرارًا · فُكّ الحجب عن {applied}"
        f" · بقي محجوبًا {refused} · أُبقي بطلبهم {kept}")
if _bad:
    log(f"  قرارات مرفوضة الصيغة: {len(_bad)}")
    for r_, why_ in _bad[:5]:
        log(f"  ✗ {why_}: {str(r_.get('ref') or r_.get('fp'))[:40]}")

# ═══════════ القرّاء ═══════════
s_rec = src("recitations","تلاوات آية بآية — قرّاء معتمدون","audio",
            "EveryAyah / Islamic Network CDN","versebyverse","يحتاج مراجعة ترخيص")
for code, name, riw, scheme, folder in RECITERS:
    db.execute("INSERT INTO reciters VALUES(?,?,?,?,?,1)", (code, name, riw, scheme, folder))
log(f"القرّاء: {len(RECITERS)} قارئًا في {len(set(r[2] for r in RECITERS))} رواية")

# ═══════════ الموسوعة الحديثية — متن وشرح وفوائد ═══════════
ENC = os.path.join(RAW, "enc")
if os.path.exists(os.path.join(ENC, "ar.json")):
    s_enc = src("hadeethenc","الموسوعة الحديثية — متن وشرح وفوائد","hadith",
                "HadeethEnc.com","v1","يحتاج مراجعة ترخيص")
    ar = json.load(open(os.path.join(ENC, "ar.json")))
    n_ok = 0
    for hid_, h in ar.items():
        full  = clean(h.get("hadeeth") or "")
        intro = clean(h.get("hadeeth_intro") or "")
        # المتن يبدأ بمقدمة الراوي («عن أبي موسى … قال:») — تُفصل ليصحّ
        # الربط بالكتب التسعة، وتُحفظ لتُعرض سطرَ راوٍ تحت النص.
        matn  = full[len(intro):].strip(' "«»:،') if intro and full.startswith(intro) else full
        gr   = (h.get("grade") or "").strip()
        # «صحيحان» تعني حديثين في مدخل واحد — لا يصلح بطاقةً مفردة
        ok   = bool(matn) and G.releasable(gr) and 20 <= len(matn) <= 400
        why  = None if ok else ("مدخلٌ يجمع حديثين" if gr == "صحيحان" else
                                f"الحكم: {gr}" if gr and not G.releasable(gr) else
                                "المتن خارج مساحة البطاقة" if matn else "بلا متن")
        n_ok += ok
        db.execute("""INSERT INTO enc VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (int(hid_), h.get("title"), intro, matn,
                    fingerprint(matn), core_key(matn), gr, h.get("attribution"),
                    h.get("reference"), clean(h.get("explanation") or ""),
                    json.dumps(h.get("hints") or [], ensure_ascii=False),
                    json.dumps(h.get("words_meanings") or [], ensure_ascii=False),
                    len(matn), 1 if ok else 0, why, s_enc))
        db.execute("INSERT INTO enc_fts(rowid,text) VALUES(?,?)", (int(hid_), searchable(matn)))
        if not ok:
            db.execute("INSERT OR IGNORE INTO review_queue VALUES('enc',?,?,?)",
                       (hid_, why or "غير صالح", matn[:200]))
    # الترجمات المتاحة
    n_tr = 0
    for lang in ("en", "ur", "id", "fr", "tr"):
        p = os.path.join(ENC, f"{lang}.json")
        if not os.path.exists(p): continue
        for hid_, h in json.load(open(p)).items():
            db.execute("INSERT OR IGNORE INTO enc_tr VALUES(?,?,?,?,?,?)",
                       (int(hid_), lang, h.get("title"), clean(h.get("hadeeth") or ""),
                        clean(h.get("explanation") or ""),
                        json.dumps(h.get("hints") or [], ensure_ascii=False)))
            n_tr += 1
    # الربط بالكتب التسعة عند تطابق المتن
    db.execute("""INSERT OR IGNORE INTO enc_link
                  SELECT e.id, h.id FROM enc e JOIN hadiths h ON h.core_key = e.core_key
                  WHERE e.core_key IS NOT NULL AND e.core_key <> ''""")
    linked = one("SELECT COUNT(DISTINCT enc_id) FROM enc_link")
    log(f"الموسوعة: {len(ar)} حديثًا · للبطاقة {n_ok} · ترجمات {n_tr} · مربوط بالكتب {linked}")

# ═══════════ فهرس الموضوعات ═══════════
from falah.text import fts_query
for i,(ar,en,terms) in enumerate(TOPICS, 1):
    db.execute("INSERT INTO topics VALUES(?,?,?,?)", (i, ar, en, terms))
    for word in terms.split():
        m = fts_query(word)
        if not m: continue
        for r in db.execute("""SELECT a.id FROM ayat_fts f JOIN ayat a ON a.id=f.rowid
                               WHERE ayat_fts MATCH ? AND a.card_ok=1 LIMIT 12""", (m,)):
            db.execute("INSERT OR IGNORE INTO topic_items VALUES(?,?,?,?)", (i,"quran",r[0],0))
        for r in db.execute("""SELECT h.id FROM hadith_fts f JOIN hadiths h ON h.id=f.rowid
                               WHERE hadith_fts MATCH ? AND h.card_ok=1 LIMIT 12""", (m,)):
            db.execute("INSERT OR IGNORE INTO topic_items VALUES(?,?,?,?)", (i,"hadith",r[0],0))

db.commit()

# ═══════════ ربط شرح الموسوعة بالكتب التسعة (مطابقة المتن) ═══════════
_encidx = {}
for _r in db.execute("SELECT id, matn FROM enc WHERE explanation IS NOT NULL AND matn IS NOT NULL"):
    _encidx.setdefault(core_key(_r[1], 6), _r[0])
_added = 0
for _hid, _matn in db.execute("SELECT id, matn FROM hadiths WHERE matn IS NOT NULL").fetchall():
    _eid = _encidx.get(core_key(_matn, 6))
    if _eid:
        cur = db.execute("INSERT OR IGNORE INTO enc_link(enc_id,hadith_id) VALUES(?,?)", (_eid, _hid))
        _added += cur.rowcount
db.commit()
log(f"شرح الموسوعة: رُبط {_added} حديثًا إضافيًّا بمطابقة المتن")

# ═══════════ مصالحة القاعدة مع محرّك الفحص ═══════════
# الحكم للمحرّك في الاتجاهين: يُنزع العلم عمّا لا يجتاز الخمسة والعشرين،
# ويُوضع على ما يجتازها. فلا يَعِد الجدولُ بما يرفضه الفحص، ولا يحجب ما يقبله.
try:
    del jm                      # فهرس الجامع الكامل ثقيلٌ في الذاكرة، وقد فرغنا منه
except NameError:
    pass
import gc; gc.collect()
import api as _api
from falah import verify as _V
_rc = sqlite3.connect(DB); _rc.row_factory = sqlite3.Row
_up = _down = 0

def _settle(rows, build_card, sql):
    """يمرّ صفًّا صفًّا بلا تحميل الجدول في الذاكرة."""
    global _up, _down
    pend = []
    for row in rows:
        try:
            it, cx = build_card(row)
            rep = _V.run(it, cx) if it else None
        except Exception:
            it, rep = None, None
        ok  = bool(rep) and rep["ok"]
        why = None if ok else ("، ".join(rep["failed"]) if rep else "تعذّر بناء البطاقة")
        if bool(row["card_ok"]) != ok:
            pend.append((1 if ok else 0, why, row["key"]))
            if ok: _up += 1
            else:  _down += 1
        if len(pend) >= 500:
            db.executemany(sql, pend); pend.clear()
    if pend: db.executemany(sql, pend)

_settle(_rc.execute("SELECT id AS key, surah, ayah, card_ok FROM ayat"),
        lambda r: _api.quran_card(_rc, r["surah"], r["ayah"], None, True, True),
        "UPDATE ayat SET card_ok=?, block_reason=? WHERE id=?")

_settle(_rc.execute("""SELECT h.id AS key, h.card_ok, b.code, h.number_in_book AS no
                       FROM hadiths h JOIN books b ON b.id=h.book_id
                       WHERE h.matn IS NOT NULL"""),
        lambda r: _api.hadith_card(_rc, r["code"], r["no"]),
        "UPDATE hadiths SET card_ok=?, block_reason=? WHERE id=?")

_settle(_rc.execute("SELECT id AS key, id, card_ok FROM enc"),
        lambda r: _api.enc_card(_rc, r["id"]),
        "UPDATE enc SET card_ok=?, block_reason=? WHERE id=?")

_rc.close(); db.commit(); gc.collect()
log(f"مصالحة الفحص: وُضع العلم على {_up} · نُزع عن {_down} — الحكم لمحرّك الفحص وحده")

db.execute("ANALYZE"); db.commit()

# ═══════════ التقرير ═══════════
log("\n── طبقة المحتوى ──")
log(f"الآيات        {one('SELECT COUNT(*) FROM ayat'):>7}   صالحة للبطاقة {one('SELECT COUNT(*) FROM ayat WHERE card_ok=1'):>6}")
log(f"التفسير       {one('SELECT COUNT(*) FROM ayah_tafsir'):>7}")
log(f"الترجمة       {one('SELECT COUNT(*) FROM ayah_translation'):>7}")
log(f"الأحاديث      {one('SELECT COUNT(*) FROM hadiths'):>7}   صالحة للبطاقة {one('SELECT COUNT(*) FROM hadiths WHERE card_ok=1'):>6}")
log(f"فُصل المتن    {one('SELECT COUNT(*) FROM hadiths WHERE matn IS NOT NULL'):>7}")
log(f"الراوي معلوم  {one('SELECT COUNT(*) FROM hadiths WHERE narrator_ar IS NOT NULL'):>7}")
log(f"تخريج متقاطع  {one('SELECT COUNT(DISTINCT group_key) FROM takhrij'):>7} مجموعة")
log(f"شاهد الأعظمي  {one('SELECT COUNT(*) FROM hadiths WHERE jami_vol IS NOT NULL'):>7}   منها للبطاقات {one('SELECT COUNT(*) FROM hadiths WHERE jami_vol IS NOT NULL AND card_ok=1'):>6}")
jg = one("SELECT COUNT(*) FROM hadiths WHERE grade_source='jami'")
log(f"  بحكم الأعظمي {jg:>5}   بابٌ معلوم {one('SELECT COUNT(*) FROM hadiths WHERE jami_bab IS NOT NULL'):>6}   تخريجه {one('SELECT COUNT(*) FROM hadiths WHERE jami_takhrij IS NOT NULL'):>6}")
log(f"الموضوعات     {one('SELECT COUNT(*) FROM topics'):>7}   مدخلاتها {one('SELECT COUNT(*) FROM topic_items'):>6}")
log(f"القرّاء        {one('SELECT COUNT(*) FROM reciters'):>7}   روايات {one('SELECT COUNT(DISTINCT riwayah) FROM reciters'):>6}")
enc_sharh = one("SELECT COUNT(*) FROM enc WHERE explanation IS NOT NULL AND explanation <> ''")
log(f"الموسوعة      {one('SELECT COUNT(*) FROM enc'):>7}   للبطاقة {one('SELECT COUNT(*) FROM enc WHERE card_ok=1'):>6}   بشرح {enc_sharh:>6}")
log("\nالكتب:")
for code, tot, card in stats:
    n = db.execute("SELECT name_ar FROM books WHERE code=?", (code,)).fetchone()[0]
    log(f"  {n:<28} {tot:>6}   للبطاقة {card:>5}")
log(f"\nالحجم {round(os.path.getsize(DB)/1e6,1)} MB · البناء {round(time.time()-t0,1)} ثانية")
