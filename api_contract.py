#!/usr/bin/env python3
"""عقد الـAPI — يُستخرج من الشيفرة لا يُكتب بجانبها.

    python3 api_contract.py            # يطبع الجدول
    python3 api_contract.py --check    # يسقط إن اختلف عن API.md

وثيقةٌ تُكتب باليد تتقادم بصمت. هذه تُقرأ من `app.py` و`api.py` كل مرّة،
فإن أُضيف مسارٌ ولم يُوثَّق ظهر، وإن حُذف مسارٌ ووُثِّق ظهر كذلك. ويقارن
أيضًا ما تناديه الواجهة بما يقدّمه الخادم — فلا تنادي شاشةٌ مسارًا لا وجود له.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))

def read(name):
    return open(os.path.join(HERE, name), encoding="utf-8").read()

def content_routes():
    """مسارات القراءة — من إعلان `falah/content_routes.py` لا من نصّ الشيفرة.

    كانت تُستخرج بتعبيرٍ نمطيّ من `api.py`: يقرأ `p == "…"` ويأمل ألّا يفوته
    شيء. وكان ذلك أضعفَ ممّا يبدو — مسارٌ يُكتب بصيغةٍ أخرى يغيب عن العقد
    بلا صوت. صارت المساراتُ بياناتٍ تُقرأ، فما في الجدول هو ما في العقد.
    """
    from falah import content_routes as CR
    return sorted(set(CR.declared()))

def app_routes():
    """مسارات /app من جدول `falah/routing.py`، مفصولةً قراءةً وكتابة."""
    from falah import routing as RT
    def grab(method):
        return sorted({r.path + ("{id}" if r.kind == "param" else "")
                       for r in RT.TABLE[method]})
    return grab("GET"), grab("POST")

# مَن يجوز له، وما يدخل، وما يخرج، وبماذا يُردّ. مكتوبٌ هنا لأنه لا يُستخرج
# من الشيفرة — والفحص يتحقّق أن كل مسارٍ قائمٍ له سطر.
SPEC = {
  # المسار: (الطريقة، الصلاحية، المدخل، المخرج، الأخطاء)
  "/healthz":  ("GET",  "عامّ", "—", "{live}", "—"),
  "/readyz":   ("GET",  "عامّ", "—", "{ready, content_db, app_db, queue, pending_migrations}",
                "503 غير جاهز"),
  "/health":   ("GET",  "عامّ", "—", "إحصاء القاعدة", "—"),
  "/sources":  ("GET",  "عامّ", "—", "المصادر وحال تراخيصها", "—"),
  "/review":   ("GET",  "عامّ", "kind", "المحجوب وسببه", "—"),
  "/topics":   ("GET",  "عامّ", "—", "فهرس الموضوعات", "—"),
  "/topics/{id}": ("GET", "عامّ", "kind, limit", "مقترحات الموضوع", "404"),
  "/quran/search": ("GET", "عامّ", "q, card_only", "نتائج", "400 استعلامٌ فارغ"),
  "/quran/ayah": ("GET", "عامّ", "surah, ayah, to, tafsir, translation",
                  "الآية بسياقها", "400 · 404"),
  "/hadith":   ("GET",  "عامّ", "book, no", "الحديث", "400 · 404"),
  "/hadith/search": ("GET", "عامّ", "q, card_only", "نتائج", "400"),
  "/enc":      ("GET",  "عامّ", "id", "من الموسوعة", "404"),
  "/enc/search": ("GET", "عامّ", "q", "نتائج", "400"),
  "/card":     ("GET",  "عامّ", "kind وموضع النصّ", "البطاقة بعد ٢٥ فحصًا",
                "400 · 404 · محجوبٌ بسببه"),
  "/verify":   ("GET",  "عامّ", "text, surah, ayah", "نتيجة الفحوص", "400"),
  "/reciters": ("GET",  "عامّ", "—", "القرّاء برواياتهم", "—"),
  "/audio":    ("GET",  "عامّ", "surah, ayah, reciter", "روابط التلاوة", "400"),
  "/options":  ("GET",  "عامّ", "—", "مادّة الوكيل", "—"),
  "/chapters": ("GET",  "عامّ", "book", "الأبواب", "400"),
  "/chapter/hadiths": ("GET", "عامّ", "book, chapter", "أحاديث الباب", "400"),
  "/templates": ("GET", "عامّ", "kind, limit", "قوالب جاهزة", "400"),
  "/template": ("GET",  "عامّ", "ref", "قالبٌ واحد", "404"),
  "/series":   ("GET",  "عامّ", "topic, count", "سلسلةٌ مقترحة", "400"),

  "/app/config":       ("GET",  "عامّ", "—", "{invite_required, origin}", "—"),
  "/app/plans":        ("GET",  "عامّ", "—", "الخطط وما لا يُباع", "—"),
  "/app/me":           ("GET",  "عامّ", "الكعكة",
                        "{user} أو {user:null} — و`user.role` **قراءةٌ فقط**", "—"),
  "/app/entitlements": ("GET",  "جلسة", "—", "الخطّة والحدود والمستهلَك", "401"),
  "/app/limits":       ("GET",  "جلسة", "—", "حدود الطابور والموارد", "401"),
  "/app/referrals":    ("GET",  "جلسة", "—", "رمز الإحالة وحصادها", "401"),
  "/app/projects":     ("GET",  "جلسة", "—", "مشاريع صاحب الجلسة", "401"),
  "/app/projects/{id}": ("GET", "جلسة+ملكية", "—", "المشروع بعناصره مفحوصةً الآن",
                         "401 · 400 ليس مشروعك"),
  "/app/jobs":         ("GET",  "جلسة", "—", "مهامّه وإحصاء الطابور والحدود", "401"),
  "/app/jobs/{id}":    ("GET",  "جلسة+ملكية", "—",
                        "{state, progress, step, result, error, retry_after}",
                        "401 · 400 ليست مهمّتك"),
  "/app/exports":      ("GET",  "جلسة", "—", "آخر ٥٠ تصديرًا", "401"),
  "/app/file":         ("GET",  "جلسة+ملكية", "p", "الملفّ نفسه",
                        "401 · 404 خارج مجلّدك"),

  "/app/register":  ("POST", "عامّ+CSRF", "email, password, name, watermark, invite, ref",
                     "201 {user, entitlements}", "400 · 403 دعوة"),
  "/app/login":     ("POST", "عامّ+CSRF", "email, password", "{user} + كعكة",
                     "400 بيانات خاطئة · محاولاتٌ كثيرة"),
  "/app/logout":    ("POST", "جلسة+CSRF", "—", "{ok}", "—"),
  "/app/password":  ("POST", "جلسة+CSRF", "old, new", "{ok} + إنهاء الجلسات", "400"),
  "/app/password/forgot": ("POST", "عامّ+CSRF", "email", "{ok} (لا يكشف وجود الحساب)", "—"),
  "/app/password/reset":  ("POST", "رمز+CSRF", "token, password", "{ok}", "400 رمزٌ منتهٍ"),
  "/app/verify/request":  ("POST", "جلسة+CSRF", "—", "{ok}", "401"),
  "/app/verify/confirm":  ("POST", "رمز+CSRF", "token", "{ok}", "400"),
  "/app/profile":   ("POST", "جلسة+CSRF", "name, watermark", "{user}", "401"),
  "/app/account/delete": ("POST", "جلسة+CSRF", "confirm='حذف'", "{ok, gone}",
                          "400 بلا تأكيد"),
  "/app/projects/create": ("POST", "جلسة+CSRF", "title, kind, skin, ratio, watermark",
                           "201 {id}", "400 حصّة المشاريع"),
  "/app/projects/update": ("POST", "جلسة+ملكية", "id + الحقول", "{ok}", "400"),
  "/app/projects/delete": ("POST", "جلسة+ملكية", "id", "{ok}", "400"),
  "/app/items/add":       ("POST", "جلسة+ملكية", "project, kind, ref", "201 {id}",
                           "400 محجوبٌ أو مكرَّر"),
  "/app/items/remove":    ("POST", "جلسة+ملكية", "project, id", "{ok}", "400"),
  "/app/items/reorder":   ("POST", "جلسة+ملكية", "project, order[]", "{ok}", "400"),
  "/app/items/accept-drift": ("POST", "جلسة+ملكية", "project, id", "{ok}", "400"),
  "/app/export":  ("POST", "جلسة+ملكية", "project",
                   "**202** {job, cards} — ويعيد المهمّة القائمة إن كان الطلب مكرَّرًا",
                   "400 فارغ/حدّ · 409 محجوب أو منحرف"),
  "/app/video":   ("POST", "جلسة+ملكية", "project, item, reciter",
                   "**202** {job}", "400 · 404 · 409"),
  "/app/jobs/cancel": ("POST", "جلسة+ملكية", "id", "{job}", "400 بدأت فلا تُلغى"),
  "/app/agent":       ("POST", "جلسة+CSRF", "answers", "السؤال التالي أو الخطّة", "404"),
  "/app/agent/build": ("POST", "جلسة+CSRF", "answers", "201 {project, added}", "400"),
  "/app/subscription/cancel": ("POST", "جلسة+CSRF", "—", "{subscription, entitlements}", "400"),
  "/app/subscription/store-event": ("POST", "جلسة+CSRF", "provider, event",
                                    "{subscription} بعد سؤال المتجر",
                                    "**402** إيصالٌ لم يثبت"),
  "/app/subscription/grant": ("POST", "صلاحية subscription.grant", "user, plan, days, note",
                              "{subscription}", "401 · 403"),

  # ═══ الإدارة — أُضيفت في P1.2. كلُّها بصلاحياتٍ مسمّاة لا بأسماء أدوار ═══
  "/app/admin/users":  ("GET", "صلاحية user.list", "limit, offset, role",
                        "{total, users[]} — أعمدةٌ مسمّاة بلا اشتقاقِ كلمةِ مرورٍ ولا ملح",
                        "401 · 403"),
  "/app/admin/users/{id}": ("GET", "صلاحية user.read", "—", "{user}", "401 · 403 · 404"),
  "/app/admin/users/role": ("POST", "صلاحية user_role.update",
                            "user, role, reason",
                            "{user} — وتُنهى جلساتُ الهدف",
                            "400 دورٌ مجهول · 403 حارسُ التسلسل · 404"),
  "/app/admin/users/status": ("POST", "صلاحية user.update", "user, status, reason",
                              "{user}", "400 · 403 · 404"),
  "/app/admin/roles":  ("GET", "صلاحية user_role.read", "—",
                        "{roles, assignable, permissions}", "401 · 403"),
  "/app/admin/audit":  ("GET", "صلاحية audit.list", "limit, offset, action, actor, result",
                        "{total, events[]} — وقراءتُه نفسُها تُسجَّل", "401 · 403"),
  "/app/schedules":    ("GET", "جلسة", "—", "{schedules[]}", "401"),
  "/app/schedules/{id}": ("GET", "جلسة · مالكٌ", "—",
                        "{schedule, runs[]} — تاريخُ التنفيذ لا آخرُ قيمة",
                        "401 · 404"),
  "/app/schedules/create": ("POST", "جلسة · مالكُ المشروع",
                        "project, kind, title, recurrence, tz, at_minute, day_of",
                        "{schedule} — الجدولةُ في الخادم لا في العميل، و`tz` "
                        "اسمُ منطقةٍ لا إزاحةٌ تنزاح بالتوقيت الصيفيّ",
                        "400 · 401 · 404"),
  "/app/schedules/update": ("POST", "جلسة · مالك", "id + الحقولُ المعدَّلة",
                        "{schedule} — ويُعاد حسابُ الاستحقاق", "400 · 401 · 404"),
  "/app/schedules/status": ("POST", "جلسة · مالك", "id, status=active|paused",
                        "{schedule} — والاستئنافُ من الآن لا من الماضي",
                        "400 · 401 · 404"),
  "/app/schedules/delete": ("POST", "جلسة · مالك", "id", "{deleted}",
                        "401 · 404"),
  "/app/admin/metrics": ("GET", "صلاحية metrics.read", "—",
                        "{uptime_s, counters[], timers[], queue} — لقطةٌ من "
                        "الذاكرة. الوسومُ معدودةٌ مسبقًا (مسارٌ مُعمَّمٌ · طريقةٌ · "
                        "رمز) فلا معرّفَ مستخدمٍ ولا طلبٍ فيها",
                        "401 · 403"),
}

def frontend_calls():
    """ما تناديه الواجهة فعلًا — للتحقّق أنها لا تنادي مسارًا لا وجود له."""
    src = read("falah-app.html")
    return sorted({m for m in re.findall(r'["\'](/app/[a-z/\-]+)["\']', src)}
                  | {m.split("?")[0] for m in re.findall(r'["\'](/[a-z]+)\?', src)})

def build():
    live = content_routes() + ["/healthz", "/readyz"]
    reads, writes = app_routes()
    return live, reads, writes

def table():
    live, reads, writes = build()
    out = ["# عقد الـAPI",
           "",
           "> مولَّدٌ من الشيفرة بـ`python3 api_contract.py`. لا يُحرَّر باليد.",
           ""]
    for title, group in (("طبقة المحتوى — قراءةٌ عامّة", live),
                         ("التطبيق — قراءة", reads),
                         ("التطبيق — كتابة", writes)):
        out += [f"## {title}", "",
                "| METHOD | PATH | AUTH | INPUT | OUTPUT | ERRORS |",
                "|---|---|---|---|---|---|"]
        for r in group:
            s = SPEC.get(r)
            if not s: out.append(f"| ? | `{r}` | **غير موثَّق** | | | |"); continue
            out.append(f"| {s[0]} | `{r}` | {s[1]} | {s[2]} | {s[3]} | {s[4]} |")
        out.append("")
    out += ["## ملاحظاتٌ تحكم كل المسارات", "",
            "- كل طلب كتابةٍ يشترط ترويسة `X-FALAH: 1`، و`Origin` المطابق إن حُدِّد `FALAH_ORIGIN`.",
            "- الجلسة كعكة `falah_sid` — HttpOnly · SameSite=Strict · Secure خلف HTTPS.",
            "- «ملكية» تعني أن الصفَّ يُقرأ بشرط `user_id` — رقمٌ مخمَّن لا يكشف عمل غيره.",
            "- كل مسارٍ يُقرَّر إذنُه في `falah/authz.py` بصلاحيةٍ اسمُها `<مورِد>.<فعل>` "
            "ونطاقٍ (OWNER · SELF · ANY). ولا اسمَ دورٍ في شرطٍ واحد.",
            "- **`X-FALAH-ADMIN` أُلغي في P1.2**: الإدارةُ بدورٍ على حسابٍ حقيقيّ. "
            "وأوّلُ `super_admin` يُصنع بـ`python3 -m falah.roles grant <بريد> super_admin`.",
            "- الأفعالُ الحسّاسة تُسجَّل في `audit_logs` — يُلحق ولا يُعدَّل ولا يُحذف، "
            "ولا سرَّ فيه.",
            "- الخطأ الداخليّ يردّ `{\"error\": \"خطأ داخلي\"}` ويُسجَّل تفصيله عندنا؛ "
            "ونصّ الاستثناء لا يُرسل.",
            "- `/app/export` و`/app/video` **لا تُصيّران داخل الطلب**: تردّان ٢٠٢ "
            "وتُستطلع المهمّة على `/app/jobs/<id>`.",
            ""]
    return "\n".join(out)

def audit():
    live, reads, writes = build()
    all_routes = set(live) | set(reads) | set(writes)
    undoc  = sorted(all_routes - set(SPEC))
    stale  = sorted(set(SPEC) - all_routes)
    fe     = set(frontend_calls())
    ghost  = sorted(x for x in fe if x.startswith("/app/") and x not in all_routes
                    and not any(x.startswith(r.split("/{")[0] + "/") for r in all_routes))
    return undoc, stale, ghost

if __name__ == "__main__":
    md = table()
    undoc, stale, ghost = audit()
    if "--check" in sys.argv:
        bad = False
        for name, items in (("مسارٌ قائمٌ بلا توثيق", undoc),
                            ("موثَّقٌ ولا وجود له", stale),
                            ("الواجهة تنادي ما لا يقدّمه الخادم", ghost)):
            if items: bad = True; print(f"  ✗ {name}: {items}")
        cur = read("API.md") if os.path.exists(os.path.join(HERE, "API.md")) else ""
        if cur.strip() != md.strip():
            bad = True; print("  ✗ API.md متقادم — شغّل python3 api_contract.py")
        print("QUALITY_GATE = " + ("FAIL" if bad else "PASS"))
        sys.exit(1 if bad else 0)
    open(os.path.join(HERE, "API.md"), "w", encoding="utf-8").write(md + "\n")
    n = len(set(build()[0]) | set(build()[1]) | set(build()[2]))
    print(f"كُتب API.md — {n} مسارًا")
    for name, items in (("بلا توثيق", undoc), ("موثَّقٌ ولا وجود له", stale),
                        ("تناديه الواجهة ولا وجود له", ghost)):
        if items: print(f"  ! {name}: {items}")
