"""طبقةُ الإذن — موضعٌ واحدٌ يُسأل: **أيجوز لهذا أن يفعل هذا بهذا؟**

    can(subject, action, resource) → Decision

ثلاثةُ أشياءَ لا رابع:

  • **subject** — من يطلب. مستخدمٌ بجلسة، أو مجهول. ومعه أدوارُه.
  • **action**  — ماذا يريد: قراءةٌ · إنشاءٌ · تعديلٌ · حذفٌ · تصييرٌ · إلغاءٌ …
  • **resource**— على ماذا: مشروعٌ برقمٍ ومالك، أو مهمّةٌ، أو ملفٌّ مصدَّر.

ولماذا هذه الصيغة بالذات؟

  ١. **لا ارتباط بأسماء المسارات.** لو أُعيدت تسمية `/app/projects/update`
     غدًا لم يتغيّر هنا حرف. القاعدةُ على «مشروعٌ يُعدَّل»، لا على مسار.

  ٢. **المالكُ يُقرأ من القاعدة لا من الطلب.** هذا هو حرفيًّا ما يمنع IDOR:
     لا يُصدَّق رقمٌ جاء من العميل بأنه له. يُحمَّل المورِد، ويُقرأ مالكُه
     الحقيقيّ، ثم يُقارَن. ومن لم يُحمَّل مورِدُه فلا إذنَ له.

  ٣. **المنعُ هو الأصل.** ما لم تُعلَن له قاعدةٌ في `POLICY` يُمنع ويُقال
     «لا سياسةَ لهذا» — لا يُسمح لأنه لم يُذكر. إضافةُ فعلٍ جديدٍ بلا قاعدة
     تسقط عند أول اختبار، وهذا مقصود.

  ٤. **الأدوارُ مكانُها محجوز.** اليوم دورٌ واحد يمنحه المفتاح الإداريّ.
     وفي P1.2 تُقرأ الأدوارُ من القاعدة وتُمنح صلاحياتٌ مسمّاة — ولا يتغيّر
     نداءُ `can` في موضعٍ واحد، لأن الشرط هنا مكتوبٌ على الصلاحية لا على
     اسمِ الدور.

ولا تعرف هذه الوحدةُ شيئًا عن HTTP: لا رموزَ حالة ولا ترويسات. الترجمةُ
إلى ردٍّ من عمل الطبقة التي فوقها.
"""
import os

# ───────────────────────── الأفعال ─────────────────────────
# قائمةٌ مغلقة. فعلٌ خارجها خطأُ برمجةٍ يُرفع فورًا، لا منعٌ صامت.
ACTIONS = frozenset({
    "read",      # قراءةُ مورِدٍ بعينه
    "list",      # سردُ ما يملكه صاحبُ الجلسة
    "create",    # إنشاءُ مورِدٍ جديد
    "update",    # تعديل
    "delete",    # حذف
    "render",    # وضعُ عملِ تصييرٍ في الطابور (تصديرٌ أو مقطع)
    "cancel",    # إلغاءُ مهمّة
    "download",  # تنزيلُ ملفٍّ مصدَّر
    "grant",     # منحةٌ إدارية
})

# ───────────────────────── الصلاحيات ─────────────────────────
# **اسمُ الصلاحية هو الزوجُ نفسُه**: `project.update` هي بالضبط
# `(resource="project", action="update")`.
#
# ولهذا فائدةٌ لا تُقدَّر: **لا يمكن أن توجد عمليةٌ بلا صلاحية**، لأن
# الصلاحيةَ ليست شيئًا يُكتب إلى جانب العملية بل هي اسمُها. ومسارٌ جديدٌ
# يعلن مورِدَه وفعلَه فقد أعلن صلاحيتَه، ومن نسي أن يمنحها لدورٍ سقط في
# `authz_test.py` لا في الإنتاج.
#
# والكتالوجُ **مستخرَجٌ من النظام لا مفترَض**: كلُّ سطرٍ هنا يقابل عمليةً
# قائمةً في `falah/routing.py` — انظر `docs/P1.2_BASELINE.md §٩`.

def _p(resource, action):
    return f"{resource}.{action}"

