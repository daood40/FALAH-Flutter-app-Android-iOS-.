"""جدولُ المسارات — إعلانٌ يُقرأ في نظرة، ثم تنفيذٌ موحَّد.

لكلِّ مسارٍ سطرٌ واحدٌ يقول كلَّ شيء:

    الطريقة · المسار · الوثيقة · (المورِد، الفعل) · الحقول · الحصّة · الحدّ

ولماذا جدولٌ لا `if/elif`؟ لأن السلسلة كانت تخفي ما ليس فيها. لتعرف أن
مسارًا يحتاج جلسةً كان عليك أن تتتبّع أين يقع من `u = self.user(c)`؛
ولتعرف أنه يفحص ملكيّةً كان عليك أن تقرأ ما تحته. هنا يُقرأ السطرُ فيُعرف،
ويُختبر الجدولُ نفسه: أن كلَّ مسارٍ أعلن مورِدَه، وأن كلَّ مورِدٍ له سياسة.

**والمنعُ أصلٌ.** ما لم يُعلَن لا يُنفَّذ: مسارٌ غير موجودٍ يمرّ على القاعدة
العامّة (وثيقةٌ ثم ٤٠٤)، ومورِدٌ بلا سياسةٍ في `authz.POLICY` يُمنع.

الترتيب في كل طلب:

    تحليلٌ → اختيارُ مسار → وثيقةٌ → حدُّ معدّلٍ (إن كان قبليًّا)
          → تحميلُ المورِد → إذنٌ → تحقّقُ حقولٍ → معالِج → ردّ

وترتيبُ تقييم الحقول محفوظٌ كما كان في `app_post` — لأن اختلافَه يغيّر
أيَّ خطأٍ يظهر أوّلًا للمستخدم، وهذا سلوكٌ ظاهرٌ لا تفصيلٌ داخليّ.
"""
from falah import app_routes as R, auth, authz as AZ, billing
from falah import jobs as JB, projects as P, ratelimit as RL, referrals as REF
from falah.web import Response

# أخطاءُ النطاق التي تعني «طلبُك خاطئ» لا «الخادمُ معطوب». تُجمع هنا لأن
# طبقةَ HTTP لا ينبغي أن تعرف أسماءَ وحدات النطاق واحدةً واحدة.
DOMAIN_ERRORS = (P.ProjectError, auth.AuthError, billing.BillingError,
                 REF.ReferralError, JB.JobError)

# ───────────────────────── أنواع الحقول ─────────────────────────
# تُقيَّم بالترتيب المكتوب، فيظهر الخطأُ الأوّل كما كان يظهر.

INT  = "int"     # int(b[key])  — ناقصٌ ⇒ KeyError، غيرُ رقمٍ ⇒ ValueError
RAW  = "raw"     # b[key] كما هو
INTS = "ints"    # [int(x) for x in b[key]]

def _fields(rq, spec):
    for name, key, kind in spec:
        v = rq.body[key]
        rq.params[name] = (int(v) if kind == INT else
                           [int(x) for x in v] if kind == INTS else v)

# ───────────────────────── وصفُ المسار ─────────────────────────

class Route:
    __slots__ = ("method", "path", "kind", "auth", "resource", "action",
                 "fields", "owner_field", "rate", "quota", "handler", "note")

    def __init__(self, method, path, handler, *, kind="exact", auth="session",
                 resource="unknown", action="read", fields=(), owner_field=None,
                 rate=None, quota=None, note=""):
        self.method, self.path, self.handler = method, path, handler
        self.kind, self.auth = kind, auth
        self.resource, self.action = resource, action
        self.fields, self.owner_field = tuple(fields), owner_field
        self.rate, self.quota, self.note = rate, quota, note

    def __repr__(self):
        return f"Route({self.method} {self.path} → {self.resource}.{self.action})"

def _r(*a, **k): return Route(*a, **k)

# ───────────────────────── الجدول ─────────────────────────
# auth: "public" لا يشترط جلسة · "session" يشترطها (والإذن يفرضها كذلك)
# rate: (النوع، "user"|"ip") يُفحص **قبل** المعالِج. وما فحصُه بعد قبول
#       العمل مكتوبٌ في `note` ويقع داخل المعالِج — انظر `ratelimit.py`.

