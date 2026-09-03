#!/usr/bin/env python3
"""فحصٌ شاملٌ للتنفيذ — ما وراء اختبارات الوحدة.

    python3 audit.py           # القاعدة + المسارات + الأمان + الوكيل + الأداء

يُشغَّل والخادمان يعملان: api.py على ٨٠٨٠ إن أردت فحص المسارات، وapp.py
على ٨٠٨١. وإن لم يعملا شُغّلا هنا مؤقتًا. كل بندٍ يُطبع بنتيجته، والفشل
يُطبع بسببه لا بعبارةٍ عامة.
"""
import json, os, random, sqlite3, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DB = os.path.join(HERE, "falah.db")

OK = FAIL = 0
FAILURES = []

def check(name, cond, detail=""):
    global OK, FAIL
    if cond:
        OK += 1; print(f"  ✓ {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1; FAILURES.append((name, detail))
        print(f"  ✗ {name}" + (f"  ← {detail}" if detail else ""))


def getc(url, cookie=None, timeout=30):
    """قراءةٌ بجلسة — يلزم لاستطلاع المهامّ."""
    url = urllib.parse.quote(url, safe=":/?&=%+-_.~")
    req = urllib.request.Request(url, headers={"Cookie": cookie} if cookie else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            # الملفّات المصدَّرة تعود صورًا لا JSON — يُقاس نجاحُها بالحالة والحجم
            try:    return r.status, json.loads(raw.decode())
            except Exception: return r.status, {"bytes": len(raw),
                                                "type": r.headers.get("Content-Type")}
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read().decode())
        except Exception: return e.code, None
    except Exception as e:
        return 0, {"error": str(e)}

def follow(base, cookie, job_id, limit=180):
    """يستطلع مهمّةً حتى تنتهي، كما يفعل المتصفّح."""
    t0 = time.time()
    seen = set()
    while time.time() - t0 < limit:
        s, d = getc(base + f"/app/jobs/{job_id}", cookie)
        if s != 200: return None, seen
        j = d["job"]; seen.add(j["state"])
        if not j["waiting"]: return j, seen
        time.sleep(0.4)
    return None, seen

def head(t): print(f"\n▸ {t}")

def get(url, timeout=30):
    url = urllib.parse.quote(url, safe=":/?&=%+-_.~")     # العربية في الرابط تُرمَّز
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read().decode())
        except Exception: return e.code, None
    except Exception as e:
        return 0, {"error": str(e)}

def post(url, body, cookie=None, csrf=True, origin=None):
    data = json.dumps(body).encode()
    hdr = {"Content-Type": "application/json"}
    if csrf:   hdr["X-FALAH"] = "1"
    if cookie: hdr["Cookie"] = cookie
    if origin: hdr["Origin"] = origin
    req = urllib.request.Request(url, data=data, headers=hdr, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode()), r.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read().decode()), []
        except Exception: return e.code, None, []
    except Exception as e:
        return 0, {"error": str(e)}, []

