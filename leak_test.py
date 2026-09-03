#!/usr/bin/env python3
"""فحصُ التسريب — ما الذي يخرج للمستخدم، وما الذي يبقى في السجلّ.

    python3 leak_test.py

قاعدتان متقابلتان، وكلتاهما تُختبر هنا:

  ١. **ما يخرج**: لا أثرَ استثناء، ولا مسارَ ملفّ، ولا سرَّ بيئة، ولا اسمَ
     جدولٍ أو عمود، ولا نصَّ استعلام. رسالةٌ عربيةٌ يفهمها صاحبها، لا خريطةٌ
     لمن يبحث عن ثغرة.
  ٢. **ما يبقى**: التفصيل الكامل في `stderr` عندنا. فالكتمان عن المستخدم
     لا يصحّ أن يكون كتمانًا عنّا — وإلا صار العطبُ صامتًا لا آمنًا.

يُشغَّل على خادمٍ اختباريّ بقاعدةٍ مؤقّتة، ويقرأ سجلّه من ملفٍّ يملكه.
"""
import json, os, re, shutil, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OK = FAIL = 0; FAILURES = []
PW = "Str0ng-Pass!x9"

def check(n, c, d=""):
    global OK, FAIL
    if c: OK += 1; print(f"  ✓ {n}" + (f"  ({d})" if d else ""))
    else: FAIL += 1; FAILURES.append((n, d)); print(f"  ✗ {n}" + (f"  ← {d}" if d else ""))
def head(t): print(f"\n▸ {t}")

# ما لا يجوز أن يظهر في ردٍّ للمستخدم، أبدًا، مهما كان رمز الحالة.
FORBIDDEN = [
    (r"Traceback \(most recent call last\)", "أثرُ استثناء"),
    (r'File "[^"]+\.py", line \d+',          "موضعٌ في الشيفرة"),
    (r"/home/|/usr/|/opt/|/data/|/tmp/",     "مسارٌ في نظام الملفّات"),
    (r"\b(SELECT|INSERT|UPDATE|DELETE)\s+.*\s+FROM\b", "نصُّ استعلام"),
    (r"\bsqlite3\.\w+Error\b",               "خطأُ قاعدةٍ بنوعه"),
    (r"\b(app\.db|falah\.db)\b",             "اسمُ ملفّ قاعدة"),
    (r"\bFALAH_[A-Z_]+\b",                   "اسمُ متغيّر بيئة"),
    (r"\b(pw_hash|pw_salt|token_hash|idem_key)\b", "اسمُ عمودٍ حسّاس"),
    (r"\b(ValueError|TypeError|KeyError|AttributeError|IndexError|"
     r"OSError|RuntimeError|IntegrityError|OperationalError)\b", "نوعُ استثناء"),
    (r"0x[0-9a-f]{8,}",                      "عنوانُ ذاكرة"),
    (r"[A-Za-z0-9+/]{60,}={0,2}",            "كتلةٌ مشفَّرة قد تكون سرًّا"),
]

def scan(text):
    return [why for pat, why in FORBIDDEN if re.search(pat, text, re.I)]

def req(base, path, body=None, cookie=None, hdr=None, method=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if data is not None: h["X-FALAH"] = "1"
    if cookie: h["Cookie"] = cookie
    h.update(hdr or {})
    r = urllib.request.Request(base + path, data=data, headers=h,
                               method=method or ("POST" if data is not None else "GET"))
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            return x.status, x.read().decode("utf-8", "replace"), x.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), []
    except Exception as e:
        return 0, f"{type(e).__name__}", []

def free_port():
    s = socket.socket(); s.bind(("", 0)); p = s.getsockname()[1]; s.close(); return p

