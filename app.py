#!/usr/bin/env python3
"""خادم تطبيق فلاح — طبقةُ HTTP وحدها.

    python3 app.py            # http://localhost:8080

طبقتان في خادمٍ واحد:
  • مسارات المحتوى (/quran/… /hadith/… /card /series …) تُمرَّر كما هي إلى
    `api.py` — لا تُنسخ منطقًا ولا تُعاد كتابته، فمصدر الحكم واحد.
  • مسارات التطبيق (/app/…) تمرّ على جدول `falah/routing.py`: وثيقةٌ ثم
    إذنٌ ثم معالِج. ولا يقرّر شيءٌ منها هنا.

وما بقي في هذا الملفّ هو HTTP بحتًا: قراءةُ الطلب، والكعكة، والترويسات،
وترجمةُ أخطاء النطاق إلى رموزِ حالة، وإقلاعُ الخادم. الاختيارُ في
`falah/routing.py`، والإذنُ في `falah/authz.py`، والعملُ في
`falah/app_routes.py`. واتّجاهُ الاعتماد ينزل ولا يصعد: لا تعرف طبقةٌ
تحتُ بشيءٍ ممّا فوقها.

الحماية: الجلسة في كعكة HttpOnly + SameSite=Strict، وكل طلبٍ يغيّر حالةً
يشترط ترويسة `X-FALAH: 1` — لا يرسلها نموذجٌ من موقعٍ آخر، فيسقط تزوير
الطلبات عبر المواقع. والردود بترويسات تمنع التضمين وشمّ الأنواع.
"""
import json, os, sqlite3, sys, time, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import api
from falah import store, auth, jobs as JB
from falah import authz as AZ, routing as RT, settings as CFG
from falah.web import Request

CFG.refresh()          # إعادةُ تحميل الوحدة تعيد قراءةَ البيئة

DB      = CFG.DB
UI      = CFG.UI
DEMO    = CFG.DEMO
COOKIE  = CFG.COOKIE
SECURE  = CFG.SECURE
ORIGIN  = CFG.ORIGIN
INVITE  = CFG.INVITE
ADMIN_KEY = CFG.ADMIN_KEY
TRUST_PROXY = CFG.TRUST_PROXY
MAX_BODY = CFG.MAX_BODY

# كل مسارات القراءة في api.py تُمرَّر كما هي. القائمة تُقابل ما أعلنه
# `falah/content_routes.py` — نقصانُ اسمٍ هنا يعني ٤٠٤ لمسارٍ موجود، وهو
# ما كشفه الفحص، ولذلك يُقارَن الاثنان في `tests.py` آليًّا.
CONTENT_PATHS = ("/health", "/sources", "/review", "/topics", "/quran", "/hadith",
                 "/enc", "/reciters", "/audio", "/card", "/verify", "/series",
                 "/options", "/chapters", "/chapter", "/templates", "/template")

class BodyTooLarge(Exception): pass

def body_json(h):
    """يقرأ جسم الطلب. الكبيرُ جدًّا يُرفض **صراحةً** لا صمتًا.

    كان يُرمى الجسمُ الكبير ويُعامَل الطلب كأنه فارغ، فيُقال للمستخدم «حقل
    ناقص» — وهو ليس ناقصًا بل مرفوضًا، فيبحث عن خطأٍ ليس عنده. وما جاوز
    ذلك بكثير كان يقطع الاتصال: الخادم يردّ ولا يستنزف الجسم، فينكسر
    الأنبوب على العميل ويرى «فشل الاتصال» لا رسالةً يفهمها.
    """
    n = int(h.headers.get("Content-Length") or 0)
    if n > MAX_BODY: raise BodyTooLarge(n)
    if n <= 0: return {}
    try:    return json.loads(h.rfile.read(n).decode("utf-8"))
    except Exception: return {}