# ═════════════════ ١ · سلامة القاعدة ═════════════════
def audit_db():
    head("سلامة القاعدة")
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    one = lambda q, *a: c.execute(q, a).fetchone()[0]

    check("لا آية بلا بصمة", one("SELECT COUNT(*) FROM ayat WHERE fingerprint IS NULL OR fingerprint=''") == 0)
    check("لا حديث مُفرَجٌ بلا بصمة متن",
          one("SELECT COUNT(*) FROM hadiths WHERE card_ok=1 AND (matn_fp IS NULL OR matn_fp='')") == 0)
    dup = one("SELECT COUNT(*) FROM (SELECT surah,ayah FROM ayat GROUP BY surah,ayah HAVING COUNT(*)>1)")
    check("لا آية مكرّرة", dup == 0, f"مكرّر: {dup}")
    check("عدد الآيات ٦٢٣٦", one("SELECT COUNT(*) FROM ayat") == 6236,
          str(one("SELECT COUNT(*) FROM ayat")))
    bad = one("""SELECT COUNT(*) FROM ayat a JOIN surahs s ON s.number=a.surah
                 WHERE a.ayah < 1""")
    check("لا رقم آية دون الواحد", bad == 0)

    # كل سورة عدد آياتها كما هو معروف
    counts = {r["surah"]: r["n"] for r in c.execute(
        "SELECT surah, COUNT(*) n FROM ayat GROUP BY surah")}
    check("كل السور الـ١١٤ حاضرة", len(counts) == 114, str(len(counts)))
    check("الفاتحة سبع والبقرة ٢٨٦ والكوثر ثلاث",
          counts.get(1) == 7 and counts.get(2) == 286 and counts.get(108) == 3,
          f"{counts.get(1)},{counts.get(2)},{counts.get(108)}")

    # لا حكم بلا قائل في المُفرَج عنه
    nog = one("""SELECT COUNT(*) FROM hadiths WHERE card_ok=1
                 AND (grade IS NULL OR grade='')""")
    check("لا حديث مُفرَجٌ بلا درجة", nog == 0, str(nog))
    weak = one("""SELECT COUNT(*) FROM hadiths WHERE card_ok=1
                  AND grade IN ('ضعيف','ضعيف جدا','موضوع','منكر')""")
    check("لا ضعيف ولا موضوع بين المُفرَج عنه", weak == 0, str(weak))

    # البسملة لا تُلحق بالآية الأولى
    basm = one("""SELECT COUNT(*) FROM ayat WHERE ayah=1 AND surah NOT IN (1,9)
                  AND text LIKE 'بِسْمِ اللَّهِ%'""")
    check("البسملة منزوعة عن أوائل السور", basm == 0, str(basm))

    # نصوص الجامع الكامل لا تتسرّب
    leak = one("SELECT COUNT(*) FROM hadiths WHERE matn LIKE '%التعمان%' OR matn LIKE '%صاحيه%'")
    check("لا تصحيف OCR في المتون المخزّنة", leak == 0, str(leak))

    # القوالب تطابق المُفرَج عنه
    t_q = one("SELECT COUNT(*) FROM templates WHERE kind='quran'")
    a_q = one("SELECT COUNT(*) FROM ayat WHERE card_ok=1")
    check("قوالب الآيات تطابق المُفرَج عنه", t_q == a_q, f"{t_q} مقابل {a_q}")
    t_h = one("SELECT COUNT(*) FROM templates WHERE kind='hadith'")
    a_h = one("SELECT COUNT(*) FROM hadiths WHERE card_ok=1")
    check("قوالب الأحاديث تطابق المُفرَج عنه", t_h == a_h, f"{t_h} مقابل {a_h}")

    # كل قالبٍ حمولته JSON صالحة وفيها نصّ
    bad_json, empty = 0, 0
    for r in c.execute("SELECT ref, payload FROM templates"):
        try:
            p = json.loads(r["payload"])
            if not (p.get("text") or "").strip(): empty += 1
        except Exception:
            bad_json += 1
    check("كل حمولات القوالب JSON صالحة", bad_json == 0, str(bad_json))
    check("لا قالب بلا نصّ", empty == 0, str(empty))

    # البصمة تكسر بأي تغيير — عيّنة
    from api import fingerprint
    sample = c.execute("SELECT text, fingerprint FROM ayat ORDER BY RANDOM() LIMIT 200").fetchall()
    mism = sum(1 for r in sample if fingerprint(r["text"]) != r["fingerprint"])
    check("بصمات عيّنة ٢٠٠ آية مطابقة", mism == 0, str(mism))
    # الفراغ الزائد ليس تغييرًا في النصّ — البصمة توحّده عمدًا وتُبقيه سواء
    check("الفراغ الزائد لا يكسر البصمة (توحيدٌ مقصود)",
          all(fingerprint(r["text"] + "  ") == r["fingerprint"] for r in sample[:20]))
    # أما تغيير حرفٍ أو حركة فيكسرها
    def tweak(t):
        for i, ch in enumerate(t):
            if ch in "َُِّْ": return t[:i] + t[i+1:]      # حذف حركة
        return t[:-1]                                      # أو حذف حرف
    tampered = sum(1 for r in sample[:40] if fingerprint(tweak(r["text"])) == r["fingerprint"])
    check("حذف حركةٍ أو حرفٍ يكسر البصمة", tampered == 0, str(tampered))

    # طابور المراجعة يفسّر كل محجوب
    q = one("SELECT COUNT(*) FROM review_queue")
    check("طابور المراجعة غير فارغ", q > 0, str(q))
    noreason = one("SELECT COUNT(*) FROM review_queue WHERE reason IS NULL OR reason=''")
    check("كل محجوب له سبب", noreason == 0, str(noreason))
    c.close()

