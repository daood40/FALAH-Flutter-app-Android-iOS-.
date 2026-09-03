#!/usr/bin/env python3
"""اختبار الكسر المتعمَّد — نُعطب النظام بيدنا لنرى كيف يسقط.

    APP=http://localhost:8080 python3 failure_test.py

الفرق بين هذا وبين `tests.py`: ذاك يسأل «هل يعمل حين تسير الأمور؟»،
وهذا يسأل «كيف يسقط حين لا تسير؟». والسقوط الجيّد له علامتان: **لا يضيع
عملُ المستخدم**، و**يُقال له ما جرى بلغةٍ يفهمها** لا برسالة استثناء.

يُشغَّل على خادمٍ اختباريّ بقاعدةٍ مؤقّتة — لا يمسّ `app.db` الحقيقية.
"""
import json, os, shutil, signal, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OK = FAIL = 0; FAILURES = []
PW  = "Str0ng-Pass!x9"

def check(n, c, d=""):
    global OK, FAIL
    if c: OK += 1; print(f"  ✓ {n}" + (f"  ({d})" if d else ""))
    else: FAIL += 1; FAILURES.append((n, d)); print(f"  ✗ {n}" + (f"  ← {d}" if d else ""))
def head(t): print(f"\n▸ {t}")

# ───────────────────────── أدوات الشبكة ─────────────────────────

def req(base, path, body=None, cookie=None, method=None, timeout=30, hdr=None):
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if data is not None: h["X-FALAH"] = "1"
    if cookie: h["Cookie"] = cookie
    h.update(hdr or {})
    r = urllib.request.Request(url, data=data, headers=h,
                               method=method or ("POST" if data is not None else "GET"))
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            raw = x.read()
            try:    return x.status, json.loads(raw.decode()), x.headers.get_all("Set-Cookie") or []
            except Exception: return x.status, {"bytes": len(raw)}, []
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read().decode()), []
        except Exception: return e.code, None, []
    except Exception as e:
        return 0, {"error": type(e).__name__ + ": " + str(e)}, []

def free_port():
    s = socket.socket(); s.bind(("", 0)); p = s.getsockname()[1]; s.close(); return p

def up(base, tries=60):
    for _ in range(tries):
        if req(base, "/healthz", timeout=2)[0] == 200: return True
        time.sleep(0.5)
    return False

