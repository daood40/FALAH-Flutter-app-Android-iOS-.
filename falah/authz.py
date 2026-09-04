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
# أسماءٌ لا أدوار. الدورُ حزمةُ صلاحيات، والشرطُ يُكتب على الصلاحية —
# فتُضاف أدوارُ P1.2 (moderator · admin · super_admin) بتوسيع هذا الجدول
# وحده، ولا يُمسّ موضعُ نداءٍ واحد.
PERMISSIONS = frozenset({
    "manage_billing",        # منحُ الاشتراكات وقبولُ إيصالٍ موثوق
    "manage_users", "manage_roles", "view_audit_log",
    "manage_system_settings", "manage_content", "manage_exports",
})

# دورُ اليوم الوحيد. في P1.1 يمنحه المفتاحُ الإداريّ كما كان تمامًا،
# وفي P1.2 يُقرأ من جدولٍ في القاعدة — والفرقُ عند المنح لا عند الفحص.
ROLES = {
    "system_admin": frozenset(PERMISSIONS),
}

class Subject:
    """من يطلب. لا يُبنى من حمولةِ طلبٍ أبدًا — بل من جلسةٍ مُتحقَّقٍ منها."""
    __slots__ = ("user_id", "roles")

    def __init__(self, user_id=None, roles=()):
        self.user_id = int(user_id) if user_id is not None else None
        self.roles = frozenset(roles)

    @property
    def authenticated(self):
        return self.user_id is not None

    def has(self, permission):
        return any(permission in ROLES.get(r, ()) for r in self.roles)

    def __repr__(self):
        return f"Subject(user={self.user_id}, roles={sorted(self.roles) or '—'})"

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
    __slots__ = ("allowed", "reason", "resource", "action")

    def __init__(self, allowed, reason, action=None, resource=None):
        self.allowed, self.reason = allowed, reason
        self.action, self.resource = action, resource

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

# ───────────────────────── الشروط ─────────────────────────
# كلُّ شرطٍ دالّة: (subject, resource) → سببٌ أو ALLOWED.

def PUBLIC(s, r):
    return ALLOWED

def AUTHENTICATED(s, r):
    return ALLOWED if s.authenticated else UNAUTHENTICATED

def OWNER(s, r):
    """جوهرُ منع IDOR: جلسةٌ أوّلًا، ثم وجودٌ، ثم تطابقُ مالكٍ **محمَّل**."""
    if not s.authenticated:                  return UNAUTHENTICATED
    if not r.exists or r.owner_id is None:   return NOT_FOUND
    if r.owner_id != s.user_id:              return NOT_FOUND
    return ALLOWED

def NEEDS(permission):
    """صلاحيةٌ مسمّاة. تُكتب على الصلاحية لا على الدور — انظر رأس الملفّ."""
    def check(s, r):
        if not s.authenticated:  return UNAUTHENTICATED
        return ALLOWED if s.has(permission) else FORBIDDEN
    check.__name__ = f"NEEDS({permission})"
    return check

def SELF(s, r):
    """مورِدٌ هو صاحبُ الجلسة نفسه: حسابُه، اشتراكُه، إحالاتُه."""
    if not s.authenticated: return UNAUTHENTICATED
    if r.id is not None and int(r.id) != s.user_id: return NOT_FOUND
    return ALLOWED

# ───────────────────────── جدول السياسة ─────────────────────────
# (نوعُ المورِد، الفعل) → الشرط. وما ليس هنا ممنوع.

POLICY = {
    # المحتوى العامّ — قراءةٌ بلا حساب، وهي طبيعةُ المشروع لا ثغرةٌ فيه
    ("content",      "read"):     PUBLIC,
    ("content",      "list"):     PUBLIC,
    ("catalogue",    "read"):     PUBLIC,     # الخطط وإعدادُ العميل و«من أنا»
    ("service",      "read"):     PUBLIC,     # الحياة والجاهزية

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

    # الملفّات المصدَّرة
    ("export",       "list"):     AUTHENTICATED,
    ("export_file",  "download"): OWNER,

    # الحساب وما يتعلّق به
    ("account",      "read"):     SELF,
    ("account",      "update"):   SELF,
    ("account",      "delete"):   SELF,
    ("subscription", "read"):     SELF,
    ("subscription", "update"):   SELF,       # الإلغاء وإيصالُ المتجر
    ("subscription", "grant"):    NEEDS("manage_billing"),
    ("referral",     "read"):     SELF,
    ("agent",        "read"):     AUTHENTICATED,
    ("agent",        "create"):   AUTHENTICATED,
    ("limits",       "read"):     AUTHENTICATED,   # حدودُ الطابور المعلَنة

    # مسارُ تطبيقٍ لم يُعلَن. وثيقةٌ أوّلًا ثم ٤٠٤ من معالِجه — وهو ترتيبُ
    # اليوم نفسُه: `if not u: 401` كان يسبق «مسار غير معروف».
    ("unknown",      "read"):     AUTHENTICATED,
}

def can(subject, action, resource):
    """أيجوز لـ`subject` أن يفعل `action` بـ`resource`؟

    نداءٌ صافٍ: لا يلمس قاعدةً ولا شبكة. المورِدُ يصل محمَّلًا ومالكُه
    مقروء — انظر `load` أدناه. وهذا الفصلُ مقصود: القرارُ يُختبر وحده.
    """
    if action not in ACTIONS:
        raise ValueError(f"فعلٌ غير معروف: {action!r}")
    if subject is None:
        subject = ANON
    rule = POLICY.get((resource.type, action))
    if rule is None:
        # المنعُ أصلٌ: مورِدٌ أو فعلٌ جديدٌ بلا قاعدةٍ لا يمرّ لأنه لم يُذكر
        return Decision(False, NO_POLICY, action, resource)
    reason = rule(subject, resource)
    return Decision(reason == ALLOWED, reason, action, resource)

def ensure(subject, action, resource):
    """`can` ثمّ يرفع `Denied` عند المنع. هذا ما تناديه طبقةُ الأعمال."""
    d = can(subject, action, resource)
    if not d: raise Denied(d)
    return d

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

OWNER_OF = {
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

def roles_for(user_id, *, admin_key_ok=False):
    """أدوارُ صاحب الجلسة. في P1.1 مصدرٌ واحد: المفتاحُ الإداريّ — كما كان
    حرفًا بحرف. وP1.2 يضيف قراءةً من القاعدة هنا، ولا شيءَ غير هذا يتغيّر.
    """
    return frozenset({"system_admin"}) if admin_key_ok else frozenset()

def subject_for(user_id, *, admin_key_ok=False):
    return Subject(user_id, roles_for(user_id, admin_key_ok=admin_key_ok))