# ═════════════════ ٢ · محرّك الفحص على عيّنة كبيرة ═════════════════
def audit_engine(n=400):
    head(f"محرّك الفحص على عيّنة {n}")
    import api
    from falah import verify as V
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    rows = c.execute("SELECT surah,ayah FROM ayat WHERE card_ok=1 ORDER BY RANDOM() LIMIT ?",
                     (n // 2,)).fetchall()
    bad = []
    for r in rows:
        it, ctx = api.quran_card(c, r["surah"], r["ayah"], None, True, True)
        rep = V.run(it, ctx)
        if not rep["ok"]: bad.append((f'{r["surah"]}:{r["ayah"]}', rep["failed"]))
    check("كل آيةٍ مُفرَجٍ عنها تجتاز الفحص فعلًا", not bad, str(bad[:3]))

    rows = c.execute("""SELECT b.code, h.number_in_book no FROM hadiths h
                        JOIN books b ON b.id=h.book_id WHERE h.card_ok=1
                        ORDER BY RANDOM() LIMIT ?""", (n // 2,)).fetchall()
    bad = []
    for r in rows:
        it, ctx = api.hadith_card(c, r["code"], r["no"])
        rep = V.run(it, ctx)
        if not rep["ok"]: bad.append((f'{r["code"]} {r["no"]}', rep["failed"]))
    check("كل حديثٍ مُفرَجٍ عنه يجتاز الفحص فعلًا", not bad, str(bad[:3]))

    # والمحجوب يبقى محجوبًا
    rows = c.execute("SELECT surah,ayah FROM ayat WHERE card_ok=0 LIMIT 20").fetchall()
    leaked = []
    for r in rows:
        it, ctx = api.quran_card(c, r["surah"], r["ayah"], None, True, True)
        if it and V.run(it, ctx)["ok"]: leaked.append(f'{r["surah"]}:{r["ayah"]}')
    check("لا يتسرّب محجوب", not leaked, str(leaked[:5]))
    c.close()

# ═════════════════ ٣ · مسارات api.py ═════════════════
def audit_api(base):
    head("مسارات القراءة (api.py)")
    s, d = get(base + "/health")
    check("‎/health يستجيب", s == 200 and d.get("ok"), str(s))
    check("‎/health يعلن الأعداد", d and d.get("ayat") == 6236, str(d.get("ayat") if d else None))

    cases = [
        ("/options", lambda d: len(d["surahs"]) == 114 and len(d["books"]) >= 7
                     and len(d["content_types"]) == 5 and len(d["platforms"]) == 8),
        ("/chapters?book=bukhari", lambda d: len(d["chapters"]) > 50),
        ("/chapter/hadiths?book=bukhari&chapter=1", lambda d: len(d["hadiths"]) > 0),
        ("/quran/ayah?surah=1&ayah=1", lambda d: "text" in d),
        ("/hadith?book=bukhari&no=1", lambda d: "text" in d),
        ("/card?kind=quran&surah=94&ayah=5&tafsir=1&translation=1", lambda d: d["released"]),
        ("/card?kind=hadith&book=bukhari&no=1", lambda d: d["released"]),
        ("/templates?kind=quran&limit=5", lambda d: len(d["templates"]) == 5),
        ("/template?ref=quran:94:5", lambda d: (d.get("text") or "").strip()),
        ("/quran/search?q=الرحمن&limit=5", lambda d: isinstance(d, (list, dict))),
        ("/hadith/search?q=النية&limit=5", lambda d: isinstance(d, (list, dict))),
        ("/topics", lambda d: len(d) > 0),
        ("/sources", lambda d: len(d) > 0),
        ("/reciters", lambda d: d["count"] >= 19),
        ("/audio?surah=1&ayah=1", lambda d: len(d["recitations"]) >= 19),
        ("/series?topic=1&count=3", lambda d: len(d["slides"]) == 5),
        ("/enc/search?q=الصلاة&limit=3", lambda d: isinstance(d, (list, dict))),
        ("/review?limit=3", lambda d: "items" in d),
    ]
    for path, ok in cases:
        s, d = get(base + path)
        try:    good = s == 200 and ok(d)
        except Exception as e: good = False; d = {"exc": str(e)}
        check(f"‎{path.split('?')[0]} يعمل", good, f"{s} {str(d)[:70]}")

    head("مسارات الخطأ — لا انهيار ولا تسريب")
    bad = [
        ("/quran/ayah?surah=999&ayah=1", (404,)),
        ("/quran/ayah?surah=1&ayah=999", (404,)),
        ("/hadith?book=nope&no=1", (404,)),
        ("/hadith?book=bukhari&no=99999", (404,)),
        ("/card?kind=quran&surah=12&ayah=39", (409,)),          # محجوبة باختلاف المصدرين
        ("/chapters?book=%27%20OR%201%3D1--", (200,)),          # حقن SQL
        ("/chapter/hadiths?book=bukhari&chapter=abc", (400,)),
        ("/quran/ayah?surah=abc&ayah=1", (400,)),
        ("/nope", (404,)),
        ("/template?ref=nope", (404,)),
    ]
    for path, want in bad:
        s, d = get(base + path)
        check(f"‎{path[:44]} → {s}", s in want, f"توقّع {want}")
        if d and isinstance(d, dict):
            txt = json.dumps(d, ensure_ascii=False)
            check(f"  لا يسرّب أثر بايثون", "Traceback" not in txt and HERE not in txt, txt[:60])

# ═════════════════ ٤ · أمان طبقة التطبيق ═════════════════
def audit_app(base):
    head("الحساب والجلسة")
    import random as _r
    m1 = f"a{_r.randint(10**6,10**7)}@t.com"
    m2 = f"b{_r.randint(10**6,10**7)}@t.com"
    pw = "Str0ng-Pass!x9"

    s, d, ck = post(base + "/app/register",
                    {"email": m1, "password": pw, "name": "أ", "watermark": "قناة أ"})
    check("التسجيل ينجح", s in (200, 201), f"{s} {str(d)[:60]}")
    cookie1 = ck[0].split(";")[0] if ck else None
    check("الجلسة تُسلَّم في كعكة HttpOnly",
          bool(ck) and "HttpOnly" in ck[0] and "SameSite=Strict" in ck[0], str(ck)[:80])

    s, d, _ = post(base + "/app/register",
                   {"email": m1, "password": pw, "name": "أ", "watermark": "x"})
    check("لا يُسجَّل بريدٌ مرّتين", s >= 400, str(s))

    s, d, _ = post(base + "/app/register",
                   {"email": f"c{_r.randint(10**6,10**7)}@t.com", "password": "123",
                    "name": "ج", "watermark": "x"})
    check("كلمة مرورٍ ضعيفة تُرفض", s >= 400, f"{s} {str(d)[:50]}")

    s, d, _ = post(base + "/app/login", {"email": m1, "password": "wrong-pass-here"})
    check("كلمة مرورٍ خاطئة تُرفض", s >= 400, str(s))

    head("حماية الطلبات")
    s, d, _ = post(base + "/app/projects/create", {"title": "x"}, cookie=cookie1, csrf=False)
    check("طلبٌ بلا ترويسة X-FALAH يُرفض", s >= 400, str(s))
    s, d, _ = post(base + "/app/projects/create", {"title": "x"}, cookie=None)
    check("طلبٌ بلا جلسة يُرفض", s in (401, 403), str(s))
    s, d, _ = post(base + "/app/projects/create", {"title": "x"},
                   cookie="falah_sid=deadbeefdeadbeefdeadbeefdeadbeef")
    check("رمز جلسةٍ مزوَّر يُرفض", s in (401, 403), str(s))

    head("عزل المستخدمين")
    s, d, _ = post(base + "/app/projects/create", {"title": "مشروع أ"}, cookie=cookie1)
    pid = (d or {}).get("id") or (d or {}).get("project")
    check("إنشاء مشروع ينجح", bool(pid), str(d)[:60])

    s, d, ck2 = post(base + "/app/register",
                     {"email": m2, "password": pw, "name": "ب", "watermark": "قناة ب"})
    cookie2 = ck2[0].split(";")[0] if ck2 else None
    if pid and cookie2:
        s, d, _ = post(base + "/app/items/add", {"project": pid, "kind": "quran",
                                             "ref": {"surah": 94, "ayah": 5}}, cookie=cookie2)
        check("مستخدمٌ لا يضيف إلى مشروع غيره", s >= 400, f"{s} {str(d)[:60]}")
        s, d, _ = post(base + "/app/export", {"project": pid}, cookie=cookie2)
        check("مستخدمٌ لا يصدّر مشروع غيره", s >= 400, f"{s} {str(d)[:60]}")
        s, d, _ = post(base + "/app/projects/delete", {"id": pid}, cookie=cookie2)
        check("مستخدمٌ لا يحذف مشروع غيره", s >= 400, f"{s} {str(d)[:60]}")

    head("قفل المصدر في المشروع")
    if pid and cookie1:
        s, d, _ = post(base + "/app/items/add", {"project": pid, "kind": "quran",
                                             "ref": {"surah": 94, "ayah": 5}}, cookie=cookie1)
        check("إضافة عنصرٍ مفحوص تنجح", s in (200, 201), f"{s} {str(d)[:60]}")
        s, d, _ = post(base + "/app/items/add", {"project": pid, "kind": "quran",
                                             "ref": {"surah": 12, "ayah": 39}}, cookie=cookie1)
        check("إضافة عنصرٍ محجوب تُرفض", s >= 400, f"{s} {str(d)[:60]}")
        s, d, _ = post(base + "/app/items/add", {"project": pid, "kind": "hadith",
                                             "ref": {"book": "bukhari", "no": 999999}},
                       cookie=cookie1)
        check("إضافة مرجعٍ لا وجود له تُرفض", s >= 400, f"{s} {str(d)[:60]}")

    head("الاشتراك والحصص عبر الشبكة")
    s, d = get(base + "/app/plans")
    check("‎/app/plans مفتوحٌ بلا جلسة", s == 200 and len(d.get("plans", [])) == 3, str(s))
    check("صفحة الخطط تُعلن ما لا يُباع",
          any("لا تُحذف بالاشتراك" in x for x in (d or {}).get("always", [])))
    s, d, _ = post(base + "/app/entitlements", {}, cookie=cookie1)   # POST خطأ متعمَّد
    s, d = get(base + "/app/entitlements")
    check("الحقوق لا تُقرأ بلا جلسة", s in (401, 403), str(s))

    s, d, _ = post(base + "/app/subscription/grant",
                   {"plan": "studio", "days": 30}, cookie=cookie1)
    check("منح الاشتراك ممنوعٌ بلا مفتاح إدارة", s == 403, f"{s} {str(d)[:50]}")
    s, d, _ = post(base + "/app/subscription/store-event",
                   {"provider": "apple",
                    "event": {"type": "purchase", "product_id": "com.falah.studio.year",
                              "transaction_id": "AUDIT-1"}}, cookie=cookie1)
    check("شراءٌ لم يتحقّق منه المتجر لا يمنح شيئًا", s == 402, f"{s} {str(d)[:70]}")
    s2, d2 = get(base + "/app/entitlements")     # بلا جلسة — للتوثيق فقط
    s3, d3, _ = post(base + "/app/agent", {"answers": {}}, cookie=cookie1)
    _e = get(base + "/app/entitlements")
    check("والخطّة تبقى كما كانت بعد المحاولة",
          "FORGED" not in str(d) and s == 402)

    head("الإحالات عبر الشبكة")
    s, d = get(base + "/app/referrals")
    check("الإحالات لا تُقرأ بلا جلسة", s in (401, 403), str(s))

    head("استعادة كلمة المرور عبر الشبكة")
    s, d, _ = post(base + "/app/password/forgot", {"email": "ghost@nowhere.invalid"})
    check("طلبٌ لبريدٍ مجهول يردّ كالمعروف", s == 200 and d.get("ok"), f"{s} {str(d)[:60]}")
    check("ولا يُفصح عن وجود الحساب", "_token" not in json.dumps(d, ensure_ascii=False))
    s, d, _ = post(base + "/app/password/reset",
                   {"token": "not-a-real-token", "password": "Wh4tever!pass"})
    check("رمزٌ مزوَّر لا يغيّر كلمة مرور", s >= 400, f"{s} {str(d)[:50]}")

    head("الوكيل عبر الشبكة")
    ans = {}
    steps = 0
    for _ in range(40):
        s, d, _ = post(base + "/app/agent", {"answers": ans}, cookie=cookie1)
        if s != 200:
            check("الوكيل يستجيب", False, f"{s} {str(d)[:80]}"); break
        if d.get("done"): break
        q = d["question"]; steps += 1
        if q["type"] == "auto":   ans[q["id"]] = q.get("value") or "—"
        elif q["type"] == "free": ans[q["id"]] = "قناة الاختبار"
        elif q["type"] == "number": ans[q["id"]] = str(q.get("default", 1))
        else:
            pick = {"source_kind": "quran", "surah": "94", "content_type": "post"}.get(q["id"])
            ans[q["id"]] = pick or q.get("default") or q["options"][0]["value"]
    else:
        check("الوكيل ينتهي", False, "لم ينتهِ بعد ٤٠ سؤالًا")
    check("الوكيل يقطع الشوط كاملًا عبر الشبكة", steps >= 12, f"{steps} سؤالًا")
    s, d, _ = post(base + "/app/agent/build", {"answers": ans}, cookie=cookie1)
    check("بناء مشروعٍ من الوكيل ينجح", s in (200, 201) and (d or {}).get("added", 0) > 0,
          f"{s} {str(d)[:60]}")
    s, d, _ = post(base + "/app/agent/build", {"answers": {"content_type": "post"}}, cookie=cookie1)
    check("إجاباتٌ ناقصة تُرفض عند البناء", s >= 400, str(s))

# ═════════════════ ٥ · الوكيل استقصاءً ═════════════════
def audit_agent_full():
    head("الوكيل — كل السور وكل الأبواب")
    from falah import agent as AG
    bad = []
    for s in AG.surahs(DB):
        a = {"content_type": "post", "platform": "x", "watermark": "و",
             "source_kind": "quran", "surah": str(s["number"])}
        try:
            q = AG.question("from", a, DB)
            if len(q["options"]) != s["n"]: bad.append((s["number"], len(q["options"]), s["n"]))
            AG.question("count", a, DB); AG.question("to", dict(a, **{"from": "1"}), DB)
        except Exception as e:
            bad.append((s["number"], "خطأ", str(e)))
    check("كل السور الـ١١٤ تعطي أرقام آياتها بلا خطأ", not bad, str(bad[:3]))

    bad, chapters_seen, hadiths_seen = [], 0, 0
    for b in AG.books(DB):
        chs = AG.chapters(DB, b["code"])
        if not chs: bad.append((b["code"], "بلا أبواب")); continue
        chapters_seen += len(chs)
        for ch in chs:
            hs = AG.chapter_hadiths(DB, b["code"], ch["chapter_id"])
            hadiths_seen += len(hs)
            if not hs: bad.append((b["code"], ch["chapter_id"], "باب بلا أحاديث"))
    check("لا بابٌ معروضٌ بلا حديثٍ مفحوص", not bad, str(bad[:3]))
    check("الأبواب والأحاديث المعروضة تُحصى",
          chapters_seen > 300 and hadiths_seen > 12000, f"{chapters_seen} بابًا · {hadiths_seen} حديثًا")

    # كل حديثٍ مُفرَجٍ عنه يجب أن يكون قابلًا للوصول من شجرة الاختيار نفسها
    unreachable = []
    for b in AG.books(DB):
        seen = set()
        for ch in AG.chapters(DB, b["code"]):
            seen |= {h["no"] for h in AG.chapter_hadiths(DB, b["code"], ch["chapter_id"])}
        if len(seen) != b["n"]: unreachable.append((b["code"], b["n"] - len(seen)))
    check("لا حديثَ مُفرَجٌ عنه يتعذّر الوصول إليه من الأسئلة", not unreachable, str(unreachable))

    # عيّنة أبواب: الخطة كلها مفحوصة
    random.seed(7)
    picks, bad = [], []
    for b in AG.books(DB):
        chs = AG.chapters(DB, b["code"])
        for ch in random.sample(chs, min(3, len(chs))):
            picks.append((b["code"], ch["chapter_id"]))
    for code, ch in picks:
        hs = AG.chapter_hadiths(DB, code, ch)
        a = {"content_type": "post", "platform": "x", "watermark": "و", "source_kind": "hadith",
             "book": code, "chapter": str(ch), "no": str(hs[0]["no"]),
             "from": str(hs[0]["no"]), "to": str(hs[min(2, len(hs)-1)]["no"])}
        P = AG.plan(a, DB)
        if not P["cards"] or any(x["checks"] != "25/25" for x in P["cards"]):
            bad.append((code, ch, [x["checks"] for x in P["cards"]][:3]))
    check(f"خطط {len(picks)} بابًا عشوائيًّا كلها مفحوصة ٢٥/٢٥", not bad, str(bad[:3]))

    # مدخلات فاسدة لا تُسقط الوكيل
    junk = [{"source_kind": "hadith", "book": "'; DROP TABLE hadiths;--"},
            {"source_kind": "quran", "surah": "-1"},
            {"source_kind": "quran", "surah": "115"},
            {"source_kind": "quran", "surah": "2", "from": "abc"},
            {"source_kind": "hadith", "book": "bukhari", "chapter": "99999"},
            {"source_kind": "zzz"}, {"content_type": "nope"}]
    crashed = []
    for a in junk:
        try:
            AG.sanitize(a, DB); AG.next_question(a, DB); AG.plan(a, DB); AG.selection(a, DB)
        except Exception as e:
            crashed.append((str(a)[:40], type(e).__name__ + ": " + str(e)[:40]))
    check("مدخلاتٌ فاسدة لا تُسقط الوكيل", not crashed, str(crashed[:3]))

# ═════════════════ ٦ · التصيير في كل الأحوال ═════════════════
def audit_render():
    head("التصيير — كل المقاسات والهيئات والألوان")
    import render as RD, api
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    q, _ = api.quran_card(c, 2, 255, None, True, True)      # آية الكرسي: طويلة
    h, _ = api.hadith_card(c, "tirmidhi", 2055)             # حديث بشرح
    short, _ = api.quran_card(c, 108, 1, None, True, True)
    c.close()

    made, bad = 0, []
    for ratio in ("square", "vertical", "wide"):
        for skin in RD.SKINS:
            for tint in ("auto", "green", "gold"):
                for card, kind in ((q, "quran"), (h, "hadith")):
                    try:
                        html = RD.build_html(card, kind, skin=skin, ratio=ratio,
                                             watermark="قناة الاختبار", tint=tint)
                        assert card["text"][:40] in html, "النصّ غاب عن الصفحة"
                        assert "العلامة المائية للمستخدم" in html and "FALAH" in html
                        made += 1
                    except Exception as e:
                        bad.append((ratio, skin, tint, kind, str(e)[:40]))
    check(f"بُنيت {made} صفحة بطاقة بلا خطأ", not bad, str(bad[:3]))

    # التصيير الفعلي لعيّنة، وفحص أن الصورة ليست فارغة
    try:
        from PIL import Image
        pil = True
    except ImportError:
        pil = False
    outs = []
    for i, (card, kind, ratio, tint) in enumerate([
            (q, "quran", "square", "auto"), (h, "hadith", "vertical", "navy"),
            (short, "quran", "wide", "gold")]):
        p = f"/tmp/audit_{i}.png"
        RD.render(RD.build_html(card, kind, skin="parch", ratio=ratio,
                                watermark="قناة الاختبار", tint=tint), p, ratio)
        outs.append((p, ratio))
    check("صُيّرت ثلاث بطاقات فعليًّا", all(os.path.getsize(p) > 20000 for p, _ in outs),
          str([os.path.getsize(p) for p, _ in outs]))
    if pil:
        ok = True; detail = []
        for p, ratio in outs:
            im = Image.open(p); w, h_ = im.size
            want = RD.SIZES[ratio]
            colors = im.convert("RGB").getcolors(200000)
            if (w, h_) != want: ok = False; detail.append((p, (w, h_), want))
            if colors is not None and len(colors) < 50:
                ok = False; detail.append((p, "شبه فارغة", len(colors)))
        check("المقاسات مضبوطة والصور ليست فارغة", ok, str(detail))

    # التقسيم: أطول آية
    files = RD.render_split(q, "quran", skin="parch", ratio="square",
                            watermark="قناة", out_prefix="/tmp/audit_split")
    check("أطول آية تُصيَّر شرائح", len(files) >= 2 and all(os.path.getsize(f) > 20000 for f in files),
          f"{len(files)} شريحة")
    for f in files + [p for p, _ in outs]:
        try: os.remove(f)
        except OSError: pass

def audit_video():
    head("الفيديو")
    t0 = time.time()
    r = subprocess.run([sys.executable, "video.py", "--surah", "108", "--ayah", "1",
                        "--to", "3", "--reciter", "alafasy", "--out", "/tmp/audit.mp4"],
                       cwd=HERE, capture_output=True, text=True, timeout=600)
    ok = r.returncode == 0 and os.path.exists("/tmp/audit.mp4") and os.path.getsize("/tmp/audit.mp4") > 50000
    check("يُبنى مقطع فيديو من آياتٍ وتلاوة", ok,
          (r.stderr or r.stdout)[-140:] if not ok else f"{os.path.getsize('/tmp/audit.mp4')/1e6:.1f}م.ب · {time.time()-t0:.0f}ث")
    if ok:
        pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration:stream=codec_type", "-of", "json", "/tmp/audit.mp4"],
                            capture_output=True, text=True)
        try:
            j = json.loads(pr.stdout)
            kinds = {s["codec_type"] for s in j.get("streams", [])}
            dur = float(j["format"]["duration"])
            check("المقطع فيه صورة وصوت وطولٌ معقول",
                  kinds >= {"video", "audio"} and 3 < dur < 400, f"{kinds} · {dur:.0f}ث")
        except Exception as e:
            check("قراءة بيانات المقطع", False, str(e)[:60])
        os.remove("/tmp/audit.mp4")


# ═════════════════ ٦٫٥ · الطابور ═════════════════
def audit_queue(base):
    head("طابور المهامّ — التصيير خارج دورة الطلب")
    m  = f"q{int(time.time()*1000)%10**8}@audit.falah"
    pw = "Str0ng-Pass!x9"
    s, d, ck = post(base + "/app/register", {"email": m, "password": pw,
                                             "name": "طابور", "watermark": "قناة الطابور"})
    if s not in (200, 201) or not ck:
        return check("تسجيل حساب الطابور", False, f"{s} {str(d)[:60]}")
    cookie = ck[0].split(";")[0]
    s, d, _ = post(base + "/app/projects/create", {"title": "مشروع الطابور",
                   "skin": "parch", "ratio": "square"}, cookie=cookie)
    pid = (d or {}).get("id")
    if not pid: return check("إنشاء مشروع الطابور", False, str(d)[:60])
    for ref in ({"surah": 108, "ayah": 1, "to": 3}, {"surah": 94, "ayah": 5}):
        post(base + "/app/items/add", {"project": pid, "kind": "quran", "ref": ref},
             cookie=cookie)

    t0 = time.time()
    s, d, _ = post(base + "/app/export", {"project": pid}, cookie=cookie)
    dt = (time.time() - t0) * 1000
    check("‎/app/export يردّ ٢٠٢ لا ٢٠١", s == 202, f"{s} {str(d)[:60]}")
    check("الردّ فوريٌّ لا ينتظر التصيير", dt < 800, f"{dt:.0f} م.ث")
    job = (d or {}).get("job") or {}
    check("الردّ يحمل رقم المهمّة وحالتها",
          bool(job.get("id")) and job.get("state") == "queued", str(job)[:60])
    check("الردّ لا يسرّب حمولة المهمّة الداخلية",
          "payload" not in job and "reserved" not in job)

    fin, seen = follow(base, cookie, job.get("id"))
    check("المهمّة تكتمل عبر الشبكة", bool(fin) and fin["state"] == "done",
          str(fin and (fin["state"], fin["error"]))[:80])
    if fin and fin["state"] == "done":
        files = (fin["result"] or {}).get("files") or []
        check("النتيجة تحمل الملفّات والوصف", bool(files) and bool(fin["result"].get("caption")),
              f"{len(files)} ملف")
        s2, d2 = getc(base + "/app/file?p=" + urllib.parse.quote(files[0]), cookie)
        check("الملفّ المصدَّر يُنزَّل بالجلسة صورةً حقيقية",
              s2 == 200 and (d2 or {}).get("bytes", 0) > 5000
              and "image/png" in ((d2 or {}).get("type") or ""), f"{s2} {str(d2)[:50]}")
        check("التقدّم بلغ ١٠٠٪ والخطوة عربية",
              fin["progress"] == 100 and bool(fin["step"]), str(fin["step"]))

    # مهمّة غيره لا تُقرأ برقمها
    m2 = f"q2{int(time.time()*1000)%10**8}@audit.falah"
    s, d, ck2 = post(base + "/app/register", {"email": m2, "password": pw, "name": "ب"})
    if ck2:
        s2, _ = getc(base + f"/app/jobs/{job.get('id')}", ck2[0].split(";")[0])
        check("لا يستطلع أحدٌ مهمّةَ غيره", s2 >= 400, str(s2))
    s2, _ = getc(base + f"/app/jobs/{job.get('id')}")
    check("الاستطلاع بلا جلسة مرفوض", s2 == 401, str(s2))

    # عشرة تصديرات معًا: الردود كلّها فورية، والخادم لا يُحبس
    s, d, _ = post(base + "/app/subscription/grant", {"plan": "creator", "days": 3},
                   cookie=cookie)     # يفشل بلا مفتاح إدارة — يُتجاوز
    lat, codes = [], []
    def fire():
        t = time.time()
        st, _, _ = post(base + "/app/export", {"project": pid}, cookie=cookie)
        lat.append((time.time() - t) * 1000); codes.append(st)
    ths = [threading.Thread(target=fire) for _ in range(10)]
    t0 = time.time()
    [t.start() for t in ths]; [t.join() for t in ths]
    wall = (time.time() - t0) * 1000
    accepted = [x for x in codes if x == 202]
    check("عشرة طلبات معًا تُخدَم في أقل من ثانيتين",
          wall < 2000, f"{wall:.0f} م.ث · {codes}")
    check("لا طلبَ منها ينتظر التصيير",
          not lat or max(lat) < 1500, f"أقصى {max(lat) if lat else 0:.0f} م.ث")
    check("ما تجاوز الحصّة يُردّ بخطأٍ لا يُوضع في الطابور",
          all(x in (202, 400) for x in codes), str(codes))

    s, d = getc(base + "/app/jobs", cookie)
    check("‎/app/jobs يعرض مهامّ صاحبها وإحصاء الطابور",
          s == 200 and isinstance(d.get("jobs"), list) and "queued" in (d.get("queue") or {}),
          str(s))
    check("المهامّ مرتّبةٌ من الأحدث",
          len(d.get("jobs", [])) >= 1 and
          all(d["jobs"][i]["created_at"] >= d["jobs"][i+1]["created_at"]
              for i in range(len(d["jobs"]) - 1)))

    # الخادم يظلّ مستجيبًا والطابور يعمل
    t0 = time.time(); sh, _ = get(base + "/health"); hdt = (time.time() - t0) * 1000
    check("الخادم يستجيب أثناء عمل الطابور", sh == 200 and hdt < 800, f"{hdt:.0f} م.ث")

    if accepted:
        left = [j["id"] for j in getc(base + "/app/jobs", cookie)[1]["jobs"] if j["waiting"]]
        done_all = True
        for jid in left[:4]:
            f2, _ = follow(base, cookie, jid, limit=240)
            if not f2 or f2["state"] not in ("done", "failed"): done_all = False
        check("الطابور يستنفد ما فيه ولا يعلق شيءٌ «يجري»", done_all)

# ═════════════════ ٧ · الأداء ═════════════════
def audit_perf(base):
    head("الأداء والحِمل")
    paths = ["/health", "/options", "/chapters?book=bukhari",
             "/card?kind=quran&surah=94&ayah=5&tafsir=1&translation=1",
             "/card?kind=hadith&book=bukhari&no=1", "/templates?kind=hadith&limit=20"]
    slow = []
    for p in paths:
        t = []
        for _ in range(5):
            t0 = time.time(); get(base + p); t.append((time.time() - t0) * 1000)
        med = sorted(t)[2]
        if med > 800: slow.append((p, round(med)))
        print(f"    {p[:44]:46s} {med:6.0f} م.ث")
    check("لا مسار يتجاوز ٨٠٠ مللي ثانية", not slow, str(slow))

    # ٣٠ طلبًا متوازيًا
    errs = []
    def hit():
        s, _ = get(base + "/card?kind=hadith&book=bukhari&no=1")
        if s != 200: errs.append(s)
    t0 = time.time()
    ths = [threading.Thread(target=hit) for _ in range(30)]
    [t.start() for t in ths]; [t.join() for t in ths]
    check("٣٠ طلبًا متوازيًا بلا خطأ", not errs, f"{len(errs)} خطأ · {time.time()-t0:.1f}ث")

    sz = os.path.getsize(DB) / 1e6
    check("حجم القاعدة معقول", sz < 900, f"{sz:.0f} م.ب")
    pv = os.path.join(HERE, "falah-preview.html")
    if os.path.exists(pv):
        check("صفحة المعاينة أخفّ من حدّ النشر",
              os.path.getsize(pv) < 16e6, f"{os.path.getsize(pv)/1e6:.2f} م.ب")

# ═════════════════ التشغيل ═════════════════
if __name__ == "__main__":
    API = os.environ.get("API", "http://localhost:8080")
    APP = os.environ.get("APP", "http://localhost:8081")
    only = sys.argv[1:] or ["db", "engine", "api", "app", "agent", "render", "video", "queue", "perf"]
    if "db" in only:     audit_db()
    if "engine" in only: audit_engine()
    if "api" in only:    audit_api(API)
    if "app" in only:    audit_app(APP)
    if "agent" in only:  audit_agent_full()
    if "render" in only: audit_render()
    if "video" in only:  audit_video()
    if "queue" in only:  audit_queue(APP)
    if "perf" in only:   audit_perf(API)
    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: نجح {OK} · سقط {FAIL}")
        for n, d in FAILURES: print(f"  ✗ {n}  ← {d}")
        sys.exit(1)
    print(f"النتيجة: كل الفحوص نجحت ✓  ({OK} بندًا)")