# ما يفعله من لا حسابَ له. وهذه هي حدودُ «العامّ» كلُّها، مكتوبةً في موضعٍ
# واحدٍ يُقرأ — لا مبثوثةً في شروطٍ متفرّقة.
ANON_PERMS = frozenset({
    "content.read", "content.list",   # النصوص المفحوصة — عامّةٌ بطبيعة المشروع
    "service.read",          # الحياة والجاهزية
    "catalogue.read",        # الخطط · إعدادُ العميل · «من أنا»
    "registration.create",   # التسجيل
    "session.create",        # الدخول
    "session.delete",        # الخروج — يعمل بجلسةٍ وبلا جلسة
    "credential.update",     # نسيتُ · إعادةُ تعيين · تأكيدُ بريد
})

# ما يزيده صاحبُ الحساب العاديّ.
USER_PERMS = ANON_PERMS | frozenset({
    # القاعدةُ العامّة: صاحبُ الجلسة يبلغ ٤٠٤ على مسارٍ لا وجود له،
    # والمجهولُ يُردّ ٤٠١ قبل ذلك. سلوكُ اليوم نفسُه، معبَّرًا عنه بصلاحية.
    "unknown.read",
    "account.update", "account.delete",
    "subscription.read", "subscription.update",
    "referral.read",
    "limits.read",
    "agent.read", "agent.create",
    "project.list", "project.create",
    "project.read", "project.update", "project.delete", "project.render",
    "project_item.create", "project_item.update", "project_item.delete",
    "job.list", "job.read", "job.cancel",
    "schedule.list", "schedule.read", "schedule.create",
    "schedule.update", "schedule.delete",
    # النشر: الحسابُ المربوط سرٌّ لصاحبه — ولا يُقرأ ولا يُفصل إلا هو
    "publish_account.list", "publish_account.create", "publish_account.delete",
    "publish_attempt.list",
    "export.list", "export_file.download",
})

# صلاحياتُ الإدارة. كلُّها مكتوبةٌ باسمها — **ولا نجمةَ ولا `admin.*`**.
ADMIN_PERMS = frozenset({
    "user.list",          # سردُ الحسابات
    "user.read",          # قراءةُ حسابٍ بعينه
    "user.update",        # إيقافٌ وإعادةُ تفعيل
    "user_role.read",     # قراءةُ الأدوار وصلاحياتها
    "user_role.update",   # تغييرُ دورِ حساب
    "audit.list",         # قراءةُ سجلّ التدقيق
    "subscription.grant", # منحُ اشتراكٍ وقبولُ إيصالٍ موثوق
    "metrics.read",       # قراءةُ القياسات — تكشف حجمَ الاستعمال وأنماطَ الفشل
})

PERMISSIONS = frozenset(USER_PERMS | ADMIN_PERMS)

# ───────────────────────── الأدوار ─────────────────────────
# **الدورُ حزمةُ صلاحياتٍ، لا شيءٌ يُفحص باسمه.** ولا يُكتب في المشروع كلِّه
# `if role == "admin"` — يفحص ذلك `authz_test.py` على الشيفرة نفسها.
#
# والتعيينُ صريحٌ ومحسوبٌ بالضمّ. الترتيبُ خطّيٌّ اليوم لأن حاجةَ اليوم
# خطّية، والبنيةُ لا تفترضه: `ROLES` قاموسُ (اسم → مجموعة)، فدورٌ جانبيٌّ
# غيرُ خطّيّ يُضاف بلا تغييرِ منطق.

_MODERATOR = USER_PERMS | {"user.list", "user.read", "audit.list",
                           "metrics.read"}
_ADMIN     = _MODERATOR | {"user.update", "user_role.read", "subscription.grant"}
_SUPER     = _ADMIN | {"user_role.update"}

ROLES = {
    "anonymous":   ANON_PERMS,
    "user":        USER_PERMS,
    "moderator":   frozenset(_MODERATOR),
    "admin":       frozenset(_ADMIN),
    "super_admin": frozenset(_SUPER),
}

DEFAULT_ROLE = "user"          # افتراضيُّ كل حسابٍ جديدٍ وكل حسابٍ قائم
ASSIGNABLE = ("user", "moderator", "admin", "super_admin")