GET = [
    _r("GET", "/app/config",   R.config,  auth="public", resource="catalogue"),
    _r("GET", "/app/plans",    R.plans,   auth="public", resource="catalogue"),
    _r("GET", "/app/me",       R.me,      auth="public", resource="catalogue"),

    _r("GET", "/app/entitlements", R.entitlements, resource="subscription"),
    _r("GET", "/app/referrals",    R.referrals,    resource="referral"),
    _r("GET", "/app/projects",     R.projects,     resource="project", action="list"),
    _r("GET", "/app/limits",       R.limits,       resource="limits"),
    _r("GET", "/app/jobs",         R.jobs,         resource="job", action="list"),
    _r("GET", "/app/exports",      R.exports,      resource="export", action="list"),
    _r("GET", "/app/file",         R.file_get,     resource="export_file",
       action="download", rate=("file", "user"),
       note="الحدُّ قبليٌّ: التنزيل رخيصٌ لكنّه كثير"),

    _r("GET", "/app/projects/", R.project_open, kind="param", owner_field="project",
       resource="project", action="read"),
    _r("GET", "/app/jobs/",     R.job_get,     kind="param", owner_field="job",
       resource="job", action="read"),
]

POST = [
    _r("POST", "/app/register", R.register, auth="public",
       resource="registration", action="create",
       rate=("register", "ip"), note="الحدُّ لكل عنوان — والعناوين تُشارَك"),
    _r("POST", "/app/password/forgot", R.password_forgot, auth="public",
       resource="credential", action="update"),
    _r("POST", "/app/password/reset",  R.password_reset,  auth="public",
       resource="credential", action="update"),
    _r("POST", "/app/verify/confirm",  R.verify_confirm,  auth="public",
       resource="credential", action="update"),
    _r("POST", "/app/login",  R.login,  auth="public", resource="session", action="create"),
    _r("POST", "/app/logout", R.logout, auth="public", resource="session", action="delete"),

    _r("POST", "/app/account/delete", R.account_delete, resource="account", action="delete"),
    _r("POST", "/app/subscription/cancel", R.subscription_cancel,
       resource="subscription", action="update"),
    _r("POST", "/app/subscription/store-event", R.subscription_store_event,
       resource="subscription", action="update"),
    _r("POST", "/app/subscription/grant", R.subscription_grant,
       resource="subscription", action="grant",
       note="يشترط صلاحية manage_billing — لا اسمَ دورٍ مكتوبًا في المسار"),
    _r("POST", "/app/verify/request", R.verify_request, resource="account", action="update"),
    _r("POST", "/app/profile",  R.profile,         resource="account", action="update"),
    _r("POST", "/app/password", R.password_change, resource="account", action="update"),

    _r("POST", "/app/projects/create", R.project_create,
       resource="project", action="create", quota="projects"),
    _r("POST", "/app/projects/update", R.project_update,
       resource="project", action="update", owner_field="project",
       fields=(("project", "id", INT),)),
    _r("POST", "/app/projects/delete", R.project_delete,
       resource="project", action="delete", owner_field="project",
       fields=(("project", "id", INT),)),

    _r("POST", "/app/items/add", R.item_add,
       resource="project_item", action="create", owner_field="project",
       fields=(("project", "project", INT), ("kind", "kind", RAW), ("ref", "ref", RAW))),
    _r("POST", "/app/items/remove", R.item_remove,
       resource="project_item", action="delete", owner_field="project",
       fields=(("project", "project", INT), ("item", "id", INT))),
    _r("POST", "/app/items/reorder", R.item_reorder,
       resource="project_item", action="update", owner_field="project",
       fields=(("project", "project", INT), ("order", "order", INTS))),
    _r("POST", "/app/items/accept-drift", R.item_accept_drift,
       resource="project_item", action="update", owner_field="project",
       fields=(("project", "project", INT), ("item", "id", INT))),

    _r("POST", "/app/export", R.export,
       resource="project", action="render", owner_field="project",
       fields=(("project", "project", INT),), quota="cards",
       note="الحدُّ داخل المعالِج: يُعدّ العملُ المقبول لا الطلب"),
    _r("POST", "/app/video", R.video,
       resource="project", action="render", owner_field="project",
       fields=(("project", "project", INT), ("item", "item", INT)), quota="videos",
       note="الحدُّ داخل المعالِج — كالتصدير"),

    _r("POST", "/app/agent",       R.agent_ask,   resource="agent", action="read",
       rate=("agent", "user")),
    _r("POST", "/app/agent/build", R.agent_build, resource="agent", action="create"),

    _r("POST", "/app/jobs/cancel", R.job_cancel,
       resource="job", action="cancel", owner_field="job",
       fields=(("job", "id", INT),)),
]

# القاعدةُ العامّة: مسارُ تطبيقٍ لم يُعلَن. وثيقةٌ أوّلًا ثم ٤٠٤ — كما كان
# تمامًا حين كان `if not u: 401` يسبق `مسار غير معروف` في آخر السلسلة.
FALLBACK = _r("*", "*", R.unknown, kind="any", resource="unknown", action="read")