class App(BaseHTTPRequestHandler):
    server_version = "FALAH"
    # `BaseHTTPRequestHandler` يُلحق `sys_version` بترويسة Server، فتصير
    # «FALAH Python/3.11.15» — أي أنها تقول لمن يبحث أيُّ ثغراتِ بايثون
    # تنطبق على هذا الخادم بالضبط. تُفرَّغ.
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # ــــــــــــــــــــ أدوات الردّ ــــــــــــــــــــ

    def _headers(self, ctype, length, extra=()):
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in extra: self.send_header(k, v)
        self.end_headers()

    def send_json(self, obj, code=200, extra=()):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._headers("application/json; charset=utf-8", len(b),
                      list(extra) + [("Cache-Control", "no-store")])
        self.wfile.write(b)

    def send_file(self, path, ctype, extra=None):
        try:    b = open(path, "rb").read()
        except FileNotFoundError: return self.send_json({"error": "غير موجود"}, 404)
        self.send_response(200)
        cache = ("public, max-age=604800"
                 if ctype.startswith(("font", "image")) else "no-cache")
        self._headers(ctype, len(b), (list(extra) if extra else []) + [("Cache-Control", cache)])
        self.wfile.write(b)

    def log_message(self, *a): pass      # سجلّ الوصول صامت — لا يُسجَّل كل طلب

    def log_error(self, fmt, *a):
        """العطب يُسجَّل حيث نراه، لا يُرسل إلى المستخدم.

        `BaseHTTPRequestHandler.log_error` يمرّ عبر `log_message` وقد أُسكت،
        فلو تُرك لبقي «سُجّل عندنا» دعوى بلا سجلّ. سطرٌ لكل عطب على
        stderr — تلتقطه الحاوية، ويكفي حتى تأتي المراقبة المهيكلة في P0-3.
        """
        try:
            print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] ERROR "
                  f"{self.client_address[0] if self.client_address else '-'} "
                  + (fmt % a if a else fmt), file=sys.stderr, flush=True)
        except Exception:
            pass

    # ــــــــــــــــــــ الجلسة ــــــــــــــــــــ

    def token(self):
        raw = self.headers.get("Cookie")
        if not raw: return None
        try:    return SimpleCookie(raw).get(COOKIE).value
        except Exception: return None

    def user(self, c):
        return auth.session_user(c, self.token())

    def set_cookie(self, tok, ttl=auth.SESSION_TTL):
        sec = "; Secure" if SECURE else ""
        return [("Set-Cookie",
                 f"{COOKIE}={tok}; Path=/; HttpOnly; SameSite=Strict{sec}; Max-Age={ttl}")]

    def clear_cookie(self):
        sec = "; Secure" if SECURE else ""
        return [("Set-Cookie", f"{COOKIE}=; Path=/; HttpOnly; SameSite=Strict{sec}; Max-Age=0")]

    def client_ip(self):
        """عنوانُ العميل الحقيقيّ — وهذا أدقّ ممّا يبدو.

        خلف وكيلٍ أماميّ (Caddy وأمثاله) يكون `client_address` عنوانَ
        الوكيل، فيصير حدُّ «لكل عنوان» حدًّا **للعالم كلّه معًا**: أوّلُ
        عشرين مسجِّلًا يمنعون البقيّة. وهذا خللُ إتاحةٍ لا حماية.

        والعلاج ليس الثقةَ بـ`X-Forwarded-For` دائمًا — فمن لا وكيلَ أمامه
        يستطيع أن يكتبها بيده فيتخطّى كلَّ حدّ. فتُقرأ **فقط** حين يُعلن
        المشغّل `FALAH_TRUST_PROXY=1`، أي حين يضمن أن وكيلَه يكتبها هو
        ويمحو ما جاء من العميل. إعلانٌ لا تخمين.
        """
        if TRUST_PROXY:
            # **الأخيرة لا الأولى.** الوكيل يُلحق عنوانَ العميل بما وجده، فلو
            # أرسل العميل `X-Forwarded-For: 1.2.3.4` صارت «1.2.3.4, <الحقيقيّ>»
            # — فأخذُ الأولى يأخذ ما كتبه المنتحِل بيده. الأخيرة هي التي
            # كتبها وكيلُنا. وCaddyfile يمحوها فوق ذلك احتياطًا مضاعفًا.
            xff = [x.strip() for x in
                   (self.headers.get("X-Forwarded-For") or "").split(",") if x.strip()]
            if xff: return xff[-1][:64]
        return self.client_address[0] if self.client_address else "-"

    def guard_csrf(self):
        """طبقتان: ترويسةٌ لا يرسلها نموذجٌ من موقعٍ آخر، ومصدرُ الطلب إن حُدِّد النطاق."""
        if self.headers.get("X-FALAH") != "1": return False
        if ORIGIN:
            o = (self.headers.get("Origin") or "").rstrip("/")
            if o and o != ORIGIN: return False
        return True

    # ــــــــــــــــــــ التمرير إلى طبقة المحتوى ــــــــــــــــــــ

    def proxy_content(self):
        """يُنفَّذ منطق api.py نفسه داخل هذه العملية — بلا شبكةٍ ولا نسخ."""
        holder = {}
        outer = self
        class Shim(api.H):
            def __init__(self):  self.path = outer.path; self.headers = outer.headers
            def _send(self, obj, code=200): holder["obj"], holder["code"] = obj, code
            def log_message(self, *a): pass
        api.H.do_GET(Shim())
        self.send_json(holder.get("obj", {"error": "لا ردّ"}), holder.get("code", 500))

    # ــــــــــــــــــــ المسارات ــــــــــــــــــــ

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html", "/reset", "/verify"):
            return self.send_file(UI, "text/html; charset=utf-8")
        if p == "/demo":              return self.send_file(DEMO, "text/html; charset=utf-8")
        if p == "/manifest.webmanifest":
            return self.send_file(os.path.join(HERE, "manifest.webmanifest"),
                                  "application/manifest+json; charset=utf-8")
        if p == "/sw.js":
            # نطاق عامل الخدمة كامل الموقع، ولا يُخزَّن هو نفسه
            return self.send_file(os.path.join(HERE, "sw.js"),
                                  "text/javascript; charset=utf-8",
                                  extra=[("Service-Worker-Allowed", "/")])
        if p.startswith("/icons/"):
            name = os.path.basename(p)
            if not name.endswith(".png"):
                return self.send_json({"error": "غير متاح"}, 404)
            return self.send_file(os.path.join(HERE, "icons", name), "image/png")
        if p.startswith("/fonts/"):
            name = os.path.basename(p)
            if not name.endswith((".ttf", ".woff2")):
                return self.send_json({"error": "غير متاح"}, 404)
            ct = "font/woff2" if name.endswith(".woff2") else "font/ttf"
            return self.send_file(os.path.join(HERE, "fonts", name), ct)
        if p == "/healthz":           return self.liveness()
        if p == "/readyz":            return self.readiness()
        if p.startswith("/app/"):     return self.app_request("GET", p, {})
        if any(p == x or p.startswith(x + "/") or p.startswith(x + "?") for x in CONTENT_PATHS):
            return self.proxy_content()
        self.send_json({"error": "مسار غير معروف"}, 404)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        if not p.startswith("/app/"):  return self.send_json({"error": "مسار غير معروف"}, 404)
        if not self.guard_csrf():      return self.send_json({"error": "طلب غير موثوق"}, 403)
        try:
            b = body_json(self)
        except BodyTooLarge as e:
            # ٤١٣ مع إغلاق الاتصال: الجسم لم يُقرأ، فلا يصحّ إبقاء الاتصال
            # مفتوحًا وفيه بقيّةٌ تُقرأ على أنها طلبٌ تالٍ.
            self.close_connection = True
            mb = MAX_BODY / 1_048_576
            return self.send_json({"error": f"الطلب أكبر من الحدّ ({mb:.1f} م.ب)",
                                   "limit_bytes": MAX_BODY, "got_bytes": int(str(e))}, 413,
                                  extra=[("Connection", "close")])
        return self.app_request("POST", p, b)

    # ــــــــــــــــــــ الحياة والجاهزية ــــــــــــــــــــ
    # الفرق ليس تجميلًا: `/healthz` يسأل «أحيَّةٌ العملية؟» فإن سقط أُعيد
    # تشغيل الحاوية. و`/readyz` يسأل «أتصلح لاستقبال طلب؟» فإن سقط سُحبت
    # من الموازِن ولم تُقتل. الخلط بينهما يعني إعادةَ تشغيلٍ لا تُصلح شيئًا،
    # أو حاويةً ميتةً تُرسَل إليها الطلبات.

    def liveness(self):
        """لا يلمس قاعدةً ولا قرصًا — يثبت أن الخيط يردّ فقط."""
        self.send_json({"live": True, "service": "falah-web"})

    def readiness(self):
        """يفحص ما يلزم لخدمة طلبٍ حقيقيّ: القاعدتان مقروءتان، والهجرات
        مطبَّقة. ولا يُسقِط الجاهزيةَ صمتُ العمّال — الخادم يستقبل ويضع في
        الطابور وإن لم يكن ثمّة عاملٌ الآن، والصمت يُبلَّغ لا يُخفى."""
        out, ok = {"ready": True, "service": "falah-web"}, True
        try:
            cc = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=3)
            out["content_db"] = cc.execute("SELECT COUNT(*) FROM surahs").fetchone()[0] == 114
            cc.close()
            ok &= out["content_db"]
        except Exception as e:
            # سببٌ ثابتٌ يفهمه المشغّل، لا نوعُ استثناءٍ يصف بنيةَ الشيفرة.
            # والتفصيل يُسجَّل عندنا كما في كل خطأٍ آخر.
            self.log_error("readyz content_db %s: %s", type(e).__name__, e)
            out["content_db"] = False; out["content_reason"] = "unreachable"; ok = False
        try:
            c = store.connect()
            try:
                c.execute("SELECT 1 FROM users LIMIT 1")
                out["app_db"] = True
                from falah import migrate as MG
                out["pending_migrations"] = [f"{m[0]:03d}:{m[1]}" for m in MG.pending(c)]
                q = JB.stats(c)
                out["queue"] = {"queued": q["queued"], "running": q["running"],
                                "oldest_wait": q["oldest_wait"],
                                "worker_silent_for": q["worker_silent_for"]}
                # عمّالٌ صامتون والطابور فيه عمل: تحذيرٌ يُقرأ، لا إسقاطُ جاهزية
                out["worker_warning"] = bool(
                    q["queued"] and (q["worker_silent_for"] is None
                                     or q["worker_silent_for"] > JB.STALE))
            finally:
                c.close()
        except Exception as e:
            self.log_error("readyz app_db %s: %s", type(e).__name__, e)
            out["app_db"] = False; out["app_reason"] = "unreachable"; ok = False
        out["ready"] = ok
        self.send_json(out, 200 if ok else 503)

    # ــــــــــــــــــــ مسارات التطبيق ــــــــــــــــــــ

    def subject(self, u):
        """الفاعلُ كما تراه طبقةُ الإذن. الأدوارُ تُشتقّ هنا لا تُقرأ من طلب.

        اليوم مصدرٌ واحد: المفتاحُ الإداريّ — كما كان `trusted` تمامًا.
        وفي P1.2 تُقرأ الأدوارُ من القاعدة داخل `authz.roles_for`، ولا
        يتغيّر هذا السطر ولا أيُّ معالِج.
        """
        ok = bool(ADMIN_KEY) and self.headers.get("X-FALAH-ADMIN") == ADMIN_KEY
        return AZ.subject_for(u["id"] if u else None, admin_key_ok=ok)

    def app_request(self, method, path, body):
        """دورةُ حياةِ الطلب كاملةً — وموضعُ ترجمةِ الأخطاء الوحيد.

        كانت هذه مكرّرةً مرّتين (`app_get` و`app_post`) بكتلتَي `except`
        متشابهتين لا متطابقتين. صارت واحدة: ما تعنيه رسالةٌ للمستخدم يُقرَّر
        هنا، ولا يُترجم خطأٌ في موضعين بطريقتين.
        """
        c = store.connect()
        rq = None
        try:
            u = self.user(c)
            rq = Request(path=path, method=method,
                         query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query),
                         body=body, c=c, root=HERE, content_db=DB,
                         user=u, subject=self.subject(u),
                         get_header=self.headers.get,
                         client_ip=self.client_ip(), session_token=self.token())
            r = RT.dispatch(rq)
            if r.file:
                return self.send_file(r.file[0], r.file[1])
            extra = list(r.headers)
            if r.cookie:
                extra += (self.set_cookie(r.cookie[1], r.cookie[2])
                          if r.cookie[0] == "set" else self.clear_cookie())
            self.send_json(r.body, r.code, extra)
        except AZ.Denied as e:
            # منعٌ صعد من طبقة النطاق لا من الجدول — يُترجَم بالجدول نفسه
            d = RT.denial_response(e.decision)
            self.send_json(d.body, d.code)
        except RT.DOMAIN_ERRORS as e:
            self.send_json({"error": str(e)}, 400)
        except KeyError as e:
            # الكتابةُ وحدها تقرأ حقولًا من الجسم، فرسالةُ «حقل ناقص» لها.
            # وفي القراءة يبقى `KeyError` عطبًا داخليًّا كما كان — لا تُوسَّع
            # رسالةُ خطأ على مسارٍ لم تكن له.
            if method == "POST":
                self.send_json({"error": "حقل ناقص: " + str(e)}, 400)
            else:
                self.log_error("internal %s: KeyError: %s", self.path, e)
                self.send_json({"error": "خطأ داخلي"}, 500)
        except (ValueError, TypeError) as e:
            # رقمٌ نصّيّ أو حقلٌ من نوعٍ غير متوقَّع: خطأُ طلبٍ لا عطبُ خادم
            self.log_error("bad request %s: %r", self.path, e)
            self.send_json({"error": "قيمةٌ غير صالحة في الطلب"}, 400)
        except Exception as e:
            # تفصيل العطب يُسجَّل عندنا ولا يُرسل: نصّ الاستثناء يصف بنيةَ
            # الشيفرة، وهو نصفُ خريطةٍ لمن يبحث عن ثغرة.
            self.log_error("internal %s: %s: %s", self.path, type(e).__name__, e)
            self.send_json({"error": "خطأ داخلي"}, 500)
        finally:
            if rq is not None: rq.close()
            c.close()