def perms_of(role):
    """صلاحياتُ دورٍ. **دورٌ مجهولٌ ⇒ لا صلاحية** — fail closed لا fail open.

    وهذا ليس احتياطًا نظريًّا: لو كُتب في القاعدة دورٌ بخطأٍ مطبعيّ، أو
    أُسقط دورٌ من الشيفرة وبقي في صفٍّ، فالنتيجةُ منعٌ كامل لا سماحٌ كامل.
    """
    return ROLES.get(role or "", frozenset())

class Subject:
    """من يطلب. لا يُبنى من حمولةِ طلبٍ أبدًا — بل من جلسةٍ مُتحقَّقٍ منها.

    والدورُ يُقرأ من القاعدة مع الجلسة، ولا يُقبل من جسمِ طلبٍ ولا كعكةٍ
    ولا ترويسة — وهذا هو الفرقُ بين نظامِ أدوارٍ ونظامٍ يبدو كذلك.
    """
    __slots__ = ("user_id", "roles")

    def __init__(self, user_id=None, roles=("anonymous",)):
        self.user_id = int(user_id) if user_id is not None else None
        self.roles = frozenset(roles) or frozenset({"anonymous"})

    @property
    def authenticated(self):
        return self.user_id is not None

    @property
    def permissions(self):
        """اتّحادُ صلاحيات أدواره. ودورٌ مجهولٌ لا يضيف شيئًا — fail closed."""
        out = frozenset()
        for r in self.roles:
            out |= perms_of(r)
        return out

    def has(self, permission):
        return permission in self.permissions

    @property
    def role(self):
        """الدورُ الأعلى — للعرض وللسجلّ فقط، لا يُبنى عليه قرار."""
        return max(self.roles, key=lambda r: len(perms_of(r)), default="anonymous")

    def __repr__(self):
        return f"Subject(user={self.user_id}, roles={sorted(self.roles)})"

ANON = Subject()

class Resource:
    """المورِد **بعد تحميله**. `owner_id` مقروءٌ من القاعدة لا من الطلب.

    و`exists=False` تعني: لم يُعثر عليه. ولا يُفرَّق في الردّ بين «غيرُ
    موجود» و«ليس لك» — فالتفريقُ يكشف وجودَ مورِدِ غيرك برقمٍ مخمَّن.
    """
    __slots__ = ("type", "id", "owner_id", "exists", "attrs")

    def __init__(self, type, id=None, owner_id=None, exists=True, **attrs):
        self.type, self.id = type, id
        self.owner_id = int(owner_id) if owner_id is not None else None
        self.exists = exists
        self.attrs = attrs

    def __repr__(self):
        return (f"Resource({self.type}#{self.id}, owner={self.owner_id}, "
                f"exists={self.exists})")

class Decision:
    """قرارٌ يحمل سببَه. السببُ رمزٌ ثابت — تترجمه الطبقةُ الأعلى إلى ردّ."""
    __slots__ = ("allowed", "reason", "resource", "action", "permission")

    def __init__(self, allowed, reason, action=None, resource=None, permission=None):
        self.allowed, self.reason = allowed, reason
        self.action, self.resource = action, resource
        self.permission = permission

    def __bool__(self):  return self.allowed
    def __repr__(self):
        return f"Decision({'allow' if self.allowed else 'deny'}: {self.reason})"

# أسبابُ المنع. ثابتةٌ ومعدودة — لا نصَّ حرًّا يُقرأ من الخارج.
UNAUTHENTICATED = "unauthenticated"   # لا جلسة
NOT_FOUND       = "not_found"          # غيرُ موجود، أو ليس لك — سواء
FORBIDDEN       = "forbidden"          # جلسةٌ صحيحةٌ وصلاحيةٌ ناقصة
NO_POLICY       = "no_policy"          # لم تُعلَن قاعدة — يُمنع بحكم الأصل
ALLOWED         = "allowed"

class Denied(Exception):
    """يُرفع عند المنع. يحمل القرار، فتقرأ الطبقةُ الأعلى سببَه ونوعَ مورِده."""
    def __init__(self, decision):
        self.decision = decision
        super().__init__(decision.reason)

# ───────────────────────── النطاقات ─────────────────────────
# بوّابةُ الصلاحية تسأل عن **الفاعل**؛ وهذه تسأل عن **هذا المورِد بعينه**.
# وفصلُهما هو ما يمنع فوضى `if role == "admin"`: الإداريُّ يملك صلاحيةً
# أوسعَ ونطاقًا أوسع — سطرٌ في جدول، لا شرطٌ في مئة دالّة.