class Rig:
    """خادمٌ اختباريّ بقاعدةٍ مؤقّتة ومجلّد صادراتٍ منفصل."""
    def __init__(self, inline=False):
        self.dir  = tempfile.mkdtemp(prefix="falah-fail-")
        self.db   = os.path.join(self.dir, "app.db")
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.env  = dict(os.environ, FALAH_APP_DB=self.db, PORT=str(self.port),
                         FALAH_INLINE_WORKER="1" if inline else "0",
                         FALAH_JOB_STALE="3", FALAH_BACKOFF="1")
        self.srv = self.wrk = None

    def start_server(self):
        self.srv = subprocess.Popen([sys.executable, "app.py"], cwd=HERE, env=self.env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
        return up(self.base)

    def stop_server(self, sig=signal.SIGTERM):
        if self.srv: self.srv.send_signal(sig); self.srv.wait(timeout=20); self.srv = None

    def start_worker(self, extra=()):
        self.wrk = subprocess.Popen([sys.executable, "worker.py", *extra], cwd=HERE,
                                    env=self.env, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True)

    def kill_worker(self, hard=True):
        if self.wrk:
            self.wrk.send_signal(signal.SIGKILL if hard else signal.SIGTERM)
            try: self.wrk.wait(timeout=15)
            except Exception: pass
            self.wrk = None

    def close(self):
        self.kill_worker()
        try: self.stop_server(signal.SIGKILL)
        except Exception: pass
        shutil.rmtree(self.dir, ignore_errors=True)

    # ــ حسابٌ ومشروعٌ جاهزان ــ
    def account(self, tag="f"):
        m = f"{tag}{int(time.time()*1000)%10**9}@fail.test"
        s, d, ck = req(self.base, "/app/register", {"email": m, "password": PW,
                                                    "name": "كسر", "watermark": "ق"})
        return (ck[0].split(";")[0] if ck else None), m

    def project(self, cookie, refs=({"surah": 108, "ayah": 1, "to": 3},)):
        s, d, _ = req(self.base, "/app/projects/create",
                      {"title": "كسر", "skin": "parch", "ratio": "square"}, cookie)
        pid = (d or {}).get("id")
        for r in refs:
            req(self.base, "/app/items/add", {"project": pid, "kind": "quran", "ref": r}, cookie)
        return pid

def wait_state(rig, cookie, jid, want, limit=200):
    t0 = time.time()
    last = None
    while time.time() - t0 < limit:
        s, d, _ = req(rig.base, f"/app/jobs/{jid}", cookie=cookie)
        if s != 200: return None
        last = d["job"]
        if last["state"] in (want if isinstance(want, (set, tuple, list)) else {want}):
            return last
        if not last["waiting"]: return last
        time.sleep(0.5)
    return last

# ═════════════════ ١ · العامل يتوقّف فجأةً ═════════════════

def t_worker_crash():
    head("العامل يُقتل في منتصف المهمّة")
    rig = Rig(inline=False)
    try:
        if not rig.start_server(): return check("الخادم يقوم", False)
        cookie, _ = rig.account("wc")
        pid = rig.project(cookie)
        s, d, _ = req(rig.base, "/app/export", {"project": pid}, cookie)
        jid = d["job"]["id"]
        rig.start_worker()
        # ننتظر حتى تدخل التصيير فعلًا ثم نقتل العامل قتلًا لا يمهله
        t0 = time.time(); entered = False
        while time.time() - t0 < 60:
            s2, d2, _ = req(rig.base, f"/app/jobs/{jid}", cookie=cookie)
            if d2 and d2["job"]["state"] == "running": entered = True; break
            time.sleep(0.2)
        check("المهمّة دخلت التصيير", entered)
        rig.kill_worker(hard=True)
        j = req(rig.base, f"/app/jobs/{jid}", cookie=cookie)[1]["job"]
        check("المهمّة تبقى «تجري» لحظةَ القتل — لا تُفقد", j["state"] == "running", j["state"])

        rig.start_worker()          # عاملٌ جديد: عليه أن يلتقطها بعد انقطاع النبض
        j2 = wait_state(rig, cookie, jid, {"done", "failed"}, limit=200)
        check("عاملٌ جديد يلتقط ما تركه المقتول ويُتمّه",
              bool(j2) and j2["state"] == "done", str(j2 and (j2["state"], j2["error"])))
        check("والنتيجة سليمةٌ لا ناقصة",
              bool(j2) and bool((j2.get("result") or {}).get("files")))
        check("والمحاولة الثانية مسجَّلةٌ لا مخفيّة",
              bool(j2) and j2["attempts"] >= 2, str(j2 and j2["attempts"]))
    finally:
        rig.close()

# ═════════════════ ٢ · الخادم يُعاد تشغيله ═════════════════

def t_server_restart():
    head("الخادم يُعاد تشغيله والمهمّة في الطابور")
    rig = Rig(inline=False)
    try:
        if not rig.start_server(): return check("الخادم يقوم", False)
        cookie, mail = rig.account("sr")
        pid = rig.project(cookie)
        s, d, _ = req(rig.base, "/app/export", {"project": pid}, cookie)
        jid = d["job"]["id"]
        check("المهمّة في الطابور قبل الإطفاء", d["job"]["state"] == "queued")

        rig.stop_server(signal.SIGTERM)
        check("الخادم أُطفئ", req(rig.base, "/healthz", timeout=2)[0] == 0)
        if not rig.start_server(): return check("الخادم يقوم ثانيةً", False)
        check("الخادم قام ثانيةً", True)

        s2, d2, _ = req(rig.base, f"/app/jobs/{jid}", cookie=cookie)
        check("الجلسة نجت من إعادة التشغيل", s2 == 200, str(s2))
        check("المهمّة لم تضِع — الطابور على القرص لا في الذاكرة",
              s2 == 200 and d2["job"]["state"] == "queued", str(d2))

        rig.start_worker()
        j = wait_state(rig, cookie, jid, "done", limit=200)
        check("وتكتمل بعد العودة", bool(j) and j["state"] == "done",
              str(j and (j["state"], j["error"])))
    finally:
        rig.close()

# ═════════════════ ٣ · العامل يُعاد تشغيله ═════════════════

def t_worker_restart():
    head("العامل يُعاد تشغيله ومهامٌّ تنتظر")
    rig = Rig(inline=False)
    try:
        if not rig.start_server(): return check("الخادم يقوم", False)
        # ثلاثةُ أصحابٍ لا صاحبٌ واحد: الطلبُ نفسه من الصاحب نفسه بصمةٌ
        # واحدة فمهمّةٌ واحدة (وهو المطلوب)، فلا يُبنى منه ثلاثُ مهامّ.
        # والخطّة المجانية تسمح بمشروعين، فالتنويع بالحسابات أصدق.
        accs, ids = [], []
        for i in range(3):
            ck, _ = rig.account(f"wr{i}")
            p = rig.project(ck, ({"surah": 112, "ayah": 1, "to": 2},))
            s, d, _ = req(rig.base, "/app/export", {"project": p}, ck)
            if s == 202: accs.append(ck); ids.append(d["job"]["id"])
        check("ثلاث مهامّ في الطابور بلا عامل", len(ids) == 3, str(ids))
        rig.start_worker(); time.sleep(6); rig.kill_worker(hard=False)   # إنهاءٌ مهذَّب
        rig.start_worker()
        done = [wait_state(rig, ck, j, "done", limit=240) for ck, j in zip(accs, ids, strict=True)]
        check("كلّها تكتمل رغم إعادة تشغيل العامل",
              all(x and x["state"] == "done" for x in done),
              str([x and x["state"] for x in done]))
        check("لكل مهمّةٍ سطرٌ واحد لا سطران", len(set(ids)) == 3, str(ids))
        check("وكلٌّ سلّمت ملفّاتٍ موجودةً على القرص",
              all(x and (x.get("result") or {}).get("files")
                  and all(os.path.isfile(os.path.join(HERE, f))
                          for f in x["result"]["files"]) for x in done))
        check("ولكلٍّ مجلّدُه — لا يكتب أحدٌ فوق ملفّات غيره",
              len({(x.get("result") or {}).get("dir") for x in done}) == 3,
              str([(x.get("result") or {}).get("dir") for x in done]))
    finally:
        rig.close()

# ═════════════════ ٤ · القاعدة تختفي لحظةً ═════════════════

def t_db_unavailable():
    head("قاعدة المحتوى تُنتزع من تحت الخادم")
    rig = Rig(inline=True)
    try:
        if not rig.start_server(): return check("الخادم يقوم", False)
        cookie, _ = rig.account("db")
        check("الجاهزية خضراء قبل العطب", req(rig.base, "/readyz")[0] == 200)
        # ملاحظةٌ من تجربةٍ سابقة: `chmod 000` لا يمنع root من القراءة، فكان
        # الحقنُ وهميًّا والاختبارُ يمرّ كذبًا. الإزاحةُ تعطب فعلًا: الاتّصال
        # التالي لا يجد ملفًّا، وهو ما يحدث حين يُفصل قرصٌ أو يُحذف حجم.
        _db = os.path.join(HERE, "falah.db")
        _moved = _db + ".moved-by-failure-test"
        os.rename(_db, _moved)
        for _sfx in ("-wal", "-shm"):
            if os.path.exists(_db + _sfx): os.rename(_db + _sfx, _moved + _sfx)
        try:
            s, d, _ = req(rig.base, "/card?kind=quran&surah=1&ayah=1")
            check("طلبُ محتوًى على قاعدةٍ معطوبة لا يُسقط الخادم", s in (0, 500, 503), str(s))
            check("ولا يسرّب نصّ الاستثناء للمستخدم",
                  not d or "Traceback" not in str(d), str(d)[:80])
            s2, d2, _ = req(rig.base, "/readyz")
            check("الجاهزية تنقلب حمراء ٥٠٣ لا تكذب",
                  s2 == 503 and d2.get("content_db") is False, f"{s2} {str(d2)[:60]}")
            check("والحياة تبقى خضراء — العملية حيّة والخلل خارجها",
                  req(rig.base, "/healthz")[0] == 200)
        finally:
            os.rename(_moved, _db)
            for _sfx in ("-wal", "-shm"):
                if os.path.exists(_moved + _sfx): os.rename(_moved + _sfx, _db + _sfx)
        time.sleep(0.5)
        check("الجاهزية تعود خضراء بلا إعادة تشغيل", req(rig.base, "/readyz")[0] == 200)
    finally:
        rig.close()

# ═════════════════ ٥ · مهمّةٌ فاسدةٌ ومهمّةٌ عالقة ═════════════════

def t_bad_and_stuck():
    head("مهمّةٌ فاسدة · مهمّةٌ عالقة · حمولةٌ مزوَّرة")
    rig = Rig(inline=True)
    try:
        if not rig.start_server(): return check("الخادم يقوم", False)
        cookie, _ = rig.account("bs")
        # مشروعٌ فارغ: خطأُ مستخدمٍ لا يُعاد
        s, d, _ = req(rig.base, "/app/projects/create", {"title": "فارغ"}, cookie)
        empty = d["id"]
        s2, d2, _ = req(rig.base, "/app/export", {"project": empty}, cookie)
        check("المشروع الفارغ يُردّ عند الباب لا يُوضع في الطابور",
              s2 == 400 and "فارغ" in str(d2), f"{s2} {str(d2)[:50]}")

        # مشروع غيره
        c2, _ = rig.account("bs2")
        pid = rig.project(cookie)
        s3, d3, _ = req(rig.base, "/app/export", {"project": pid}, c2)
        check("تصدير مشروع غيره مرفوض", s3 >= 400, str(s3))

        # مدخلاتٌ فاسدة
        for body, name in (({"project": "أبجد"}, "رقم مشروعٍ نصّيّ"),
                           ({}, "طلبٌ بلا مشروع"),
                           ({"project": -1}, "رقمٌ سالب"),
                           ({"project": 10**12}, "رقمٌ لا وجود له")):
            sx, dx, _ = req(rig.base, "/app/export", body, cookie)
            check(f"{name} يُردّ بخطأٍ نظيف",
                  400 <= sx < 500 and dx and "Traceback" not in str(dx),
                  f"{sx} {str(dx)[:50]}")

        # مهمّةٌ عالقة: نكتبها «تجري» بنبضٍ قديم ثم نرى هل تُستعاد
        s4, d4, _ = req(rig.base, "/app/export", {"project": pid}, cookie)
        jid = d4["job"]["id"]
        wait_state(rig, cookie, jid, "done", limit=200)
        import sqlite3
        con = sqlite3.connect(rig.db)
        con.execute("""UPDATE jobs SET state='running', attempts=0, heartbeat=?,
                       started_at=?, finished_at=NULL, result=NULL WHERE id=?""",
                    (int(time.time()) - 9999, int(time.time()) - 9999, jid))
        con.commit(); con.close()
        j = wait_state(rig, cookie, jid, {"done", "failed"}, limit=120)
        check("المهمّة العالقة تُستعاد تلقائيًّا ولا تبقى «تجري» أبدًا",
              bool(j) and j["state"] in ("done", "failed"), str(j and j["state"]))
    finally:
        rig.close()

# ═════════════════ ٦ · التصيير نفسه يفشل ═════════════════

def t_render_failure():
    """التصيير يفشل عطبًا عابرًا: نضع ملفًّا مكان مجلّد الصادرات.

    محاولةٌ أولى فاشلة كانت `PLAYWRIGHT_BROWSERS_PATH=/nonexistent` — ولم
    تُعطب شيئًا، لأن `render.py` يحدّد مسار المتصفّح بنفسه ويتراجع إلى
    الافتراضيّ إن غاب. الحقنُ الذي لا يَحقِن يجعل الاختبار يمرّ كذبًا.
    الملفّ مكان المجلّد يعطب فعلًا: `makedirs` يسقط بـOSError، وهو المصنَّف
    عابرًا — فيُختبر مسارُ الإعادة كاملًا حتى الاستسلام وردِّ الحصّة.
    """
    head("التصيير يفشل — القرص يمنع الكتابة")
    rig = Rig(inline=True)
    try:
        if not rig.start_server(): return check("الخادم يقوم", False)
        cookie, _ = rig.account("rf")
        pid = rig.project(cookie)
        me_id = req(rig.base, "/app/me", cookie=cookie)[1]["user"]["id"]
        blocker = os.path.join(HERE, "exports", str(me_id))
        os.makedirs(os.path.dirname(blocker), exist_ok=True)
        shutil.rmtree(blocker, ignore_errors=True)
        open(blocker, "w").write("")        # ملفٌّ حيث يُنتظر مجلّد
        before = req(rig.base, "/app/entitlements", cookie=cookie)[1]["used"]["cards"]
        s, d, _ = req(rig.base, "/app/export", {"project": pid}, cookie)
        check("الطلب يُقبل رغم أن التصيير سيفشل — الفشل يظهر لاحقًا لا في الطلب",
              s == 202, str(s))
        j = wait_state(rig, cookie, d["job"]["id"], "failed", limit=240)
        check("المهمّة تنتهي فاشلةً لا معلّقةً إلى الأبد",
              bool(j) and j["state"] == "failed", str(j and (j["state"], j["step"])))
        check("والسبب مسجَّلٌ لا فارغ", bool(j) and bool(j["error"]), str(j and j["error"])[:70])
        check("وجُرِّبت المحاولات كلّها قبل الاستسلام",
              bool(j) and j["attempts"] >= 2, str(j and j["attempts"]))
        after = req(rig.base, "/app/entitlements", cookie=cookie)[1]["used"]["cards"]
        check("الحصّة رُدَّت كاملةً — لم يخرج شيءٌ فلا يُحاسَب عليه",
              after == before, f"{before} → {after}")
        check("والخادم بقي مستجيبًا خلال الفشل كلّه",
              req(rig.base, "/healthz")[0] == 200)
        os.remove(blocker)
        s2, d2, _ = req(rig.base, "/app/export", {"project": pid}, cookie)
        j2 = wait_state(rig, cookie, d2["job"]["id"], "done", limit=240)
        check("وبعد زوال العطب ينجح الطلب نفسه بلا تدخّل",
              bool(j2) and j2["state"] == "done", str(j2 and (j2["state"], j2["error"])))
    finally:
        shutil.rmtree(os.path.join(HERE, "exports", "0"), ignore_errors=True)
        rig.close()

# ═════════════════ ٧ · ملفٌّ مفقود وطلبٌ غير مصرَّح ═════════════════

def t_missing_and_unauthorized():
    head("ملفٌّ مفقود · وصولٌ غير مصرَّح · تزوير طلب")
    rig = Rig(inline=True)
    try:
        if not rig.start_server(): return check("الخادم يقوم", False)
        cookie, _ = rig.account("mu")
        pid = rig.project(cookie)
        s, d, _ = req(rig.base, "/app/export", {"project": pid}, cookie)
        j = wait_state(rig, cookie, d["job"]["id"], "done", limit=200)
        f0 = j["result"]["files"][0]

        os.remove(os.path.join(HERE, f0))
        s2, d2, _ = req(rig.base, "/app/file?p=" + urllib.parse.quote(f0), cookie=cookie)
        check("ملفٌّ حُذف من القرص يُردّ ٤٠٤ لا خمسمئة",
              s2 == 404 and "Traceback" not in str(d2), f"{s2} {str(d2)[:40]}")

        for bad, name in (("../../etc/passwd", "خروجٌ من المجلّد"),
                          ("exports/999999/1/x.png", "مجلّد مستخدمٍ آخر"),
                          ("app.db", "قاعدة البيانات نفسها"),
                          ("../app.py", "شيفرة الخادم")):
            sx, _, _ = req(rig.base, "/app/file?p=" + urllib.parse.quote(bad), cookie=cookie)
            check(f"لا يُقدَّم عبر المسار: {name}", sx >= 400, str(sx))

        s3, _, _ = req(rig.base, f"/app/jobs/{d['job']['id']}")
        check("استطلاعٌ بلا جلسة يُردّ ٤٠١", s3 == 401, str(s3))
        s4, d4, _ = req(rig.base, "/app/export", {"project": pid}, cookie,
                        hdr={"X-FALAH": ""})
        check("طلبُ كتابةٍ بلا ترويسة الحماية يُردّ ٤٠٣", s4 == 403, str(s4))
        s5, _, _ = req(rig.base, "/app/subscription/grant", {"plan": "studio"}, cookie)
        check("منحُ اشتراكٍ بلا مفتاح إدارة مرفوض", s5 == 403, str(s5))
    finally:
        rig.close()

# ═════════════════ ٨ · الطلب المكرَّر ═════════════════

def t_duplicate():
    head("الطلب المكرَّر — النقرة المزدوجة والشبكة المتقطّعة")
    rig = Rig(inline=False)
    try:
        if not rig.start_server(): return check("الخادم يقوم", False)
        cookie, _ = rig.account("dp")
        pid = rig.project(cookie)
        import threading
        got = []
        def fire():
            got.append(req(rig.base, "/app/export", {"project": pid}, cookie))
        ts = [threading.Thread(target=fire) for _ in range(6)]
        [t.start() for t in ts]; [t.join() for t in ts]
        codes = [g[0] for g in got]
        jids  = {(g[1] or {}).get("job", {}).get("id") for g in got if g[0] == 202}
        check("ستّ نقراتٍ متزامنة لا تُنتج إلا مهمّةً واحدة",
              len(jids) == 1, f"{len(jids)} · {codes}")
        check("والمكرَّر يُردّ بالمهمّة القائمة لا بخطأ",
              all(x == 202 for x in codes), str(codes))
        dups = [g[1].get("duplicate") for g in got if g[0] == 202]
        check("والردّ يقول صراحةً إنه مكرَّر", any(dups), str(dups))
        used = req(rig.base, "/app/entitlements", cookie=cookie)[1]["used"]["cards"]
        check("والحصّة استُهلكت مرّةً واحدة لا ستًّا", used == 1, str(used))

        rig.start_worker()
        j = wait_state(rig, cookie, list(jids)[0], "done", limit=200)
        check("وتُنتج ملفّاتٍ مرّةً واحدة",
              bool(j) and j["state"] == "done", str(j and j["state"]))
        s, d, _ = req(rig.base, "/app/jobs", cookie=cookie)
        check("ولا يبقى في السجلّ إلا مهمّةٌ واحدة",
              len([x for x in d["jobs"] if x["kind"] == "export"]) == 1,
              str(len(d["jobs"])))
    finally:
        rig.close()

# ═════════════════ ٩ · الحدود تحت الضغط ═════════════════

def t_limits():
    head("الحدود تحت الضغط")
    rig = Rig(inline=False)     # بلا عامل: يمتلئ الطابور
    try:
        if not rig.start_server(): return check("الخادم يقوم", False)
        cookie, _ = rig.account("lm")
        s, lim, _ = req(rig.base, "/app/limits", cookie=cookie)
        check("الحدود معلنةٌ للمستخدم قبل أن يصطدم بها",
              s == 200 and lim.get("max_queued_per_user", 0) > 0, str(lim)[:70])
        codes = []
        for i in range(lim["max_queued_per_user"] + 3):
            pid = rig.project(cookie, ({"surah": 108, "ayah": 1, "to": 3},))
            codes.append(req(rig.base, "/app/export", {"project": pid}, cookie)[0])
        accepted = codes.count(202)
        check("طابور المستخدم لا يتجاوز حدّه",
              accepted <= lim["max_queued_per_user"], f"{accepted} · {codes}")
        check("وما زاد يُردّ بخطأٍ لا يُقبل صامتًا",
              any(400 <= x < 500 for x in codes), str(codes))
        used = req(rig.base, "/app/entitlements", cookie=cookie)[1]["used"]["cards"]
        check("والمردود لم تُخصم حصّته", used == accepted, f"{used} مقابل {accepted}")
        check("الخادم ما زال مستجيبًا والطابور ممتلئ",
              req(rig.base, "/healthz")[0] == 200)
    finally:
        rig.close()

# ═════════════════ التشغيل ═════════════════

TESTS = [t_worker_crash, t_server_restart, t_worker_restart, t_db_unavailable,
         t_bad_and_stuck, t_render_failure, t_missing_and_unauthorized,
         t_duplicate, t_limits]

if __name__ == "__main__":
    only = sys.argv[1:]
    for fn in TESTS:
        if only and not any(o in fn.__name__ for o in only): continue
        try:
            fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            check(f"{fn.__name__} أُنجز بلا انهيار", False, f"{type(e).__name__}: {e}")
    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: نجح {OK} · سقط {FAIL}")
        for n, d in FAILURES: print(f"  ✗ {n}  ← {d}")
        sys.exit(1)
    print(f"النتيجة: كل اختبارات الكسر نجحت ✓  ({OK} بندًا)")