def check_config():
    """يتحقّق من الإعداد قبل الاستقبال. السقوط هنا خيرٌ من إعدادٍ صامتٍ خاطئ.

    المبدأ: **ما كان خطؤه يمسّ الأمان يُسقط الإقلاع في الإنتاج**، وما كان
    نقصًا في ميزةٍ يُطبع تحذيرًا ويمضي. خادمٌ يعمل بكعكةٍ غير مشفَّرة على
    HTTPS أسوأُ من خادمٍ لا يعمل، لأن أحدًا لن ينتبه.

    و«الإنتاج» يُعلَن بـ`FALAH_ENV=production` ولا يُخمَّن.
    """
    prod = os.environ.get("FALAH_ENV", "development").strip().lower() in ("production", "prod")
    fatal, warn = [], []

    if not os.path.exists(DB):
        fatal.append(f"قاعدة المحتوى غير موجودة ({os.path.basename(DB)}) — شغّل `make db`")
    for f in (UI, DEMO):
        if not os.path.exists(f):
            fatal.append(f"ملفُّ واجهةٍ مفقود: {os.path.basename(f)}")

    if prod:
        if not SECURE:
            fatal.append("FALAH_SECURE=1 لازمٌ في الإنتاج — وإلا سافرت الكعكة بلا تشفير")
        if not ORIGIN:
            fatal.append("FALAH_ORIGIN لازمٌ في الإنتاج — بلا حارسٍ لمصدر الطلب")
        elif not ORIGIN.startswith("https://"):
            fatal.append(f"FALAH_ORIGIN يجب أن يبدأ بـhttps:// (الآن: {ORIGIN})")
        if os.environ.get("FALAH_INLINE_WORKER", "1") != "0":
            warn.append("عاملٌ داخل الخادم في الإنتاج — يزاحم استقبال الطلبات. "
                        "اضبط FALAH_INLINE_WORKER=0 وشغّل worker.py")
        if ADMIN_KEY and len(ADMIN_KEY) < 24:
            fatal.append("FALAH_ADMIN_KEY قصيرٌ جدًّا — لا يقلّ عن ٢٤ محرفًا عشوائيًّا")
        if not ADMIN_KEY:
            warn.append("لا FALAH_ADMIN_KEY — منحُ الاشتراكات وإيصالاتُ المتجر معطَّلة")
        # المتاجر: إمّا مضبوطةٌ كاملةً أو معطَّلةٌ كاملةً — لا نصفَ إعداد
        ap = [k for k in ("FALAH_APPLE_BUNDLE_ID", "FALAH_APPLE_ISSUER_ID",
                          "FALAH_APPLE_KEY_ID", "FALAH_APPLE_KEY_P8")
              if os.environ.get(k)]
        if ap and not os.environ.get("FALAH_APPLE_ROOT_CA"):
            fatal.append("مفاتيح آبل مضبوطةٌ بلا FALAH_APPLE_ROOT_CA — "
                         "لا يُقبل إيصالٌ بلا تحقّقٍ من سلسلته")
    else:
        if SECURE and not ORIGIN:
            warn.append("FALAH_SECURE=1 خارج HTTPS يمنع الكعكة من الوصول")

    if fatal:
        print("⛔ إعدادٌ ناقصٌ أو خطِر — لن يُقلع الخادم:", file=sys.stderr)
        for m in fatal: print(f"   • {m}", file=sys.stderr)
        print("   راجع .env.example", file=sys.stderr)
        raise SystemExit(78)                      # EX_CONFIG
    for m in warn: print(f"⚠ {m}", flush=True)
    return True

