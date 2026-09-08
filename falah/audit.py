"""سجلّ التدقيق — مَن فعل، وماذا، وعلى مَن، وبأيّ نتيجة.

غيرُ `store.log`: ذاك سجلٌّ عامٌّ خفيف (`user_id, action, detail`) يخدم
عرضَ نشاطِ صاحبِ الحساب. وهذا سجلٌّ **أمنيّ**: يحمل الفاعلَ ودورَه لحظةَ
الفعل، والمورِدَ الذي مُسّ، والنتيجة، والعنوان، ورقمَ الطلب. والفرقُ
عمليّ: من `events` لا تعرف مَن أوقف حسابًا ولا هل نجح؛ من هذا تعرف.

ثلاثُ قواعدَ تحكمه:

  ١. **كتالوجٌ مغلق.** حدثٌ ليس في `ACTIONS` يرفع `ValueError`. فلا ينمو
     السجلُّ بلا حساب، ولا يُسجَّل كلُّ شيءٍ عشوائيًّا فيصير ضجيجًا لا يُقرأ.

  ٢. **لا سرَّ فيه أبدًا.** المصفاةُ أدناه تُسقط كلَّ مفتاحٍ يشبه سرًّا،
     وتُسقط أيَّ قيمةٍ طويلةٍ تشبه رمزًا. وهي في الشيفرة لا في وعدِ وثيقة،
     ويفتّشها `rbac_test.py` بسرٍّ معروفٍ سلفًا.

  ٣. **يُلحَق ولا يُعدَّل.** المنعُ في القاعدة نفسها بمُشغِّلين يُجهضان
     `UPDATE` و`DELETE` — لا في التطبيق وحده. والتصحيحُ حدثٌ جديد.

وحدُّ هذا صريح: من يملك ملفَّ `app.db` على القرص يملك أن يُسقط المُشغِّل.
الحمايةُ من التطبيق ومن مستعمليه، لا من مالك الخادم.
"""
import json, re, secrets

from . import store

# ───────────────────────── الكتالوج المغلق ─────────────────────────

ACTIONS = frozenset({
    # المصادقة
    "login.success", "login.failure", "logout",
    # الحساب
    "account.created", "account.updated", "account.deleted",
    "password.changed", "password.reset",
    # الأدوار والإدارة
    "role.changed", "user.suspended", "user.reactivated",
    # الفوترة
    "subscription.granted", "subscription.canceled", "subscription.store_event",
    # العمل
    "project.created", "project.deleted",
    "export.created", "export.failed", "export.completed",
    # الأمن والقراءة الإدارية
    "security.denied", "audit.read",
})

RESULTS = frozenset({"success", "failure", "denied"})

# ───────────────────────── مصفاةُ الأسرار ─────────────────────────
# تُسقط بالاسم، ثم بالشكل. والإسقاطُ **حذفٌ تامّ** لا استبدالٌ بنجومٍ تحكي
# طولَ السرّ.

SECRET_KEY = re.compile(
    r"(pass|pwd|secret|token|cookie|session|auth|api[_-]?key|credential|"
    r"salt|hash|signature|receipt|payload|private)", re.I)

# قيمةٌ طويلةٌ من محارف الرموز: تشبه رمزًا حتى لو كان مفتاحُها بريئًا
TOKENISH = re.compile(r"^[A-Za-z0-9_\-+/=]{24,}$")

MAX_VALUE = 200

def scrub(meta):
    """يُعيد نسخةً آمنةً من `metadata`. ما شكَّ فيه أسقطه."""
    if not isinstance(meta, dict): return {}
    out = {}
    for k, v in meta.items():
        if SECRET_KEY.search(str(k)):       continue
        if isinstance(v, (dict, list)):     continue      # لا عمقَ ولا حمولاتٌ خام
        if v is None or isinstance(v, bool) or isinstance(v, int):
            out[str(k)[:40]] = v; continue
        sv = str(v)
        if TOKENISH.match(sv):              continue
        out[str(k)[:40]] = sv[:MAX_VALUE]
    return out

