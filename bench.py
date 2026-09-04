#!/usr/bin/env python3
"""قياسُ الخطّ الأساس — يُشغَّل قبل التفكيك وبعده بالأمر نفسه.

    python3 bench.py --label BEFORE      # يكتب baseline/BEFORE.json
    python3 bench.py --label AFTER
    python3 bench.py --compare BEFORE AFTER

ما يُقاس:
  • زمنُ المسار (latency) — عبر HTTP على خادمٍ حقيقيّ بقاعدةٍ مؤقّتة
  • عددُ استعلامات القاعدة لكل مسار — بعدّادٍ على `sqlite3.Cursor.execute`
  • زمنُ الوضع في الطابور — `POST /app/export` و`POST /app/video`
  • أعدادُ الفحوص في كل حزمة

القاعدة: الأرقام مقيسةٌ من تشغيلٍ فعليّ. وما تعذّر قياسُه يُكتب `null`
ويُقال لماذا — لا يُقدَّر ولا يُنسخ من تقريرٍ سابق.
"""
import argparse, json, os, socket, sqlite3, statistics, subprocess, sys, tempfile, time
import urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "baseline")
PW   = "Str0ng-Pass!x9"

# المسارات المقيسة. الثلاثة الأولى تشغيلية، والباقي محتوًى وتطبيق.
ROUTES = [
    ("/healthz",                                   "public"),
    ("/readyz",                                    "public"),
    ("/health",                                    "public"),
    ("/card?kind=quran&surah=94&ayah=5&to=6",      "public"),
    ("/card?kind=hadith&book=bukhari&no=1",        "public"),
    ("/quran/search?q=%D8%A7%D9%84%D8%B5%D8%A8%D8%B1&limit=10", "public"),
    ("/hadith/search?q=%D8%A7%D9%84%D9%86%D9%8A%D8%A9&limit=10", "public"),
    ("/chapters?book=bukhari",                     "public"),
    ("/templates?kind=quran&limit=20",             "public"),
    ("/topics",                                    "public"),
    ("/series?topic=1&count=5",                    "public"),
    ("/sources",                                   "public"),
    ("/app/config",                                "public"),
    ("/app/me",                                    "session"),
    ("/app/entitlements",                          "session"),
    ("/app/projects",                              "session"),
    ("/app/jobs",                                  "session"),
    ("/app/exports",                               "session"),
    ("/app/limits",                                "session"),
]

# ══════════════ أدواتٌ مشتركة ══════════════

def free_port():
    s = socket.socket(); s.bind(("", 0)); p = s.getsockname()[1]; s.close(); return p

def req(base, path, body=None, cookie=None, timeout=30, hdr=None):
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
            try:    return x.status, json.loads(b), x.headers.get_all("Set-Cookie") or []
            except Exception: return x.status, {"bytes": len(b)}, []
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read()), []
        except Exception: return e.code, None, []
    except Exception as e:
        return 0, {"error": type(e).__name__}, []

N = int(os.environ.get("BENCH_N", 25))

def timed(base, path, cookie=None, n=None, warm=5):
    """يعيد (وسيط, أدنى, أقصى) بالملّي ثانية — الوسيطُ لا المتوسّط، فلا
    تجرّه قفزةٌ واحدة من جامع القمامة أو من القرص."""
    n = n or N
    for _ in range(warm): req(base, path, cookie=cookie)
    xs, code = [], None
    for _ in range(n):
        t = time.perf_counter()
        code = req(base, path, cookie=cookie)[0]
        xs.append((time.perf_counter() - t) * 1000)
    xs.sort()
    return {"p50": round(statistics.median(xs), 2), "min": round(xs[0], 2),
            "max": round(xs[-1], 2), "n": n, "status": code}

# ══════════════ عدّ الاستعلامات ══════════════
# يُقاس داخل العملية لا عبر الشبكة: `api.H.do_GET` يُستدعى على قشرةٍ
# كما يفعل `proxy_content` تمامًا، والقاعدةُ تُفتح بصنفٍ يعدّ.

class Counting(sqlite3.Connection):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.qcount = 0
    def execute(self, *a, **k):
        self.qcount += 1; return super().execute(*a, **k)
    def cursor(self, *a, **k):
        outer = self
        class C(sqlite3.Cursor):
            def execute(self, *b, **kk):
                outer.qcount += 1; return super().execute(*b, **kk)
        return super().cursor(C)

def queries_for(paths):
    """عددُ استعلامات القاعدة لكل مسارِ محتوى. يستورد `api` مرّةً ويستبدل
    `conn` بواحدةٍ تعدّ — ولا يمسّ منطق الحكم بشيء."""
    sys.path.insert(0, HERE)
    import api
    out, orig = {}, api.conn

    def one(path):
        holder = {}

        def counting_conn():
            c = sqlite3.connect(f"file:{api.DB}?mode=ro", uri=True, factory=Counting)
            c.row_factory = sqlite3.Row
            holder["c"] = c
            return c

        class Shim(api.H):
            def __init__(self):  self.path = path; self.headers = {}
            def _send(self, obj, code=200): holder["code"] = code
            def log_message(self, *a): pass

        api.conn = counting_conn
        api.H.do_GET(Shim())
        return {"queries": holder["c"].qcount, "status": holder.get("code")}

    for path in paths:
        try:
            out[path] = one(path)
        except Exception as e:
            out[path] = {"queries": None, "why": f"{type(e).__name__}: {e}"}
    api.conn = orig
    return out

