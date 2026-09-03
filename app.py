#!/usr/bin/env python3
"""خادم تطبيق فلاح — الواجهة والحساب والمشاريع فوق طبقة المحتوى.

    python3 app.py            # http://localhost:8080

طبقتان في خادمٍ واحد:
  • مسارات المحتوى (/quran/… /hadith/… /card /series …) تُمرَّر كما هي إلى
    `api.py` — لا تُنسخ منطقًا ولا تُعاد كتابته، فمصدر الحكم واحد.
  • مسارات التطبيق (/app/…) محميّةٌ بجلسةٍ، تكتب في `app.db` وحدها.

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
from falah import store, auth, projects as P, billing, referrals as REF, jobs as JB

DB      = os.path.join(HERE, "falah.db")
UI      = os.path.join(HERE, "falah-app.html")      # مساحة العمل
DEMO    = os.path.join(HERE, "falah-agent.html")     # النموذج التفاعلي (بلا حساب)
COOKIE  = "falah_sid"
SECURE  = os.environ.get("FALAH_SECURE") == "1"      # خلف HTTPS: كعكةٌ لا تسافر إلا مشفّرة
ORIGIN  = os.environ.get("FALAH_ORIGIN", "").rstrip("/")   # نطاق الإنتاج، إن حُدِّد
INVITE  = os.environ.get("FALAH_INVITE", "").strip()  # إطلاقٌ مغلق: لا حساب إلا برمز دعوة
ADMIN_KEY = os.environ.get("FALAH_ADMIN_KEY", "").strip()   # منح الاشتراك وإيصالات المتجر
# لا تُقرأ X-Forwarded-For إلا بإعلانٍ صريح — انظر `client_ip`
TRUST_PROXY = os.environ.get("FALAH_TRUST_PROXY") == "1"
# كل مسارات القراءة في api.py تُمرَّر كما هي. القائمة تُقابل ما في `api.H.do_GET`
# حرفًا بحرف — نقصانُ اسمٍ هنا يعني ٤٠٤ لمسارٍ موجود، وهو ما كشفه الفحص.
CONTENT_PATHS = ("/health", "/sources", "/review", "/topics", "/quran", "/hadith",
                 "/enc", "/reciters", "/audio", "/card", "/verify", "/series",
                 "/options", "/chapters", "/chapter", "/templates", "/template")

MAX_BODY = int(os.environ.get("FALAH_MAX_BODY", 1_000_000))

# ═══════════ حدّ المعدّل على المكلف ═══════════
# كان الحدُّ على الدخول وحده. والتصدير والمقطع أثقلُ منه بكثير — بطاقةٌ
# ثلاثُ ثوانٍ ومقطعٌ ستٌّ وعشرون — فمن يستطيع بدءَ ألفٍ في الساعة يخنق
# الخدمة على غيره ولو لم يتجاوز حصّته الشهرية.
#
# **وما يُعدّ هو العملُ المقبول لا الطلب.** مئةُ نقرةٍ على الزرّ نفسه تصير
# مهمّةً واحدة (بفضل مفتاح التفرّد)، فتُحسب واحدة. بهذا يمنع الحدُّ الإساءة
# ولا يكسر تزامنًا مشروعًا — وهو الفرق بين حدٍّ يحمي وحدٍّ يُزعج.
def _lim(name, default, window):
    return (int(os.environ.get(f"FALAH_RATE_{name}", default)), window)

RATE = {
    "export":   _lim("EXPORT",   30, 3600),    # ثلاثون تصديرًا في الساعة
    "video":    _lim("VIDEO",    15, 3600),
    "agent":    _lim("AGENT",   300, 3600),    # سؤالٌ وجوابٌ — أخفّ بكثير
    "register": _lim("REGISTER", 20, 3600),    # لكل عنوان — والعناوين تُشارَك
    "file":     _lim("FILE",    600, 3600),
}

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

    def rate_ok(self, c, kind, who):
        """يعيد True إن بقي في الحدّ. ولا يزيد العدّاد — الزيادة عند القبول."""
        lim, win = RATE[kind]
        return not auth.throttled(c, f"rate:{kind}:{who}", limit=lim, window=win)

    def rate_bump(self, c, kind, who):
        auth.bump(c, f"rate:{kind}:{who}", window=RATE[kind][1])

    def too_many(self, kind):
        lim, win = RATE[kind]
        mins = win // 60
        self.send_json({"error": f"تجاوزتَ الحدّ: {lim} في {mins} دقيقة. "
                                 f"انتظر قليلًا ثم أعد المحاولة.",
                        "limit": lim, "window_seconds": win}, 429,
                       extra=[("Retry-After", str(win))])
        return None

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
        if p.startswith("/app/"):     return self.app_get(p)
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
        return self.app_post(p, b)

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

    # ــ قراءة ــ

    def app_get(self, p):
        c = store.connect()
        try:
            if p == "/app/config":
                return self.send_json({"invite_required": bool(INVITE),
                                       "origin": ORIGIN or None})

            if p == "/app/plans":
                return self.send_json(billing.catalogue())

            if p == "/app/me":
                u = self.user(c)
                return self.send_json({"user": u} if u else {"user": None}, 200)

            u = self.user(c)
            if not u: return self.send_json({"error": "يلزم تسجيل الدخول"}, 401)

            if p == "/app/entitlements":
                return self.send_json(billing.entitlements(c, u["id"]))

            if p == "/app/referrals":
                return self.send_json(REF.summary(c, u["id"]))

            if p == "/app/projects":
                return self.send_json({"projects": P.listing(c, u["id"])})

            if p.startswith("/app/projects/"):
                pid = int(p.rsplit("/", 1)[-1])
                content = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
                content.row_factory = sqlite3.Row
                try:    return self.send_json(P.open_project(c, content, u["id"], pid))
                finally: content.close()

            if p == "/app/file":
                if not self.rate_ok(c, "file", u["id"]): return self.too_many("file")
                self.rate_bump(c, "file", u["id"]); c.commit()
                rel = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("p", [""])[0]
                return self.send_export_file(c, u, rel)

            if p == "/app/limits":
                return self.send_json(JB.limits())

            if p == "/app/jobs":
                return self.send_json({"jobs": JB.listing(c, u["id"]),
                                       "queue": JB.stats(c), "limits": JB.limits()})

            if p.startswith("/app/jobs/"):
                # الاستطلاع: المتصفّح يسأل عن مهمّته حتى تنتهي
                return self.send_json({"job": JB.get(c, u["id"], int(p.rsplit("/", 1)[-1]))})

            if p == "/app/exports":
                rows = c.execute("""SELECT * FROM exports WHERE user_id=?
                                    ORDER BY created_at DESC LIMIT 50""", (u["id"],)).fetchall()
                return self.send_json({"exports": [dict(r) for r in rows]})

            self.send_json({"error": "مسار غير معروف"}, 404)
        except (P.ProjectError, auth.AuthError, billing.BillingError,
                REF.ReferralError, JB.JobError) as e:
            self.send_json({"error": str(e)}, 400)
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
            c.close()

    # ــ كتابة ــ

    def app_post(self, p, b):
        c = store.connect()
        content = None
        try:
            agent = self.headers.get("User-Agent", "")

            if p == "/app/register":
                ip = self.client_ip()
                if not self.rate_ok(c, "register", ip): return self.too_many("register")
                self.rate_bump(c, "register", ip); c.commit()
                if INVITE and (b.get("invite") or "").strip() != INVITE:
                    store.log(c, None, "invite_rejected", (b.get("email") or "")[:80]); c.commit()
                    return self.send_json({"error": "رمز الدعوة غير صحيح"}, 403)
                uid = auth.register(c, b.get("email"), b.get("password"),
                                    b.get("name"), b.get("watermark"))
                ref_note = None
                if (b.get("ref") or "").strip():
                    try:    REF.attach(c, uid, b["ref"])
                    except REF.ReferralError as e: ref_note = str(e)
                try:    auth.request_verify(c, uid)
                except Exception: pass
                tok, u = auth.login(c, b.get("email"), b.get("password"), agent)
                return self.send_json({"user": u, "referral_note": ref_note,
                                       "entitlements": billing.entitlements(c, uid)},
                                      201, self.set_cookie(tok))

            if p == "/app/password/forgot":
                # الردّ واحدٌ سواءٌ وُجد البريد أو لم يوجد
                r = auth.request_reset(c, b.get("email"))
                sent = (r.get("mail") or {}).get("sent")
                return self.send_json({"ok": True, "mail_sent": bool(sent),
                                       "note": None if sent else
                                       "إن كان البريد مسجَّلًا فالرسالة في طريقها"})

            if p == "/app/password/reset":
                uid = auth.reset_password(c, b.get("token"), b.get("password"))
                return self.send_json({"ok": True}, 200, self.clear_cookie())

            if p == "/app/verify/confirm":
                auth.verify_email(c, b.get("token"))
                return self.send_json({"ok": True})

            if p == "/app/login":
                tok, u = auth.login(c, b.get("email"), b.get("password"), agent)
                return self.send_json({"user": u}, 200, self.set_cookie(tok))

            if p == "/app/logout":
                auth.logout(c, self.token())
                return self.send_json({"ok": True}, 200, self.clear_cookie())

            u = self.user(c)
            if not u: return self.send_json({"error": "يلزم تسجيل الدخول"}, 401)

            if p == "/app/account/delete":
                # يُشترط التصريح بكلمة «حذف» حتى لا يقع الحذف بنقرةٍ عابرة
                if (b.get("confirm") or "").strip() != "حذف":
                    return self.send_json({"error": "اكتب «حذف» للتأكيد"}, 400)
                gone = auth.delete_account(c, u["id"], export_dir=HERE)
                return self.send_json({"ok": True, **gone}, 200, self.clear_cookie())

            if p == "/app/subscription/cancel":
                return self.send_json({"subscription": billing.cancel(c, u["id"]),
                                       "entitlements": billing.entitlements(c, u["id"])})

            if p == "/app/subscription/store-event":
                # الجهاز يرسل رمز الشراء فقط، والخادم يسأل المتجر عنه ويشتقّ
                # الحقّ من ردّه — فلا يُمنح شيءٌ بحمولةٍ قادمةٍ من جهاز.
                trusted = bool(ADMIN_KEY) and self.headers.get("X-FALAH-ADMIN") == ADMIN_KEY
                try:
                    sub = billing.apply_store_event(c, u["id"], b.get("provider"),
                                                    b.get("event") or {}, verified=trusted)
                except billing.BillingError as e:
                    return self.send_json({"error": str(e)}, 402)
                return self.send_json({"subscription": sub,
                                       "entitlements": billing.entitlements(c, u["id"])})

            if p == "/app/subscription/grant":
                # منحةٌ إدارية: تجارب، تعويضات، دعوات. لا تُفتح للعامّة.
                if not ADMIN_KEY or self.headers.get("X-FALAH-ADMIN") != ADMIN_KEY:
                    return self.send_json({"error": "غير مصرَّح"}, 403)
                sub = billing.grant(c, int(b.get("user") or u["id"]), b.get("plan"),
                                    days=int(b.get("days") or 30), provider="grant",
                                    note=b.get("note"))
                return self.send_json({"subscription": sub})

            if p == "/app/verify/request":
                r = auth.request_verify(c, u["id"])
                return self.send_json({"ok": True, "already": r.get("already", False),
                                       "mail_sent": bool((r.get("mail") or {}).get("sent"))})

            if p == "/app/profile":
                auth.update_profile(c, u["id"], b.get("name"), b.get("watermark"))
                return self.send_json({"user": auth.session_user(c, self.token())})

            if p == "/app/password":
                auth.change_password(c, u["id"], b.get("old"), b.get("new"))
                return self.send_json({"ok": True, "note": "أُنهيت كل الجلسات"},
                                      200, self.clear_cookie())

            if p == "/app/projects/create":
                billing.check(c, u["id"], "projects")
                pid = P.create(c, u["id"], b.get("title"), b.get("kind", "series"),
                               b.get("skin", "parch"), b.get("ratio", "square"),
                               b.get("watermark") or u["watermark"])
                return self.send_json({"id": pid}, 201)

            if p == "/app/projects/update":
                P.update(c, u["id"], int(b["id"]), **{k: b.get(k) for k in
                         ("title", "kind", "skin", "ratio", "watermark", "note", "archived")})
                return self.send_json({"ok": True})

            if p == "/app/projects/delete":
                P.delete(c, u["id"], int(b["id"]))
                return self.send_json({"ok": True})

            content = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
            content.row_factory = sqlite3.Row

            if p == "/app/items/add":
                iid = P.add_item(c, content, u["id"], int(b["project"]),
                                 b["kind"], b["ref"])
                return self.send_json({"id": iid}, 201)

            if p == "/app/items/remove":
                P.remove_item(c, u["id"], int(b["project"]), int(b["id"]))
                return self.send_json({"ok": True})

            if p == "/app/items/reorder":
                P.reorder(c, u["id"], int(b["project"]), [int(x) for x in b["order"]])
                return self.send_json({"ok": True})

            if p == "/app/export":
                return self.export(c, content, u, int(b["project"]))

            if p == "/app/agent":
                if not self.rate_ok(c, "agent", u["id"]): return self.too_many("agent")
                self.rate_bump(c, "agent", u["id"]); c.commit()
                from falah import agent as AG
                ans = b.get("answers") or {}
                ans = AG.sanitize(ans, DB)
                q = AG.next_question(ans, DB, u["watermark"])
                prog = AG.progress(ans, DB)
                if q: return self.send_json({"done": False, "question": q,
                                             "answers": ans, "progress": prog,
                                             "preview": AG.plan(ans, DB) if ans.get("source_kind") and
                                                        AG.selection(ans, DB) else None})
                try:    return self.send_json({"done": True, "plan": AG.plan(ans, DB),
                                               "answers": ans, "progress": prog})
                except SystemExit as e: return self.send_json({"error": str(e)}, 404)

            if p == "/app/agent/build":
                from falah import agent as AG
                ans = b.get("answers") or {}
                if AG.next_question(ans, DB, u["watermark"]):
                    return self.send_json({"error": "الإجابات غير مكتملة"}, 400)
                pl  = AG.plan(ans, DB)
                st  = pl["style"]
                pid = P.create(c, u["id"], pl["title"], "series",
                               st["skin"], st["ratio"],
                               st["watermark"] or u["watermark"])
                added = 0
                for card in pl["cards"]:
                    try:
                        P.add_item(c, content, u["id"], pid, card["kind"], card["ref"]); added += 1
                    except P.ProjectError:
                        pass          # ما لم يجتز الفحص لحظة الإضافة يُترك، ولا يُستبدل
                store.log(c, u["id"], "agent_project", f"{pid}:{added}")
                c.commit()
                return self.send_json({"project": pid, "added": added}, 201)

            if p == "/app/video":
                return self.video(c, content, u, int(b["project"]), int(b["item"]),
                                  b.get("reciter", "alafasy"))

            if p == "/app/jobs/cancel":
                return self.send_json({"job": JB.cancel(c, u["id"], int(b["id"]))})

            if p == "/app/items/accept-drift":
                P.accept_drift(c, content, u["id"], int(b["project"]), int(b["id"]))
                return self.send_json({"ok": True})

            self.send_json({"error": "مسار غير معروف"}, 404)
        except (P.ProjectError, auth.AuthError, billing.BillingError,
                REF.ReferralError, JB.JobError) as e:
            self.send_json({"error": str(e)}, 400)
        except KeyError as e:
            self.send_json({"error": "حقل ناقص: " + str(e)}, 400)
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
            if content: content.close()
            c.close()

    # ــــــــــــــــــــ التصدير ــــــــــــــــــــ

    def export(self, c, content, u, pid):
        """يضع تصديرَ المشروع في الطابور ويردّ فورًا. الشروط تُفحص هنا —
        قبل الوضع — حتى يعرف المستخدمُ الخطأَ في طلبه لا بعد دقيقة."""
        st = P.open_project(c, content, u["id"], pid)
        if not st["items"]:   return self.send_json({"error": "المشروع فارغ"}, 400)
        if not st["exportable"]:
            return self.send_json({"error": "فيه عناصر محجوبة أو منحرفة — راجعها أولًا",
                                   "blocked": st["blocked"], "drift": st["drift"]}, 409)
        proj = st["project"]
        n = len(st["items"])
        # الحصّة تُفحص ثم تُحجز عند الوضع — وإلا أغرق أحدٌ الطابورَ بما يتجاوز
        # خطّته قبل أن يُصيَّر منه شيء. وتُردّ كاملةً إن فشل العمل.
        billing.check(c, u["id"], "cards", n)
        billing.require(c, u["id"], "ratios", proj["ratio"], what="هذا المقاس")
        billing.require(c, u["id"], "designs", proj["skin"], what="هذا التصميم")
        # التفرّد يُفحص قبل حجز الحصّة: نقرتان لا تستهلكان بطاقاتٍ مرّتين
        dup = JB.live_for(c, JB.idem_key(u["id"], "export", {"project": pid}))
        if dup:
            return self.send_json({"job": JB.view(dup), "duplicate": True,
                                   "note": "هذا التصدير في الطابور بالفعل"}, 202)
        if not self.rate_ok(c, "export", u["id"]): return self.too_many("export")
        billing.consume(c, u["id"], "cards", n)
        try:
            job = JB.enqueue(c, u["id"], "export", {"project": pid}, {"cards": n})
        except JB.JobConflict as e:
            # سباقٌ بين الفحص أعلاه والإدراج: طلبان متزامنان بالبصمة نفسها.
            # الفهرس الفريد حسمه، فيُردّ الثاني بالمهمّة القائمة — لا بخطأ.
            billing.release(c, u["id"], "cards", n)
            return self.send_json({**json.loads(str(e)),
                                   "note": "هذا التصدير في الطابور بالفعل"}, 202)
        except JB.JobError:
            billing.release(c, u["id"], "cards", n)     # لم تدخل الطابور فلا تُحاسَب
            raise
        self.rate_bump(c, "export", u["id"])      # عند القبول لا عند الطلب
        store.log(c, u["id"], "export_queued", f"{pid}:{job['id']}"); c.commit()
        self.send_json({"job": job, "cards": n,
                        "note": "التصدير في الطابور — تابِع حالته"}, 202)

    def video(self, c, content, u, pid, item_id, reciter):
        """مقطعٌ من عنصرٍ قرآنيّ في المشروع: البطاقة نفسها + تلاوة قارئٍ مسجَّل.
        التلاوة رواية، فلا تُركَّب على نصٍّ لم يجتز الفحص، ولا على غير القرآن.
        يوضع في الطابور — ٢٦ ثانية لا تُنتظر داخل طلب."""
        st = P.open_project(c, content, u["id"], pid)
        it = next((x for x in st["items"] if x["id"] == item_id), None)
        if not it:                 return self.send_json({"error": "العنصر غير موجود"}, 404)
        if it["kind"] != "quran":  return self.send_json({"error": "المقطع للآيات فقط"}, 400)
        if it["state"] != "ok":
            return self.send_json({"error": "العنصر يحتاج مراجعة: " + (it.get("why") or "")}, 409)
        r = content.execute("SELECT code FROM reciters WHERE code=?", (reciter,)).fetchone()
        if not r:                  return self.send_json({"error": "القارئ غير مسجَّل"}, 400)
        billing.check(c, u["id"], "videos")
        billing.require(c, u["id"], "ratios", st["project"]["ratio"], what="هذا المقاس")
        pay = {"project": pid, "item": item_id, "reciter": reciter}
        dup = JB.live_for(c, JB.idem_key(u["id"], "video", pay))
        if dup:
            return self.send_json({"job": JB.view(dup), "duplicate": True,
                                   "note": "هذا المقطع في الطابور بالفعل"}, 202)
        if not self.rate_ok(c, "video", u["id"]): return self.too_many("video")
        billing.consume(c, u["id"], "videos")
        try:
            job = JB.enqueue(c, u["id"], "video", pay, {"videos": 1})
        except JB.JobConflict as e:
            billing.release(c, u["id"], "videos", 1)
            return self.send_json({**json.loads(str(e)),
                                   "note": "هذا المقطع في الطابور بالفعل"}, 202)
        except JB.JobError:
            billing.release(c, u["id"], "videos", 1)
            raise
        self.rate_bump(c, "video", u["id"])
        store.log(c, u["id"], "video_queued", f"{pid}:{item_id}:{job['id']}"); c.commit()  # noqa
        self.send_json({"job": job, "note": "المقطع في الطابور — تابِع حالته"}, 202)

    def send_export_file(self, c, u, rel):
        """لا يُقدَّم إلا ملفٌ داخل مجلّد صاحب الجلسة — لا مسارَ يخرج منه."""
        root = os.path.realpath(os.path.join(HERE, "exports", str(u["id"])))
        full = os.path.realpath(os.path.join(HERE, rel))
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            return self.send_json({"error": "ملف غير متاح"}, 404)
        types = {".png": "image/png", ".mp4": "video/mp4", ".txt": "text/plain; charset=utf-8"}
        self.send_file(full, types.get(os.path.splitext(full)[1], "application/octet-stream"))

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