TABLE = {"GET": GET, "POST": POST}
_EXACT = {m: {r.path: r for r in rs if r.kind == "exact"} for m, rs in TABLE.items()}
_PARAM = {m: [r for r in rs if r.kind == "param"] for m, rs in TABLE.items()}

def resolve(method, path):
    """يعيد (المسار، اسمُ حقلِ المعرِّف من المسار). لا يفتح قاعدةً ولا يقرّر."""
    r = _EXACT.get(method, {}).get(path)
    if r: return r, None
    for r in _PARAM.get(method, []):
        if path.startswith(r.path):
            return r, r.owner_field
    return FALLBACK, None

def declared():
    """كلُّ ما أُعلن — يقرؤه فحصُ العقد وفحصُ اكتمال الجدول."""
    return sorted((r.method, r.path + ("{id}" if r.kind == "param" else ""),
                   r.auth, r.resource, r.action)
                  for rs in TABLE.values() for r in rs)

# ───────────────────────── ترجمةُ المنع إلى ردّ ─────────────────────────
# رسائلُ اليوم نفسُها ورموزُها نفسُها. و«غيرُ موجود» و«ليس لك» ردٌّ واحد
# عمدًا: التفريقُ يكشف وجودَ مورِدِ غيرك برقمٍ مخمَّن.

MISSING = {
    "project":      (400, "المشروع غير موجود"),
    "project_item": (400, "المشروع غير موجود"),
    "job":          (400, "المهمّة غير موجودة"),
    "export_file":  (404, "ملف غير متاح"),
}

def denial_response(d):
    if d.reason == AZ.UNAUTHENTICATED:
        return Response({"error": "يلزم تسجيل الدخول"}, 401)
    if d.reason == AZ.NOT_FOUND:
        code, msg = MISSING.get(d.resource.type, (404, "غير موجود"))
        return Response({"error": msg}, code)
    return Response({"error": "غير مصرَّح"}, 403)

# ───────────────────────── التنفيذ ─────────────────────────

def locate(rq, route, path_id):
    """يبني المورِدَ الذي سيُحكم عليه — **بمالكه مقروءًا من القاعدة**."""
    if route.resource == "export_file":
        rel = rq.query.get("p", [""])[0]
        res = AZ.export_file(rq.root, rel)
        rq.params["export_file"] = res.attrs.get("path")
        return res
    if path_id is not None:
        # `/app/projects/7` — النصُّ نفسه الذي كان: آخرُ مقطعٍ يُحوَّل عددًا،
        # فما ليس عددًا يسقط ٤٠٠ كما كان لا ٤٠٤.
        rq.params[path_id] = int(rq.path.rsplit("/", 1)[-1])
        return AZ.load(rq.c, route.resource if route.resource != "project_item"
                       else "project", rq.params[path_id])
    if route.fields:
        _fields(rq, route.fields)
    if route.owner_field:
        kind = "project" if route.resource == "project_item" else route.resource
        return AZ.load(rq.c, kind, rq.params[route.owner_field])
    return AZ.own(route.resource, rq.subject)

def dispatch(rq):
    """يمرّ بالطلب على الترتيب المُعلَن ويعيد `Response`.

    ولا يبتلع استثناءً: أخطاءُ النطاق تصعد إلى طبقةِ HTTP لتُترجَم هناك
    كما كانت تُترجَم — موضعٌ واحدٌ للترجمة لا موضعان.
    """
    route, path_id = resolve(rq.method, rq.path)

    # ١) حدُّ المعدّل القبليّ — قبل أيّ عمل، وقبل معرفةِ المورِد
    if route.rate:
        kind, by = route.rate
        who = rq.client_ip if by == "ip" else rq.uid
        if by == "user" and who is None:
            # مسارٌ محدودٌ بالمستخدم بلا جلسة: الوثيقةُ أوّلًا كما كانت
            return denial_response(AZ.can(rq.subject, route.action,
                                          AZ.Resource(route.resource)))
        if not RL.ok(rq.c, kind, who):
            body, hdr = RL.exceeded(kind)
            return Response(body, 429, headers=hdr)
        RL.bump(rq.c, kind, who); rq.c.commit()

    # ٢) المورِد ثم الإذن — بهذا الترتيب، فلا حكمَ على مورِدٍ لم يُحمَّل
    res = locate(rq, route, path_id)
    d = AZ.can(rq.subject, route.action, res)
    if not d:
        return denial_response(d)

    # ٣) بقيّةُ الحقول لمسارٍ لم يُحمَّل له مورِدٌ من حقلٍ
    if route.fields and not route.owner_field:
        _fields(rq, route.fields)

    return route.handler(rq)