def main():
    d = tempfile.mkdtemp(prefix="falah-leak-")
    port = free_port(); base = f"http://127.0.0.1:{port}"
    log = os.path.join(d, "server.log")
    env = dict(os.environ, FALAH_APP_DB=os.path.join(d, "app.db"), PORT=str(port),
               FALAH_INLINE_WORKER="1",
               FALAH_ADMIN_KEY="admin-secret-value-must-never-leak-12345")
    lf = open(log, "w")
    p = subprocess.Popen([sys.executable, "app.py"], cwd=HERE, env=env,
                         stdout=lf, stderr=lf, start_new_session=True)
    try:
        for _ in range(60):
            if req(base, "/healthz", timeout=2)[0] == 200: break
            time.sleep(0.5)

        s, body, ck = req(base, "/app/register",
                          {"email": f"lk{int(time.time())}@t.com", "password": PW,
                           "name": "تسريب", "watermark": "ق"})
        cookie = ck[0].split(";")[0] if ck else None
        s, body, _ = req(base, "/app/projects/create", {"title": "ت"}, cookie)
        pid = json.loads(body).get("id")

        # ═══ ١ · كل رمز حالةٍ يُستدرَج عمدًا ═══
        head("كل رمز حالة — ماذا يخرج للمستخدم؟")
        cases = [
            # (وصف، مسار، جسم، كعكة، ترويسات، الرمز المتوقَّع)
            ("٤٠٠ رقمٌ نصّيّ",      "/app/export", {"project": "أبجد"}, cookie, None, 400),
            ("٤٠٠ حقلٌ ناقص",      "/app/export", {}, cookie, None, 400),
            ("٤٠٠ مشروعٌ لا وجود له", "/app/export", {"project": 10**12}, cookie, None, 400),
            ("٤٠٠ جسمٌ ليس JSON",   "/app/projects/create", None, cookie, None, None),
            ("٤٠٠ نوعٌ خاطئ",       "/app/items/add",
             {"project": pid, "kind": {"x": 1}, "ref": []}, cookie, None, None),
            ("٤٠١ بلا جلسة",        "/app/projects", None, None, None, 401),
            ("٤٠١ كعكةٌ مزوَّرة",    "/app/projects", None, "falah_sid=deadbeef", None, 401),
            ("٤٠٣ بلا ترويسة الحماية", "/app/export", {"project": pid}, cookie,
             {"X-FALAH": ""}, 403),
            ("٤٠٣ منحةٌ بلا مفتاح", "/app/subscription/grant", {"plan": "studio"},
             cookie, None, 403),
            ("٤٠٣ مفتاحُ إدارةٍ خاطئ", "/app/subscription/grant", {"plan": "studio"},
             cookie, {"X-FALAH-ADMIN": "wrong"}, 403),
            ("٤٠٤ مسارٌ مجهول",     "/app/nope", None, cookie, None, 404),
            ("٤٠٤ ملفٌّ خارج المجلّد", "/app/file?p=../../etc/passwd", None, cookie, None, 404),
            ("٤٠٤ حديثٌ لا وجود له", "/hadith?book=bukhari&no=99999999", None, None, None, None),
            ("٤٠٢ إيصالٌ لم يثبت",  "/app/subscription/store-event",
             {"provider": "apple", "event": {"signedTransactionInfo": "x.y.z"}},
             cookie, None, 402),
            ("٤٠٠ استعلامٌ فاسد",   "/chapters?book=%27+OR+1%3D1--", None, None, None, None),
            ("٤٠٠ حقنُ SQL في رقم", "/hadith?book=bukhari&no=1%20OR%201%3D1", None, None, None, None),
            ("٤٠٠ رمزٌ منتهٍ",      "/app/password/reset",
             {"token": "x" * 60, "password": PW}, None, None, None),
            ("٤٠٠ بريدٌ فاسد",      "/app/register",
             {"email": "@@@", "password": PW}, None, None, None),
        ]
        seen_codes = set()
        for name, path, body_, ck_, hdr_, want in cases:
            st, txt, _ = req(base, path, body_, ck_, hdr_)
            seen_codes.add(st)
            leaks = scan(txt)
            check(f"{name} → {st}: لا تسريب", not leaks,
                  f"{leaks} · {txt[:70]}")
            if want is not None and st != want:
                check(f"{name}: الرمز كما يجب", False, f"{st} بدل {want}")
            # ولا بدّ من رسالةٍ عربيةٍ مفهومة لا فراغ
            if 400 <= st < 500:
                try:    msg = json.loads(txt).get("error", "")
                except Exception: msg = txt
                check(f"{name}: رسالةٌ عربيةٌ مفهومة",
                      bool(re.search(r"[؀-ۿ]", str(msg))), str(msg)[:60])

        print(f"\n    رموزٌ استُدرجت فعلًا: {sorted(seen_codes)}")

        # ═══ ٢ · الخمسمئة والثلاثة والخمسمئة ═══
        head("٥٠٠ و٥٠٣ — أخطر ما يُسرَّب")
        dbp = os.path.join(HERE, "falah.db")
        moved = dbp + ".leaktest"
        os.rename(dbp, moved)
        for sfx in ("-wal", "-shm"):
            if os.path.exists(dbp + sfx): os.rename(dbp + sfx, moved + sfx)
        try:
            st, txt, _ = req(base, "/readyz")
            check(f"٥٠٣ الجاهزية → {st}: لا تسريب", not scan(txt), f"{scan(txt)} · {txt[:80]}")
            check("٥٠٣ يسمّي ما سقط بلا تفصيلٍ داخليّ",
                  st == 503 and '"content_db": false' in txt.lower()
                  and "unreachable" in txt, txt[:90])
            st2, txt2, _ = req(base, "/card?kind=quran&surah=1&ayah=1")
            check(f"طلبٌ على قاعدةٍ مفقودة → {st2}: لا تسريب",
                  not scan(txt2), f"{scan(txt2)} · {txt2[:80]}")
        finally:
            os.rename(moved, dbp)
            for sfx in ("-wal", "-shm"):
                if os.path.exists(moved + sfx): os.rename(moved + sfx, dbp + sfx)

        # ═══ ٣ · السرُّ المضبوط في البيئة لا يظهر في أي ردّ ═══
        head("سرُّ البيئة لا يخرج في أي ردّ")
        secret = env["FALAH_ADMIN_KEY"]
        bodies = []
        for path in ("/healthz", "/readyz", "/app/config", "/app/plans", "/app/me",
                     "/health", "/sources", "/app/limits", "/app/jobs"):
            st, txt, _ = req(base, path, cookie=cookie)
            bodies.append((path, txt))
        check("لا ردَّ يحمل مفتاح الإدارة",
              not any(secret in t for _, t in bodies))
        check("ولا ردَّ يحمل اسم متغيّر بيئة",
              not any(re.search(r"FALAH_[A-Z_]+", t) for _, t in bodies),
              str([p for p, t in bodies if re.search(r"FALAH_[A-Z_]+", t)]))
        check("ولا ردَّ يحمل مسارًا في نظام الملفّات",
              not any(re.search(r"/home/|/data/|/tmp/", t) for _, t in bodies),
              str([p for p, t in bodies if re.search(r"/home/|/data/|/tmp/", t)]))

        # ═══ ٤ · الترويسات ═══
        head("ترويسات الردّ")
        r = urllib.request.Request(base + "/healthz")
        with urllib.request.urlopen(r, timeout=10) as x:
            hs = dict(x.headers)
        check("لا ترويسةَ تفشي المكدّس التقنيّ",
              "X-Powered-By" not in hs and "python" not in str(hs.get("Server", "")).lower(),
              str(hs.get("Server")))
        check("nosniff مضبوطة", hs.get("X-Content-Type-Options") == "nosniff")
        check("والتضمين ممنوع", hs.get("X-Frame-Options") == "DENY")

        # ═══ ٥ · السجلّ: التفصيل موجودٌ عندنا ═══
        head("السجلّ — الكتمان عن المستخدم لا عنّا")
        time.sleep(0.6)
        lf.flush()
        text = open(log, encoding="utf-8", errors="replace").read()
        lines = [l for l in text.splitlines() if "ERROR" in l]
        check("العطب سُجّل فعلًا — لا دعوى بلا سجلّ", bool(lines), f"{len(lines)} سطرًا")
        if lines:
            print("    عيّنة:", lines[0][:110])
            check("لكل سطرٍ ختمٌ زمنيّ",
                  all(re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", l) for l in lines))
            check("ومستوًى معلَن", all("ERROR" in l for l in lines))
            check("ونوعُ الاستثناء أو وصفُ الطلب",
                  any(re.search(r"(ValueError|TypeError|KeyError|bad request|internal)", l)
                      for l in lines))
            check("والمسارُ الذي وقع فيه", any("/app/" in l for l in lines))
        check("ولا يحمل السجلّ كلمة مرورٍ صريحة", PW not in text)
        check("ولا مفتاح الإدارة", secret not in text)
        check("ولا رمزَ جلسةٍ خامًا",
              not (cookie and cookie.split("=", 1)[1] in text))

        # ═══ ٦ · الفروق بين ما يخرج وما يبقى ═══
        head("المقابلة: ما خرج مقابل ما بقي")
        st, txt, _ = req(base, "/app/export", {"project": "ليس رقمًا"}, cookie)
        time.sleep(0.4); lf.flush()
        tail = open(log, encoding="utf-8", errors="replace").read()
        check("الردّ للمستخدم رسالةٌ عربيةٌ قصيرة",
              st == 400 and "قيمة" in txt and len(txt) < 200, f"{st} {txt[:60]}")
        check("والسجلّ عندنا يحمل نوع الاستثناء ومساره",
              "ValueError" in tail and "/app/export" in tail)
    finally:
        p.kill(); p.wait(timeout=15); lf.close()
        shutil.rmtree(d, ignore_errors=True)

    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: نجح {OK} · سقط {FAIL}")
        for n, dd in FAILURES: print(f"  ✗ {n}  ← {dd}")
        return 1
    print(f"النتيجة: لا تسريب ✓  ({OK} بندًا)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