def PUBLIC(s, r):
    """لا جلسةَ ولا مورِد. الصلاحيةُ وحدها تكفي (ويملكها المجهول)."""
    return ALLOWED

def AUTHENTICATED(s, r):
    """جلسةٌ فقط — لا رقمَ مورِدٍ يأتي من الطلب أصلًا (سردٌ أو إنشاء)."""
    return ALLOWED

def OWNER(s, r):
    """جوهرُ منع IDOR: وجودٌ ثم تطابقُ مالكٍ **محمَّل من القاعدة**.

    ولا دورَ يوسّع هذا. `super_admin` لا يقرأ مشروعَ غيره، لأن نطاقَ
    `project.read` هو `OWNER` لكلِّ دور — وذلك مقصودٌ ومكتوبٌ في التصميم.
    """
    if not r.exists or r.owner_id is None:   return NOT_FOUND
    if r.owner_id != s.user_id:              return NOT_FOUND
    return ALLOWED

def SELF(s, r):
    """مورِدٌ هو صاحبُ الجلسة نفسه: حسابُه، اشتراكُه، إحالاتُه."""
    if r.id is not None and int(r.id) != s.user_id: return NOT_FOUND
    return ALLOWED

def ANY(s, r):
    """مورِدٌ لا يقيّده نطاق — لمن يملك صلاحيةً إدارية.

    وليس هذا تجاوزًا: البوّابةُ الأولى (الصلاحية) هي التي حسمت، وحارسُ
    التسلسل في `may_manage` هو الذي يقيّد **مَن** يُدار. انظر §٥ من التصميم.
    """
    return ALLOWED

# ───────────────────────── جدول السياسة ─────────────────────────
# (نوعُ المورِد، الفعل) → النطاق. وما ليس هنا ممنوع.
# والصلاحيةُ المطلوبة تُشتقّ من المفتاح نفسه: "<مورِد>.<فعل>".

POLICY = {
    # المحتوى العامّ — قراءةٌ بلا حساب، وهي طبيعةُ المشروع لا ثغرةٌ فيه
    ("content",      "read"):     PUBLIC,
    ("content",      "list"):     PUBLIC,
    ("service",      "read"):     PUBLIC,     # الحياة والجاهزية
    ("catalogue",    "read"):     PUBLIC,     # الخطط وإعدادُ العميل و«من أنا»

    # ما يسبق الجلسة بطبيعته — لا يجوز أن يشترط جلسةً من يريد أن ينشئها
    ("registration", "create"):   PUBLIC,
    ("session",      "create"):   PUBLIC,     # دخول
    ("session",      "delete"):   PUBLIC,     # خروج — يعمل بجلسةٍ وبلا جلسة
    ("credential",   "update"):   PUBLIC,     # نسيتُ · إعادةُ تعيين · تأكيدُ بريد

    # المشاريع
    ("project",      "list"):     AUTHENTICATED,
    ("project",      "create"):   AUTHENTICATED,
    ("project",      "read"):     OWNER,
    ("project",      "update"):   OWNER,
    ("project",      "delete"):   OWNER,
    ("project",      "render"):   OWNER,

    # عناصرُ المشروع — إذنُها إذنُ مشروعها، ويُحمَّل مالكُ المشروع لأجلها
    ("project_item", "create"):   OWNER,
    ("project_item", "update"):   OWNER,
    ("project_item", "delete"):   OWNER,

    # المهامّ
    ("job",          "list"):     AUTHENTICATED,
    ("job",          "read"):     OWNER,
    ("job",          "cancel"):   OWNER,

    # الجدولة. السردُ AUTHENTICATED لأنه محصورٌ بالمستخدم في الاستعلام
    # نفسِه؛ وما عداه OWNER — والمالكُ يُقرأ من القاعدة لا يُصدَّق من الطلب.
    # و`create` نطاقُه المشروعُ لا الجدول: لا جدولَ بعدُ ليُملَك، والمحروسُ
    # هو أن يكون المشروعُ لك.
    ("schedule",     "list"):     AUTHENTICATED,
    ("schedule",     "read"):     OWNER,
    ("schedule",     "create"):   AUTHENTICATED,
    ("schedule",     "update"):   OWNER,
    ("schedule",     "delete"):   OWNER,
    ("publish_account", "list"):   AUTHENTICATED,
    ("publish_account", "create"): AUTHENTICATED,
    ("publish_account", "delete"): OWNER,
    ("publish_attempt", "list"):   AUTHENTICATED,

    # الملفّات المصدَّرة
    ("export",       "list"):     AUTHENTICATED,
    ("export_file",  "download"): OWNER,

    # الحساب وما يتعلّق به
    ("account",      "update"):   SELF,
    ("account",      "delete"):   SELF,
    ("subscription", "read"):     SELF,
    ("subscription", "update"):   SELF,       # الإلغاء وإيصالُ المتجر
    ("subscription", "grant"):    ANY,        # منحةٌ إدارية — صلاحيتُها إدارية
    ("referral",     "read"):     SELF,
    ("agent",        "read"):     AUTHENTICATED,
    ("agent",        "create"):   AUTHENTICATED,
    ("limits",       "read"):     AUTHENTICATED,

    # ═══ الإدارة — كلُّها بصلاحياتٍ مسمّاة، وبحارس تسلسلٍ فوقها ═══
    ("user",         "list"):     AUTHENTICATED,
    ("user",         "read"):     ANY,
    ("user",         "update"):   ANY,
    ("user_role",    "read"):     AUTHENTICATED,
    ("user_role",    "update"):   ANY,
    ("audit",        "list"):     AUTHENTICATED,
    # القياساتُ ليست عامّة: تكشف حجمَ الاستعمال وأنماطَ الفشل،
    # وكلاهما معلومةٌ لمن يخطّط هجومًا. مشرفٌ فما فوق.
    ("metrics",      "read"):     AUTHENTICATED,

    # مسارُ تطبيقٍ لم يُعلَن. وثيقةٌ أوّلًا ثم ٤٠٤ من معالِجه — وهو ترتيبُ
    # اليوم نفسُه: `if not u: 401` كان يسبق «مسار غير معروف».
    ("unknown",      "read"):     AUTHENTICATED,
}