def new_request_id():
    """معرّفٌ قصيرٌ لكل طلب. الحدُّ الأدنى الذي يحتاجه التدقيق — ولا يُبنى
    عليه شيءٌ من مراقبة P1.3، ولا يخرج في ترويسةِ ردّ (فذلك تغييرُ عقد)."""
    return secrets.token_hex(8)

# ───────────────────────── الكتابة ─────────────────────────

def record(c, action, *, result="success", actor_id=None, actor_role=None,
           resource_type=None, resource_id=None, ip=None, user_agent=None,
           request_id=None, metadata=None, commit=True):
    """يكتب سطرًا. حدثٌ خارج الكتالوج خطأُ برمجةٍ يُرفع، لا يُبتلع.

    ولا يُبتلع خطأُ الكتابة كذلك: إن تعذّر تسجيلُ فعلٍ حسّاسٍ فالأولى أن
    يُعرف. ومن أراد ألّا يُسقط فعلًا بسبب سجلٍّ فليستعمل `try_record`،
    وهو مقصورٌ على ما ليس فعلًا حسّاسًا.
    """
    if action not in ACTIONS:
        raise ValueError(f"حدثُ تدقيقٍ خارج الكتالوج: {action!r}")
    if result not in RESULTS:
        raise ValueError(f"نتيجةٌ غير معروفة: {result!r}")
    c.execute("""INSERT INTO audit_logs(at,request_id,actor_id,actor_role,action,
                                        resource_type,resource_id,result,ip,
                                        user_agent,metadata)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (store.now(), request_id, actor_id, actor_role, action,
               resource_type, None if resource_id is None else str(resource_id)[:80],
               result, (ip or None) and str(ip)[:64],
               (user_agent or None) and str(user_agent)[:200],
               json.dumps(scrub(metadata), ensure_ascii=False) if metadata else None))
    if commit: c.commit()

def try_record(c, action, **kw):
    """كتابةٌ لا تُسقط الطلبَ إن فشلت. لِما ليس فعلًا حسّاسًا وحده."""
    try:    record(c, action, **kw)
    except ValueError: raise            # خطأُ برمجةٍ يبقى مرئيًّا
    except Exception:  pass

def from_request(rq, action, **kw):
    """يكتب حدثًا بسياق الطلب — فلا يُنسى عنوانٌ ولا وكيلٌ ولا رقمُ طلب."""
    kw.setdefault("actor_id", rq.subject.user_id)
    kw.setdefault("actor_role", rq.subject.role)
    kw.setdefault("ip", rq.client_ip)
    kw.setdefault("user_agent", rq.get_header("User-Agent", ""))
    kw.setdefault("request_id", rq.request_id)
    record(rq.c, action, **kw)

# ───────────────────────── القراءة ─────────────────────────

FIELDS = ("id", "at", "request_id", "actor_id", "actor_role", "action",
          "resource_type", "resource_id", "result", "ip", "user_agent", "metadata")

def listing(c, *, limit=50, offset=0, action=None, actor_id=None, result=None):
    """أحدثُ الأحداث. مفلترةٌ باستعلاماتٍ مُعامَلة — لا تركيبَ نصّ."""
    where, args = ["1=1"], []
    if action:            where.append("action=?");   args.append(action)
    if actor_id is not None: where.append("actor_id=?"); args.append(int(actor_id))
    if result:            where.append("result=?");   args.append(result)
    lim = max(1, min(int(limit or 50), 200)); off = max(0, int(offset or 0))
    sql = "FROM audit_logs WHERE " + " AND ".join(where)
    total = c.execute("SELECT COUNT(*) " + sql, args).fetchone()[0]
    rows = c.execute(f"SELECT {','.join(FIELDS)} " + sql
                     + " ORDER BY at DESC, id DESC LIMIT ? OFFSET ?",
                     args + [lim, off]).fetchall()
    return {"total": total, "limit": lim, "offset": off,
            "events": [dict(r) for r in rows]}