# ══════════════ التشغيل ══════════════

def measure(label):
    d = tempfile.mkdtemp(prefix="falah-bench-")
    port = free_port(); base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, FALAH_APP_DB=os.path.join(d, "app.db"), PORT=str(port),
               # بلا عاملٍ داخليّ: نقيس زمنَ **الوضع في الطابور** لا التصيير.
               FALAH_INLINE_WORKER="0", FALAH_RATE_REGISTER="10000",
               FALAH_RATE_EXPORT="10000", FALAH_RATE_VIDEO="10000",
               FALAH_RATE_LOGIN="10000")
    log = open(os.path.join(d, "app.log"), "w")
    p = subprocess.Popen([sys.executable, "app.py"], cwd=HERE, env=env,
                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    res = {"label": label, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "git": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                                 capture_output=True, text=True).stdout.strip(),
           "routes": {}, "queries": {}, "enqueue": {}, "sizes": {}}
    try:
        for _ in range(80):
            if req(base, "/healthz", timeout=2)[0] == 200: break
            time.sleep(0.5)
        else:
            raise SystemExit("الخادم لم يُقلع — انظر " + os.path.join(d, "app.log"))

        mail = f"bench{int(time.time()*1000)%10**9}@bench.test"
        s, dd, ck = req(base, "/app/register",
                        {"email": mail, "password": PW, "name": "bench", "watermark": "bench"})
        cookie = ck[0].split(";")[0] if ck else None
        if not cookie: raise SystemExit(f"تعذّر إنشاء حساب القياس: {s} {dd}")

        # خطّةٌ موسَّعة لحساب القياس وحده: الخطّةُ المجانية حدُّها مشروعان
        # وصفرُ مقاطع، فلا يبلغ القياسُ ما يريد قياسه.
        #
        # والمنحةُ عبر المسار الإداريّ نفسه — لكن بدورٍ حقيقيّ لا بمفتاحٍ
        # مشترك (أُلغي في P1.2). الحسابُ يُرقّى بأمرٍ محلّيّ ثم يعيد الدخول،
        # لأن الترقيةَ تُنهي الجلسات. ولا يُضعَّف حدٌّ في الشيفرة لأجل قياس.
        subprocess.run([sys.executable, "-m", "falah.roles", "grant", mail,
                        "super_admin", "--reason", "bench"],
                       cwd=HERE, env=env, capture_output=True, check=True)
        s2, d2, ck2 = req(base, "/app/login", {"email": mail, "password": PW})
        cookie = ck2[0].split(";")[0] if ck2 else cookie
        s2, d2, _ = req(base, "/app/subscription/grant",
                        {"plan": "studio", "days": 1}, cookie)
        if s2 != 200: raise SystemExit(f"تعذّرت منحةُ خطّة القياس: {s2} {d2}")

        # مشروعٌ بعنصرين — لقياس التصدير ولملء `/app/projects`
        pid = req(base, "/app/projects/create",
                  {"title": "قياس", "kind": "series"}, cookie)[1]["id"]
        for ref in ({"surah": 94, "ayah": 5}, {"surah": 94, "ayah": 6}):
            s3, d3, _ = req(base, "/app/items/add",
                            {"project": pid, "kind": "quran", "ref": ref}, cookie)
            if s3 != 201: raise SystemExit(f"تعذّرت إضافة عنصر القياس: {s3} {d3}")

        print(f"▸ زمنُ المسارات ({label})")
        for path, auth in ROUTES:
            r = timed(base, path, cookie if auth == "session" else None)
            res["routes"][path] = {**r, "auth": auth}
            print(f"  {r['p50']:>8.2f} م.ث  {path}  [{r['status']}]")

        # ── زمنُ الوضع في الطابور ──
        # لكلٍّ مشروعٌ جديد: مفتاحُ التفرّد يجعل الطلبَ الثاني على المشروع
        # نفسه ردًّا على مهمّةٍ قائمة — وهو مسارٌ آخر لا الوضع.
        print(f"\n▸ زمنُ الوضع في الطابور ({label})")
        for kind, n in (("export", max(12, N // 2)), ("video", max(12, N // 2))):
            xs, codes = [], set()
            for i in range(n):
                q = req(base, "/app/projects/create",
                        {"title": f"q{kind}{i}", "kind": "series"}, cookie)[1]["id"]
                req(base, "/app/items/add",
                    {"project": q, "kind": "quran",
                     "ref": {"surah": 94, "ayah": 5}}, cookie)
                if kind == "export":
                    body, path = {"project": q}, "/app/export"
                else:
                    it = req(base, f"/app/projects/{q}", cookie=cookie)[1]["items"][0]["id"]
                    body, path = {"project": q, "item": it}, "/app/video"
                t = time.perf_counter()
                code, out, _ = req(base, path, body, cookie)
                xs.append((time.perf_counter() - t) * 1000); codes.add(code)
                # تُلغى بعد القياس: حدُّ المنتظر خمسٌ لكل مستخدم، وهو حدٌّ
                # مقصود. الإلغاء خارج النافذة المقيسة فلا يدخل في الرقم.
                jid = ((out or {}).get("job") or {}).get("id")
                if jid: req(base, "/app/jobs/cancel", {"id": jid}, cookie)
            xs.sort()
            res["enqueue"][kind] = {"p50": round(statistics.median(xs), 2),
                                    "min": round(xs[0], 2), "max": round(xs[-1], 2),
                                    "n": n, "statuses": sorted(codes)}
            print(f"  {res['enqueue'][kind]['p50']:>8.2f} م.ث  POST /app/{kind}  {sorted(codes)}")
    finally:
        p.terminate()
        try: p.wait(timeout=10)
        except Exception: p.kill()
        log.close()

    # `/healthz` و`/readyz` من طبقة التطبيق لا من `api`، و`/series` يفتح
    # اتصالَه داخل `carousel` — فلا يعدّها هذا العدّاد. تُستثنى صراحةً بدل
    # أن تُكتب صفرًا يوهم أنها بلا استعلام.
    print(f"\n▸ عددُ استعلامات القاعدة ({label})")
    skip = {"/healthz", "/readyz", "/series?topic=1&count=5"}
    res["queries"] = queries_for([r for r, a in ROUTES
                                  if a == "public" and not r.startswith("/app")
                                  and r not in skip])
    res["queries_not_counted"] = {
        "/healthz": "طبقة التطبيق — لا تمرّ بـapi.conn",
        "/readyz": "طبقة التطبيق — لا تمرّ بـapi.conn",
        "/series?topic=1&count=5": "carousel يفتح اتصالَه بنفسه"}
    for k, v in res["queries"].items():
        print(f"  {str(v['queries']):>8}  {k}")

    res["sizes"] = {f: sum(1 for _ in open(os.path.join(HERE, f), encoding="utf-8"))
                    for f in ("app.py", "api.py")}
    for f in ("falah/authz.py", "falah/routing.py", "falah/handlers_app.py",
              "falah/handlers_content.py"):
        fp = os.path.join(HERE, f)
        if os.path.exists(fp):
            res["sizes"][f] = sum(1 for _ in open(fp, encoding="utf-8"))

    os.makedirs(OUT, exist_ok=True)
    dst = os.path.join(OUT, f"{label}.json")
    json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n✓ كُتب {dst}")
    return res

def compare(a, b):
    A = json.load(open(os.path.join(OUT, f"{a}.json"), encoding="utf-8"))
    B = json.load(open(os.path.join(OUT, f"{b}.json"), encoding="utf-8"))
    print(f"\n{'المسار':<44} {a:>10} {b:>10} {'الفرق':>10}")
    print("─" * 78)
    worse = []
    for k in A["routes"]:
        if k not in B["routes"]: print(f"{k:<44} {'—':>10} {'مفقود':>10}"); continue
        x, y = A["routes"][k]["p50"], B["routes"][k]["p50"]
        d = (y - x) / x * 100 if x else 0
        flag = " ⚠" if d > 20 and y - x > 0.5 else ""
        if flag: worse.append((k, x, y))
        print(f"{k:<44} {x:>10.2f} {y:>10.2f} {d:>+9.1f}%{flag}")
    print("\nاستعلامات القاعدة")
    for k in A["queries"]:
        x = A["queries"][k]["queries"]; y = (B["queries"].get(k) or {}).get("queries")
        flag = " ⚠" if (x is not None and y is not None and y > x) else ""
        print(f"{k:<44} {str(x):>10} {str(y):>10}{flag}")
    print("\nالوضع في الطابور")
    for k in A["enqueue"]:
        x = A["enqueue"][k]["p50"]; y = B["enqueue"][k]["p50"]
        print(f"{'POST /app/'+k:<44} {x:>10.2f} {y:>10.2f} {(y-x)/x*100:>+9.1f}%")
    print("\nأسطرُ الملفّات")
    for k in sorted(set(A["sizes"]) | set(B["sizes"])):
        print(f"{k:<44} {str(A['sizes'].get(k,'—')):>10} {str(B['sizes'].get(k,'—')):>10}")
    if worse:
        print(f"\n⚠ {len(worse)} مسارًا تباطأ بأكثر من ٢٠٪ — يُفسَّر أو يُصلَح، لا يُتجاوز.")
    return worse

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"))
    a = ap.parse_args()
    if a.compare: compare(*a.compare)
    elif a.label: measure(a.label)
    else: ap.error("--label أو --compare")