def can(subject, action, resource):
    """أيجوز لـ`subject` أن يفعل `action` بـ`resource`؟

    نداءٌ صافٍ: لا يلمس قاعدةً ولا شبكة. المورِدُ يصل محمَّلًا ومالكُه
    مقروء — انظر `load` أدناه. وهذا الفصلُ مقصود: القرارُ يُختبر وحده.

    **ثلاثُ بوّاباتٍ بترتيبها، وكلُّها يجب أن تُفتح:**

      ① وثيقة  — مورِدٌ غيرُ عامٍّ يشترط جلسةً. (وترتيبُها أوّلًا مقصود:
                  فالمجهولُ يُردّ ٤٠١ لا ٤٠٣، وهو سلوكُ اليوم نفسُه.)
      ② صلاحية — هل يملك دورُ الفاعل «<مورِد>.<فعل>»؟ سؤالٌ عن الفاعل
                  وحده، لا يعرف أيَّ مورِدٍ بعينه.
      ③ نطاق   — وهل هذا المورِدُ **بعينه** في نطاقه؟ OWNER · SELF · ANY.

    وفصلُ ② عن ③ هو ما يمنع فوضى `if role == "admin"`.
    """
    if action not in ACTIONS:
        raise ValueError(f"فعلٌ غير معروف: {action!r}")
    if subject is None:
        subject = ANON
    scope = POLICY.get((resource.type, action))
    if scope is None:
        # المنعُ أصلٌ: مورِدٌ أو فعلٌ جديدٌ بلا قاعدةٍ لا يمرّ لأنه لم يُذكر
        return Decision(False, NO_POLICY, action, resource)

    permission = _p(resource.type, action)

    # ① وثيقة
    if scope is not PUBLIC and not subject.authenticated:
        return Decision(False, UNAUTHENTICATED, action, resource, permission)

    # ② صلاحية — ودورٌ مجهولٌ لا يملك شيئًا، فالنتيجةُ منعٌ لا سماح
    if not subject.has(permission):
        return Decision(False, FORBIDDEN, action, resource, permission)

    # ③ نطاق
    reason = scope(subject, resource)
    return Decision(reason == ALLOWED, reason, action, resource, permission)