def start_inline_worker(n=1):
    """عاملٌ داخل عملية الخادم — ليعمل `python3 app.py` وحده كما كان.
    في الإنتاج يُطفأ (`FALAH_INLINE_WORKER=0`) ويُشغَّل `worker.py` منفصلًا،
    فيستقلّ التصييرُ الثقيل بموارده ولا يزاحم استقبالَ الطلبات."""
    import threading, time
    def loop(name):
        last = 0.0
        while True:
            if time.time() - last > 60:
                c = store.connect()
                try:    JB.reap(c)
                except Exception: pass
                finally: c.close(); last = time.time()
            try:
                if JB.run_once(DB, HERE, worker=name) is None: time.sleep(1.0)
            except Exception: time.sleep(1.0)
    for i in range(max(1, n)):
        threading.Thread(target=loop, args=(f"inline#{i}",), daemon=True).start()

class Server(ThreadingHTTPServer):
    """طابورُ إصغاءٍ يحتمل الدفعة.

    قياسٌ حقيقيّ: عند ١٠٠ طلبٍ متزامن سقط **٤٨ اتصالًا قبل أن يُقرأ**، لأن
    `request_queue_size` في `socketserver` خمسةٌ افتراضًا — أي أن ما زاد على
    خمسةِ اتصالاتٍ منتظرةٍ في لحظةِ الذروة يُرفض في طبقة النظام، لا في
    الشيفرة. والمستخدم يرى «تعذّر الاتصال» لا رسالةً مفهومة.

    الرفعُ إلى ١٢٨ لا يزيد عملًا ولا ذاكرةً — يزيد صبرَ الطابور فقط. وخلف
    وكيلٍ أماميّ (Caddy) يقلّ أثرُه، لكن الخادم لا ينبغي أن يعتمد على وجوده.
    """
    request_queue_size = int(os.environ.get("FALAH_LISTEN_BACKLOG", 128))
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    check_config()                  # يسقط قبل الاستقبال لا بعده
    store.init()                    # يُنشئ app.db إن لم تكن موجودة
    port = int(os.environ.get("PORT", 8080))
    inline = os.environ.get("FALAH_INLINE_WORKER", "1") != "0"
    if inline: start_inline_worker(int(os.environ.get("FALAH_WORKERS", 1)))
    print(f"تطبيق فلاح → http://localhost:{port}/"
          f"{'  · كعكة آمنة' if SECURE else ''}{('  · النطاق ' + ORIGIN) if ORIGIN else ''}"
          f"{'  · عاملٌ داخليّ' if inline else '  · بلا عاملٍ داخليّ (شغّل worker.py)'}",
          flush=True)
    Server(("0.0.0.0", port), App).serve_forever()
