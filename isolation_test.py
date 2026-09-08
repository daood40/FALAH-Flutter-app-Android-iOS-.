#!/usr/bin/env python3
"""حدود المستخدم — «أ» لا يبلغ شيئًا من «ب»، بأي طريق.

    python3 isolation_test.py

كل بندٍ هنا صيغته واحدة: **مورِدٌ يملكه ب، وطلبٌ يوقّعه أ.** والنتيجة
المقبولة واحدة: يفشل. لا يُقرأ، ولا يُعدَّل، ولا يُحذف، ولا يُنزَّل، ولا
يُستدلّ على وجوده من فرق الرسائل.

ويُختبر معها ما يُبنى على الحدود نفسها: مسارات الملفّات المصدَّرة (خروجٌ
بالنقاط، وترميزٌ مفرد ومزدوج، ومسارٌ مطلق)، وحدودُ الموارد، وحدُّ المحاولات.
يُشغَّل على خادمٍ اختباريّ بقاعدةٍ مؤقّتة.
"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OK = FAIL = 0; FAILURES = []
PW = "Str0ng-Pass!x9"

def check(n, c, d=""):
    global OK, FAIL
    if c: OK += 1; print(f"  ✓ {n}" + (f"  ({d})" if d else ""))
    else: FAIL += 1; FAILURES.append((n, d)); print(f"  ✗ {n}" + (f"  ← {d}" if d else ""))
def head(t): print(f"\n▸ {t}")

def req(base, path, body=None, cookie=None, hdr=None, timeout=25, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if data is not None: h["X-FALAH"] = "1"
    if cookie: h["Cookie"] = cookie
    h.update(hdr or {})
    r = urllib.request.Request(base + path, data=data, headers=h,
                               method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            b = x.read()
            if raw: return x.status, b, []
            try:    return x.status, json.loads(b), x.headers.get_all("Set-Cookie") or []
            except Exception: return x.status, {"bytes": len(b)}, []
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read()), []
        except Exception: return e.code, None, []
    except Exception as e:
        return 0, {"error": type(e).__name__}, []


def oversized(base, nbytes, chunk=65536, read_between=True):
    """يرسل جسمًا فوق الحدّ **بمقبسٍ خام** ويفصل طبقتين لا يخلطهما:

      • **دلالةُ HTTP**: هل أرسل الخادمُ ٤٠٣؟ ٤١٣؟ بأيّ جسم؟
      • **سلوكُ النقل**: هل أُتمّ إرسالُ الجسم؟ هل وقع خطأُ كتابة؟
        هل أُغلق الاتصال؟

    ولماذا مقبسٌ خام لا `urllib`؟ لأن `urllib` يخلط الطبقتين: يعامل خطأَ
    الكتابة **خطأً نهائيًّا** فلا يقرأ الردَّ الذي وصل فعلًا إلى مخزنه.
    فيقول «تعذّر الاتصال» عن خادمٍ ردَّ ٤١٣ كما ينبغي. وهذا فرقٌ بين
    «الخادمُ مخطئ» و«هذا العميلُ لا يقرأ» — ولا يجوز الخلط بينهما.
    """
    body = json.dumps({"project": 1, "junk": "x" * nbytes}).encode()
    host, port = urllib.parse.urlparse(base).hostname, urllib.parse.urlparse(base).port
    s_ = socket.create_connection((host, port), timeout=15)
    s_.sendall(b"POST /app/export HTTP/1.1\r\nHost: " + host.encode()
               + b"\r\nContent-Type: application/json\r\nX-FALAH: 1\r\n"
               + f"Content-Length: {len(body)}\r\n".encode() + b"\r\n")
    sent, resp, werr = 0, b"", None
    s_.settimeout(0.4)
    while sent < len(body):
        try:
            sent += s_.send(body[sent:sent + chunk])
        except OSError as e:
            werr = type(e).__name__; break
        if not read_between: continue
        try:
            d = s_.recv(65536)
            if not d: break
            resp += d
            if b"\r\n\r\n" in resp: break
        except socket.timeout: pass
        except OSError as e: werr = werr or type(e).__name__; break
    # تُقرأ الترويساتُ ثم **الجسمُ بطوله المعلَن**. الاكتفاءُ بـ`\r\n\r\n`
    # يجعل البندَ متقطّعًا: الترويساتُ قد تصل في حزمةٍ والجسمُ في التالية.
    s_.settimeout(4)
    closed = False
    try:
        while b"\r\n\r\n" not in resp:
            d = s_.recv(65536)
            if not d: closed = True; break
            resp += d
        h = resp.split(b"\r\n\r\n", 1)[0].decode("latin1")
        want = next((int(x.split(":", 1)[1]) for x in h.splitlines()
                     if x.lower().startswith("content-length")), 0)
        while len(resp.split(b"\r\n\r\n", 1)[1]) < want:
            d = s_.recv(65536)
            if not d: closed = True; break
            resp += d
    except OSError as e:
        werr = werr or type(e).__name__
    except (IndexError, StopIteration, ValueError):
        pass
    head, _, rest = resp.partition(b"\r\n\r\n")
    try:    payload = json.loads(rest.decode("utf-8"))
    except Exception: payload = None
    s_.close()
    return {"sent": sent, "total": len(body), "write_error": werr, "closed": closed,
            "status": int(head.split()[1]) if head.split()[1:] else 0,
            "head": head.decode("latin1"), "body": payload}

def free_port():
    s = socket.socket(); s.bind(("", 0)); p = s.getsockname()[1]; s.close(); return p

def main():
    d = tempfile.mkdtemp(prefix="falah-iso-")
    port = free_port(); base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, FALAH_APP_DB=os.path.join(d, "app.db"), PORT=str(port),
               FALAH_INLINE_WORKER="1", FALAH_BACKOFF="1",
               # حدٌّ منخفضٌ عمدًا: الخطّة المجانية تنفد حصّتها قبل الحدّ
               # الافتراضيّ (٣٠/ساعة)، فلا يُبلغ ما نريد اختباره.
               FALAH_RATE_EXPORT="4", FALAH_RATE_REGISTER="10000")
    p = subprocess.Popen([sys.executable, "app.py"], cwd=HERE, env=env,
                         stdout=open(os.path.join(d, "app.log"), "w"),
                         stderr=subprocess.STDOUT, start_new_session=True)
    made = []
    try:
        for _ in range(60):
            if req(base, "/healthz", timeout=2)[0] == 200: break
            time.sleep(0.5)

        def account(tag):
            m = f"{tag}{int(time.time()*1000)%10**9}@iso.test"
            s, dd, ck = req(base, "/app/register",
                            {"email": m, "password": PW, "name": tag, "watermark": tag})
            ck = ck[0].split(";")[0] if ck else None
            uid = req(base, "/app/me", cookie=ck)[1]["user"]["id"]
            return ck, uid, m

        A, uidA, mailA = account("A")
        B, uidB, mailB = account("B")
        check("حسابان مستقلّان", A and B and uidA != uidB, f"{uidA} · {uidB}")

        # ═══ مورِدُ ب ═══
        s, dd, _ = req(base, "/app/projects/create",
                       {"title": "مشروع ب", "skin": "parch", "ratio": "square"}, B)
        pidB = dd["id"]
        req(base, "/app/items/add",
            {"project": pidB, "kind": "quran", "ref": {"surah": 108, "ayah": 1, "to": 3}}, B)
        itemB = req(base, f"/app/projects/{pidB}", cookie=B)[1]["items"][0]["id"]
        s, dd, _ = req(base, "/app/export", {"project": pidB}, B)
        jobB = dd["job"]["id"]
        t0 = time.time(); resB = None
        while time.time() - t0 < 200:
            j = req(base, f"/app/jobs/{jobB}", cookie=B)[1]["job"]
            if not j["waiting"]: resB = j; break
            time.sleep(0.5)
        check("مشروعُ ب صُدِّر فعلًا فصار له ملفّات",
              bool(resB) and resB["state"] == "done", str(resB and resB["state"]))
        fileB = (resB["result"] or {}).get("files", [None])[0] if resB else None
        made.append(os.path.join(HERE, "exports", str(uidB)))

        # ═══ أ يحاول كل طريق ═══
        head("أ ← موردُ ب: كل طريقٍ يجب أن يُغلق")
        cases = [
            ("قراءةُ مشروع ب",        "GET",  f"/app/projects/{pidB}", None),
            ("تعديلُ مشروع ب",        "POST", "/app/projects/update",
             {"id": pidB, "title": "استوليتُ عليه"}),
            ("حذفُ مشروع ب",          "POST", "/app/projects/delete", {"id": pidB}),
            ("إضافةُ عنصرٍ لمشروع ب", "POST", "/app/items/add",
             {"project": pidB, "kind": "quran", "ref": {"surah": 112, "ayah": 1}}),
            ("إزالةُ عنصرٍ من ب",     "POST", "/app/items/remove",
             {"project": pidB, "id": itemB}),
            ("إعادةُ ترتيب عناصر ب",  "POST", "/app/items/reorder",
             {"project": pidB, "order": [itemB]}),
            ("اعتمادُ انحرافٍ في ب",  "POST", "/app/items/accept-drift",
             {"project": pidB, "id": itemB}),
            ("تصديرُ مشروع ب",        "POST", "/app/export", {"project": pidB}),
            ("مقطعٌ من عنصر ب",       "POST", "/app/video",
             {"project": pidB, "item": itemB, "reciter": "alafasy"}),
            ("استطلاعُ مهمّة ب",      "GET",  f"/app/jobs/{jobB}", None),
            ("إلغاءُ مهمّة ب",        "POST", "/app/jobs/cancel", {"id": jobB}),
        ]
        for name, method, path, body in cases:
            st, dd, _ = req(base, path, body, A)
            check(f"{name} — يفشل", st >= 400, f"{st} {str(dd)[:60]}")

        # تنزيل ملفّ ب بمساره الحقيقيّ
        if fileB:
            st, dd, _ = req(base, "/app/file?p=" + urllib.parse.quote(fileB), cookie=A)
            check("تنزيلُ ملفّ ب بمساره الصحيح — يفشل", st >= 400, str(st))
            st2, _, _ = req(base, "/app/file?p=" + urllib.parse.quote(fileB), cookie=B)
            check("وصاحبُه ينزّله", st2 == 200, str(st2))

        # ═══ التخمين ═══
        head("التخمين — الأرقام لا تكشف")
        for jid in range(1, jobB + 4):
            st, dd, _ = req(base, f"/app/jobs/{jid}", cookie=A)
            if st == 200 and dd.get("job", {}).get("id") == jobB:
                check("رقمُ مهمّةٍ مخمَّن يكشف عمل ب", False, str(jid)); break
        else:
            check("لا رقمَ مهمّةٍ مخمَّن يكشف عمل ب", True, f"جُرِّب {jobB+3} رقمًا")

        seen = set()
        for pid in range(1, pidB + 4):
            st, dd, _ = req(base, f"/app/projects/{pid}", cookie=A)
            seen.add(st)
            if st == 200 and dd.get("project", {}).get("user_id") == uidB:
                check("رقمُ مشروعٍ مخمَّن يكشف مشروع ب", False, str(pid)); break
        else:
            check("لا رقمَ مشروعٍ مخمَّن يكشف مشروع ب", True, f"الردود {sorted(seen)}")

        # الرسالةُ لا تفرّق بين «ليس لك» و«لا وجود له» — وإلا عُدَّت الأرقام
        st1, d1, _ = req(base, f"/app/projects/{pidB}", cookie=A)
        st2, d2, _ = req(base, "/app/projects/999999", cookie=A)
        check("رسالةُ «ليس لك» = رسالةُ «لا وجود له»",
              (st1, str(d1)) == (st2, str(d2)), f"{d1} مقابل {d2}")

        # ═══ الحصّة والقوائم ═══
        head("الحصّة والقوائم لا تختلط")
        entA = req(base, "/app/entitlements", cookie=A)[1]
        entB = req(base, "/app/entitlements", cookie=B)[1]
        check("حصّةُ ب استُهلكت وحصّةُ أ لم تُمسّ",
              entB["used"]["cards"] > 0 and entA["used"]["cards"] == 0,
              f"أ={entA['used']['cards']} ب={entB['used']['cards']}")
        check("قائمةُ مشاريع أ فارغةٌ من مشاريع ب",
              all(x["id"] != pidB for x in req(base, "/app/projects", cookie=A)[1]["projects"]))
        check("وقائمةُ مهامّه كذلك",
              all(x["id"] != jobB for x in req(base, "/app/jobs", cookie=A)[1]["jobs"]))
        check("وقائمةُ صادراته كذلك",
              all(x.get("user_id") != uidB
                  for x in req(base, "/app/exports", cookie=A)[1]["exports"]))

        # ═══ المسارات ═══
        head("مسارُ الملفّ — خروجٌ وترميزٌ ومطلق")
        traversals = [
            "../../etc/passwd", "..%2f..%2fetc%2fpasswd",
            "..%252f..%252fetc%252fpasswd", "....//....//etc/passwd",
            "/etc/passwd", "app.py", "../app.py", "falah.db", "../falah.db",
            f"exports/{uidB}/{pidB}/00_quran.png",
            f"exports/{uidA}/../{uidB}/{pidB}/00_quran.png",
            "exports/../app.py", ".env", "../.env",
            "exports/%2e%2e/%2e%2e/app.py",
            "\\..\\..\\app.py", "exports/./../../app.py",
        ]
        for t in traversals:
            st, dd, _ = req(base, "/app/file?p=" + urllib.parse.quote(t, safe=""), cookie=A)
            check(f"لا يُقدَّم: {t[:42]}", st >= 400, f"{st} {str(dd)[:40]}")
        st, dd, _ = req(base, "/app/file", cookie=A)
        check("ولا بلا مسارٍ أصلًا", st >= 400, str(st))

        # وأسماءُ الملفّات المُنتَجة نفسها آمنة
        if fileB:
            check("اسمُ الملفّ المُنتَج بلا محارف خطِرة",
                  not any(ch in fileB for ch in "\\;&|$`\n\r\"'<>"), fileB)
            check("وهو داخل مجلّد صاحبه لا غير",
                  fileB.startswith(f"exports/{uidB}/"), fileB)

        # ═══ الملفّات الثابتة ═══
        head("الملفّات الثابتة لا تُستعمل بابًا")
        for path in ("/icons/../app.py", "/icons/..%2fapp.py", "/fonts/../falah.db",
                     "/fonts/../../etc/passwd", "/icons/x.png", "/fonts/x.ttf"):
            st, _, _ = req(base, path, cookie=A)
            check(f"لا يُقدَّم: {path[:40]}", st >= 400, str(st))

        # ═══ الحدود ═══
        head("حدود الموارد معلنةٌ ومطبَّقة")
        lim = req(base, "/app/limits", cookie=A)[1]
        for k in ("max_queued_per_user", "max_running", "max_cards_per_job",
                  "max_video_seconds", "max_storage_mb_per_user",
                  "job_timeout_seconds", "max_retries"):
            check(f"حدٌّ معلَن: {k}", isinstance(lim.get(k), int) and lim[k] > 0, str(lim.get(k)))
        st, dd, _ = req(base, "/app/register",
                        {"email": "x" * 500 + "@t.com", "password": PW}, None)
        check("بريدٌ فاحشُ الطول يُرفض", st >= 400, str(st))
        st, dd, _ = req(base, "/app/projects/create", {"title": "ع" * 5000}, A)
        check("عنوانٌ فاحشُ الطول يُرفض أو يُقصّ", st >= 400 or
              len(req(base, f"/app/projects/{dd.get('id')}", cookie=A)[1]
                  ["project"]["title"]) <= 120, str(st))
        # ═══ B23 · حدُّ الجسم: دلالةُ HTTP مفصولةٌ عن سلوك النقل ═══
        # كان هذا البند يُقاس بـ`urllib` فيسقط متقطّعًا. والسقوطُ لم يكن في
        # الخادم بل في القياس: `urllib` يعامل خطأَ الكتابة خطأً نهائيًّا فلا
        # يقرأ ردًّا وصل فعلًا. فصُلت الطبقتان ولم يُخفَّف شيء — بل صار
        # المقيسُ أدقَّ وأشدَّ.

        # ① دلالةُ HTTP — هل الخادمُ يفي بالعقد؟
        r = oversized(base, 1_100_000)
        check("جسمٌ فوق الحدّ يُردّ ٤١٣ لا صمتًا ولا «حقل ناقص»",
              r["status"] == 413 and "أكبر من الحدّ" in str(r["body"]),
              f"{r['status']} {str(r['body'])[:60]}")
        check("والرسالة تقول الحدَّ وما وصل",
              isinstance(r["body"], dict)
              and "limit_bytes" in r["body"] and "got_bytes" in r["body"])
        check("والردُّ يُعلن إغلاقَ الاتصال — فلا تُقرأ البقيّةُ طلبًا تاليًا",
              "Connection: close" in r["head"], r["head"].splitlines()[-1][:50])
        for label, n, chunk in (("فوق الحدّ ببايتاتٍ قليلة", 1_000_100, 65536),
                                ("فوق الحدّ بعشرة أضعاف", 10_000_000, 65536),
                                ("بدفعاتٍ صغيرة (٤ ك.ب)", 1_100_000, 4096)):
            rr = oversized(base, n, chunk)
            check(f"و٤١٣ ثابتةٌ مهما كان الحجمُ والدفعة: {label}",
                  rr["status"] == 413, str(rr["status"]))

        # ② سلوكُ النقل — الحدُّ المعروف، مُثبَتٌ لا مسكوتٌ عنه
        check("**والخادمُ لا يستنزف الجسمَ المرفوض** — يردّ بعد الترويسات ويغلق",
              r["sent"] < r["total"],
              f"أُرسل {r['sent']:,} من {r['total']:,} قبل وصول الردّ")
        # عميلٌ يعتبر خطأَ الكتابة نهائيًّا (كـurllib) قد يفوته الردُّ الواصل.
        # يُقاس ولا يُدَّعى: عشرون محاولةً تُصنَّف. والثابتُ المطلوب أن الخطأ
        # إمّا ٤١٣ صحيحةٌ وإمّا خطأُ نقل — **ولا رمزَ حالةٍ خاطئ أبدًا**.
        seen = {}
        for _ in range(20):
            st2, dd2, _ = req(base, "/app/export",
                              {"project": 1, "junk": "x" * 1_100_000}, A)
            seen[st2] = seen.get(st2, 0) + 1
        check("وعميلٌ لا يقرأ عند خطأ الكتابة يرى إمّا ٤١٣ وإمّا قطعَ نقل — "
              "ولا رمزَ حالةٍ خاطئًا أبدًا",
              set(seen) <= {413, 0}, str(seen))
        check("ويرى ٤١٣ في بعضها على الأقلّ — فالردُّ يُرسَل فعلًا",
              seen.get(413, 0) >= 1, f"٤١٣ في {seen.get(413,0)} من ٢٠")
        # جسمٌ هائل: العميل قد ينكسر أنبوبه، والمهمّ أن يبقى الخادم حيًّا
        req(base, "/app/export", {"project": 1, "junk": "x" * 6_000_000}, A)
        check("والخادم يبقى حيًّا بعد جسمٍ هائل",
              req(base, "/healthz")[0] == 200)

        head("حدُّ المعدّل على المكلف — ٤٢٩ لا ٤٠٠")
        # الطلبُ المكرَّر نفسه لا يُحسب: التزامن المشروع لا يُعاقَب
        s2, d2, _ = req(base, "/app/projects/create",
                        {"title": "حدّ", "skin": "parch", "ratio": "square"}, A)
        pidA = d2["id"]
        req(base, "/app/items/add",
            {"project": pidA, "kind": "quran", "ref": {"surah": 112, "ayah": 1}}, A)
        import threading
        got = []
        def dup():
            got.append(req(base, "/app/export", {"project": pidA}, A)[0])
        ts = [threading.Thread(target=dup) for _ in range(25)]
        [t.start() for t in ts]; [t.join() for t in ts]
        check("٢٥ نقرةً على الزرّ نفسه لا تُعدّ ٢٥ عملًا",
              got.count(429) == 0, f"٤٢٩ ظهر {got.count(429)} مرّة")

        # أعمالٌ مختلفةٌ فعلًا: هنا يجب أن يظهر الحدّ
        # عملٌ مقبولٌ جديد يعني مهمّةً جديدة، ولا تكون جديدةً إلا بعد انتهاء
        # سابقتها (مفتاح التفرّد يمنع اثنتين حيّتين بالبصمة نفسها). فننتظر.
        codes = []
        for _ in range(10):
            st3, d3, _ = req(base, "/app/export", {"project": pidA}, A)
            codes.append(st3)
            if st3 == 429: break
            jid = (d3 or {}).get("job", {}).get("id")
            if jid:
                t1 = time.time()
                while time.time() - t1 < 120:
                    if not req(base, f"/app/jobs/{jid}", cookie=A)[1]["job"]["waiting"]: break
                    time.sleep(0.4)
        check("وأعمالٌ مقبولةٌ متتابعة تبلغ الحدّ فيظهر ٤٢٩",
              429 in codes, f"الرموز {codes}")
        st4, d4, _ = req(base, "/app/export", {"project": pidA}, A)
        check("والرسالة تقول الحدَّ ونافذته",
              st4 == 429 and "limit" in str(d4) and "window_seconds" in str(d4),
              f"{st4} {str(d4)[:70]}")
        check("والحدُّ لصاحبه وحده — ب ما زال يصدّر",
              req(base, "/app/export", {"project": pidB}, B)[0] in (202, 400),
              str(req(base, "/app/export", {"project": pidB}, B)[0]))

        # ═══ القيم المعدودة ═══
        head("القيم المعدودة تُرفض عند الباب")
        # حسابٌ نظيف: حصّةُ أ نفدت، ورسالةُ الحصّة تشبه رسالةَ الرفض فتخلط
        C, uidC, _ = account("C")
        for field, bad in (("skin", "'; DROP TABLE users--"), ("ratio", "../../etc"),
                           ("kind", "<script>"), ("skin", "red}body{x:url(http://e/)}"),
                           ("ratio", "square\"><img src=x onerror=alert(1)>")):
            st, dd, _ = req(base, "/app/projects/create", {"title": "ت", field: bad}, C)
            check(f"{field}={bad[:24]} — يُرفض بسببه",
                  st >= 400 and "غير مقبولة" in str(dd), f"{st} {str(dd)[:50]}")
        st, dd, _ = req(base, "/app/projects/create",
                        {"title": "ت", "skin": "night", "ratio": "square"}, C)
        check("والقيمُ الصحيحة تمرّ", st == 201, f"{st} {str(dd)[:40]}")
        # وحدُّ الطول يُرفض بسببه هو الآخر
        st, dd, _ = req(base, "/app/projects/update",
                        {"id": dd.get("id"), "watermark": "و" * 200}, C)
        check("وعلامةٌ أطول من حدّها تُرفض بسببها",
              st >= 400 and "أطول من" in str(dd), f"{st} {str(dd)[:50]}")

        # ═══ حدُّ المحاولات ═══
        head("حدُّ محاولات الدخول")
        codes = []
        for _ in range(12):
            codes.append(req(base, "/app/login", {"email": mailB, "password": "خطأ"})[0])
        check("المحاولات المتكرّرة تُحبس", any(c >= 400 for c in codes[-3:]), str(codes[-4:]))
        msg = req(base, "/app/login", {"email": mailB, "password": "خطأ"})[1]
        check("والرسالة تقول إنه حبسٌ لا خطأ كلمة",
              "محاولات" in str(msg.get("error", "")), str(msg)[:60])
        st, dd, _ = req(base, "/app/login", {"email": mailA, "password": PW})
        check("وحبسُ ب لا يحبس أ", st == 200, f"{st} {str(dd)[:40]}")
    finally:
        p.kill(); p.wait(timeout=15)
        for m in made: shutil.rmtree(m, ignore_errors=True)
        shutil.rmtree(d, ignore_errors=True)

    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: نجح {OK} · سقط {FAIL}")
        for n, dd in FAILURES: print(f"  ✗ {n}  ← {dd}")
        return 1
    print(f"النتيجة: الحدود صامدة ✓  ({OK} بندًا)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