def ensure(subject, action, resource):
    """`can` ثمّ يرفع `Denied` عند المنع. هذا ما تناديه طبقةُ الأعمال."""
    d = can(subject, action, resource)
    if not d: raise Denied(d)
    return d

# ───────────────────────── حارسُ التسلسل ─────────────────────────
# ثلاثُ قواعدَ تمنع تصعيدَ الامتياز، مكتوبةٌ **هنا** لا في المعالِجات —
# فمن أضاف مسارَ إدارةٍ جديدًا غدًا ونسيها، سقط في `rbac_test.py`.

SELF_TARGET   = "self_target"     # لا أحدَ يغيّر دورَ نفسه
NOT_GRANTABLE = "not_grantable"   # لا تُمنح صلاحيةٌ لا تملكها
NOT_MANAGEABLE = "not_manageable" # لا تُدار حسابٌ ليس دونك

def may_manage(actor, target_role, target_id=None):
    """أيجوز لهذا الفاعل أن **يُدير** حاملَ هذا الدور؟

    ق١ — لا أحدَ يمسّ نفسَه. تمنع `user → admin`، وتمنع كذلك أن يُسقط
         آخرُ `super_admin` نفسَه فيُقفل النظام. **ولا استثناء لأحد.**
    ق٣ — صلاحياتُ دورِ الهدف يجب أن تكون **مجموعةً جزئيةً حقيقية** من
         صلاحيات الفاعل. فـ`admin` لا يوقف `admin` آخر ولا `super_admin`.
    """
    if target_id is not None and actor.user_id is not None and int(target_id) == actor.user_id:
        return SELF_TARGET
    tp, ap = perms_of(target_role), actor.permissions
    if not (tp < ap):                     # جزئيّةٌ حقيقية: لا تساوي ولا أوسع
        return NOT_MANAGEABLE
    return ALLOWED

def may_grant(actor, new_role):
    """أيجوز له أن يمنح هذا الدور؟

    ق٢ — لا تُمنح صلاحيةٌ لا تملكها: صلاحياتُ الدور الممنوح يجب أن تكون
         مجموعةً جزئيةً من صلاحيات الفاعل. فلا يصنع أحدٌ دورًا أقوى منه.
    """
    if new_role not in ROLES or new_role == "anonymous":
        return NOT_GRANTABLE
    return ALLOWED if perms_of(new_role) <= actor.permissions else NOT_GRANTABLE

# ───────────────────────── تحميلُ المورِد ─────────────────────────
# لكلِّ نوعٍ طريقةٌ واحدةٌ لقراءة مالكه. مكتوبةٌ هنا لا في المسارات، فلا
# يُنسى `AND user_id=?` في موضعٍ ويُذكر في آخر.

def _owner_project(c, pid):
    r = c.execute("SELECT user_id FROM projects WHERE id=?", (pid,)).fetchone()
    return r[0] if r else None

def _owner_item(c, item_id):
    r = c.execute("""SELECT p.user_id FROM project_items i
                     JOIN projects p ON p.id=i.project_id WHERE i.id=?""",
                  (item_id,)).fetchone()
    return r[0] if r else None

def _owner_job(c, jid):
    r = c.execute("SELECT user_id FROM jobs WHERE id=?", (jid,)).fetchone()
    return r[0] if r else None

def _owner_user(c, uid):
    """حسابٌ «مالكُه» هو نفسُه. يُحمَّل ليُعرف أنه موجود، لا ليُقارَن مالكُه —
    فنطاقُ `user.read` و`user.update` هو `ANY`، وحارسُ التسلسل هو المقيِّد."""
    r = c.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone()
    return r[0] if r else None

def _owner_publish_account(c, aid):
    r = c.execute("SELECT user_id FROM publish_accounts WHERE id=?",
                  (aid,)).fetchone()
    return r[0] if r else None

def _owner_schedule(c, sid):
    r = c.execute("SELECT user_id FROM schedules WHERE id=?", (sid,)).fetchone()
    return r[0] if r else None

OWNER_OF = {
    "user":         _owner_user,
    "schedule":     _owner_schedule,
    "publish_account": _owner_publish_account,
    "project":      _owner_project,
    "project_item": _owner_item,
    "job":          _owner_job,
}

def load(c, type, id):
    """يبني مورِدًا بمالكه الحقيقيّ. رقمٌ لا مورِدَ له يعود `exists=False`.

    ولا يُرفع خطأٌ هنا: عدمُ الوجود قرارُ إذنٍ لا عطبُ خادم — و`OWNER`
    يعامله معاملةَ «ليس لك» عمدًا، فلا يُفرَّق بينهما في الردّ.
    """
    if type not in OWNER_OF:
        raise ValueError(f"نوعُ مورِدٍ لا يُحمَّل: {type!r}")
    try:
        rid = int(id)
    except (TypeError, ValueError):
        return Resource(type, id, None, exists=False)
    owner = OWNER_OF[type](c, rid)
    return Resource(type, rid, owner, exists=owner is not None)

def own(type, subject):
    """مورِدٌ مملوكٌ لصاحب الجلسة بحكم تعريفه — لا رقمَ يأتي من العميل.

    مثالُه `/app/projects` و`/app/jobs`: السردُ مقصورٌ على صاحب الجلسة،
    فلا مورِدَ يُحمَّل ولا رقمَ يُصدَّق.
    """
    return Resource(type, subject.user_id, subject.user_id,
                    exists=subject.authenticated)

def public(type="content"):
    return Resource(type, None, None, exists=True)

# ───────────────────────── الملفّات المصدَّرة ─────────────────────────

def export_file(root_dir, rel_path):
    """يشتقّ **مالكَ الملفّ من موضعه** ثم يترك الحكمَ لـ`can`.

    الصادرات تسكن `exports/<رقم المستخدم>/…`، فالمالكُ مقروءٌ من المسار
    بعد `realpath` — أي بعد حلّ كلِّ نقطتين ورابطٍ رمزيّ. وما استقرّ خارج
    `exports/<رقم>/` فلا مالكَ له، فيُمنع.

    وهذا أدقُّ من مقارنةِ المسار بمجلّدي أنا: هناك السؤال «أهذا مجلّدي؟»
    وهنا السؤال «لمن هذا الملفّ؟» — والثاني هو سؤالُ الإذن الصحيح، ويُختبر
    وحده بلا جلسة.
    """
    base = os.path.realpath(os.path.join(root_dir, "exports"))
    full = os.path.realpath(os.path.join(root_dir, rel_path or ""))
    if not full.startswith(base + os.sep):
        return Resource("export_file", None, None, exists=False, path=full)
    seg = full[len(base) + 1:].split(os.sep)
    # لا بدّ من `exports/<رقم>/شيء` — والمجلّد نفسه ليس ملفًّا فيُمنع
    if len(seg) < 2 or not seg[0].isdigit():
        return Resource("export_file", None, None, exists=False, path=full)
    if not os.path.isfile(full):
        return Resource("export_file", None, int(seg[0]), exists=False, path=full)
    return Resource("export_file", full, int(seg[0]), exists=True, path=full)

# ───────────────────────── الأدوار من مصدرها ─────────────────────────

def roles_for(user):
    """أدوارُ صاحب الجلسة — **من القاعدة وحدها**.

    `user` هو صفُّ المستخدم كما قرأته الجلسة، لا شيءٌ جاء من العميل. ولا
    ترويسةَ ولا كعكةَ ولا حقلَ جسمٍ يدخل هنا بحال.

    ودورٌ لا تعرفه `ROLES` (خطأٌ مطبعيّ في القاعدة، أو دورٌ أُسقط من
    الشيفرة وبقي في صفّ) يُعطي **صفرَ صلاحيات** لا صلاحياتِ مستخدم:
    fail closed. ولذلك يُردّ الدورُ كما هو ولا يُستبدل بالافتراضيّ.
    """
    if not user: return frozenset({"anonymous"})
    role = (user.get("role") if isinstance(user, dict) else user["role"]) or ""
    return frozenset({"anonymous", role})

def subject_for(user):
    """الفاعلُ كما تراه طبقةُ الإذن. لا يُبنى إلا من جلسةٍ مُتحقَّقٍ منها."""
    if not user: return ANON
    uid = user["id"] if not isinstance(user, dict) else user.get("id")
    return Subject(uid, roles_for(user))
