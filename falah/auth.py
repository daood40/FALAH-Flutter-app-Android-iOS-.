"""التسجيل والدخول — بالمكتبة القياسية وحدها.

القواعد المطبَّقة هنا:
  • كلمة المرور لا تُحفظ أبدًا؛ يُحفظ اشتقاقُها PBKDF2-SHA256 بملحٍ لكل حساب.
  • رمز الجلسة يُحفظ مجزَّأً؛ من قرأ القاعدة لا يستطيع انتحال جلسة.
  • المقارنة بزمنٍ ثابت، والردّ على «بريد غير مسجَّل» و«كلمة خاطئة» واحد،
    فلا تُستدلّ الحسابات الموجودة من شكل الخطأ.
  • حدُّ محاولات لكل بريدٍ في نافذةٍ زمنية، فلا يُجرَّب الفتح بالتخمين.
"""
import hashlib, hmac, os, re, secrets, sqlite3
from . import store

ITER        = 240_000            # PBKDF2 — يُرفع مع الأجهزة، ويُحفظ مع كل حساب
SESSION_TTL = 30 * 24 * 3600     # شهر
MAX_TRIES   = 8                  # محاولات دخول فاشلة
WINDOW      = 15 * 60            # في ربع ساعة
EMAIL_RE    = re.compile(r"^[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+$")

class AuthError(Exception):
    """خطأ معروض للمستخدم — رسالته عربية ومقصودة."""

# ــــــــــــــــــــ كلمة المرور ــــــــــــــــــــ

def hash_password(pw, salt=None, iters=ITER):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iters)
    return h, salt, iters

def check_password(pw, h, salt, iters):
    calc = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes(salt), iters)
    return hmac.compare_digest(calc, bytes(h))

def password_problem(pw):
    if len(pw or "") < 8:            return "كلمة المرور أقصر من ثمانية أحرف"
    if len(pw) > 200:                return "كلمة المرور أطول مما يلزم"
    if pw.strip() != pw:             return "كلمة المرور تبدأ أو تنتهي بفراغ"
    if pw.lower() in ("password", "12345678", "کلمهسر", "11111111"):
        return "كلمة المرور شائعة جدًّا"
    return None

def normalize_email(email):
    return (email or "").strip().lower()

# ــــــــــــــــــــ حدّ المحاولات ــــــــــــــــــــ

def throttled(c, key, limit=MAX_TRIES, window=WINDOW):
    t = store.now()
    r = c.execute("SELECT count,start FROM throttle WHERE key=?", (key,)).fetchone()
    if r and t - r["start"] < window:
        return r["count"] >= limit
    return False

def bump(c, key, window=WINDOW):
    t = store.now()
    r = c.execute("SELECT count,start FROM throttle WHERE key=?", (key,)).fetchone()
    if r and t - r["start"] < window:
        c.execute("UPDATE throttle SET count=count+1 WHERE key=?", (key,))
    else:
        c.execute("INSERT OR REPLACE INTO throttle(key,count,start) VALUES(?,1,?)", (key, t))

def clear(c, key):
    c.execute("DELETE FROM throttle WHERE key=?", (key,))

# ــــــــــــــــــــ الحسابات ــــــــــــــــــــ

def register(c, email, password, name=None, watermark=None):
    email = normalize_email(email)
    if not EMAIL_RE.match(email):  raise AuthError("صيغة البريد غير صحيحة")
    p = password_problem(password)
    if p:                          raise AuthError(p)
    h, salt, iters = hash_password(password)
    try:
        cur = c.execute("""INSERT INTO users(email,name,watermark,pw_hash,pw_salt,pw_iter,created_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (email, (name or "").strip() or None,
                         (watermark or "").strip() or None, h, salt, iters, store.now()))
    except sqlite3.IntegrityError:
        raise AuthError("هذا البريد مسجَّل من قبل")
    uid = cur.lastrowid
    store.log(c, uid, "register", email)
    c.commit()
    return uid

def login(c, email, password, agent=None):
    email = normalize_email(email)
    key = "login:" + email
    if throttled(c, key):
        raise AuthError("محاولات كثيرة — انتظر ربع ساعة ثم أعد المحاولة")
    u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    # يُحسب الاشتقاق حتى مع بريدٍ غير مسجَّل، كي لا يفرّق زمن الردّ بينهما
    ok = (check_password(password, u["pw_hash"], u["pw_salt"], u["pw_iter"])
          if u else hash_password(password or "x") and False)
    if not u or not ok:
        bump(c, key); store.log(c, u["id"] if u else None, "login_failed", email); c.commit()
        raise AuthError("البريد أو كلمة المرور غير صحيحة")
    if u["status"] != "active":
        raise AuthError("الحساب موقوف")
    clear(c, key)
    token = new_session(c, u["id"], agent)
    c.execute("UPDATE users SET last_login=? WHERE id=?", (store.now(), u["id"]))
    store.log(c, u["id"], "login")
    c.commit()
    return token, dict_user(u)

def change_password(c, user_id, old, new):
    u = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not u or not check_password(old, u["pw_hash"], u["pw_salt"], u["pw_iter"]):
        raise AuthError("كلمة المرور الحالية غير صحيحة")
    p = password_problem(new)
    if p: raise AuthError(p)
    h, salt, iters = hash_password(new)
    c.execute("UPDATE users SET pw_hash=?,pw_salt=?,pw_iter=? WHERE id=?", (h, salt, iters, user_id))
    # تغيير الكلمة يُنهي كل الجلسات القائمة — لا جلسةَ تنجو من كلمةٍ مسروقة
    c.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    store.log(c, user_id, "password_changed")
    c.commit()

def update_profile(c, user_id, name=None, watermark=None):
    c.execute("UPDATE users SET name=COALESCE(?,name), watermark=COALESCE(?,watermark) WHERE id=?",
              ((name or "").strip() or None, (watermark or "").strip() or None, user_id))
    store.log(c, user_id, "profile_updated")
    c.commit()

def dict_user(u):
    """ما يراه العميل عن نفسه. **`role` قراءةٌ فقط**: يُقرأ من القاعدة
    ويُعرض، ولا يُقبل من جسمِ طلبٍ ولا كعكةٍ ولا ترويسةٍ في أيّ مسار."""
    keys = u.keys() if hasattr(u, "keys") else ()
    return {"id": u["id"], "email": u["email"], "name": u["name"],
            "watermark": u["watermark"], "created_at": u["created_at"],
            "role": (u["role"] if "role" in keys else None) or "user"}

# ــــــــــــــــــــ الجلسات ــــــــــــــــــــ

def _hash_token(tok):
    return hashlib.sha256(tok.encode("ascii")).hexdigest()

def new_session(c, user_id, agent=None, ttl=SESSION_TTL):
    tok = secrets.token_urlsafe(32)
    t = store.now()
    c.execute("""INSERT INTO sessions(token_hash,user_id,created_at,expires_at,seen_at,agent)
                 VALUES(?,?,?,?,?,?)""",
              (_hash_token(tok), user_id, t, t + ttl, t, (agent or "")[:200]))
    return tok

def session_user(c, token):
    if not token: return None
    r = c.execute("""SELECT s.token_hash, s.expires_at, u.* FROM sessions s
                     JOIN users u ON u.id=s.user_id WHERE s.token_hash=?""",
                  (_hash_token(token),)).fetchone()
    if not r: return None
    if r["expires_at"] < store.now():
        c.execute("DELETE FROM sessions WHERE token_hash=?", (r["token_hash"],)); c.commit()
        return None
    if r["status"] != "active": return None
    c.execute("UPDATE sessions SET seen_at=? WHERE token_hash=?", (store.now(), r["token_hash"]))
    c.commit()
    return dict_user(r)

def logout(c, token):
    if token:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))
        c.commit()

def purge_expired(c):
    n = c.execute("DELETE FROM sessions WHERE expires_at<?", (store.now(),)).rowcount
    c.commit(); return n


def delete_account(c, user_id, export_dir=None):
    """حذفٌ لا رجعة فيه: المستخدم وجلساته ومشاريعه وعناصرها وصادراته وسجلّه.
    وما صُدِّر من ملفاتٍ يُمحى من القرص كذلك، فلا يبقى أثرٌ للحساب.
    النصوص الشرعية في قاعدة المحتوى ليست ملكًا لحساب، فلا تُمسّ."""
    rows = c.execute("SELECT path FROM exports WHERE user_id=?", (user_id,)).fetchall()
    pids = [r[0] for r in c.execute("SELECT id FROM projects WHERE user_id=?", (user_id,))]
    if pids:
        q = ",".join("?" * len(pids))
        c.execute(f"DELETE FROM project_items WHERE project_id IN ({q})", pids)
    # ــــ جداولُ الحساب بالاسم، واحدًا واحدًا ــــ
    #
    # كان هنا `try/except pass` على قائمةٍ من خمسةِ جداول، وهو أسوأُ شكلٍ
    # للخطأ: ينجح الحذفُ ظاهرًا ويترك وراءه `publish_accounts` وفيه **رمزُ
    # بوتِ تلغرام مغلَّفًا** — سرُّ حسابٍ خارجيٍّ لمن حذف حسابَه وظنّ أنه
    # انصرف. ويترك `receipts` و`subscriptions` و`schedules` و`tokens`
    # و`usage`. والصمتُ كان يضمن ألّا يُعرف: جدولٌ نُسي لا يرفع صوتًا.
    #
    # فلا `except` بعد اليوم. وجدولٌ زال أو تغيّر عمودُه يُسقط الحذفَ بصوتٍ
    # عالٍ — لأنّ حذفًا ناقصًا صامتًا أسوأُ من حذفٍ يفشل ويُصلَح.
    email = (c.execute("SELECT email FROM users WHERE id=?",
                       (user_id,)).fetchone() or [""])[0]

    # تشغيلاتُ الجدولة تُعرف بجدولها لا بصاحبها — فتُحذف قبل أن يزول الأب
    c.execute("""DELETE FROM schedule_runs WHERE schedule_id IN
                 (SELECT id FROM schedules WHERE user_id=?)""", (user_id,))
    for t in ("schedules",
              "publish_attempts", "publish_accounts",   # النشر — وفيه سرٌّ
              "exports", "projects",
              "receipts", "subscriptions", "usage",     # المال والحصص
              "referral_codes",
              "jobs", "tokens", "sessions", "events"):
        c.execute(f"DELETE FROM {t} WHERE user_id=?", (user_id,))  # noqa: S608
    # الإحالةُ طرفان، وكلاهما عمودٌ قائمٌ بذاته
    c.execute("DELETE FROM referrals WHERE referrer_id=? OR invitee_id=?",
              (user_id, user_id))
    # ومفتاحُ كبح المحاولات بالبريد لا بالمعرِّف — ولولا حذفُه لبقي البريدُ
    # مكتوبًا في القاعدة بعد زوال صاحبه
    if email:
        c.execute("DELETE FROM throttle WHERE key IN (?,?)",
                  ("login:" + email, "reset:" + email))
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    c.commit()
    removed = 0
    if export_dir:
        # الحدُّ مجلّدُ صاحب الحساب وحده — لا جذرُ المشروع.
        #
        # كان `export_dir` يُمرَّر جذرَ المشروع، فلو صار في `exports.path`
        # سطرٌ منحرفٌ يومًا لأمكن أن يُحذف به `app.py` أو `falah.db`. ولا
        # يُحتجّ بأن السطر يكتبه الخادم: الحدُّ يُرسم على أضيق ما يكفي، لا
        # على أوسع ما يُظنّ آمنًا اليوم.
        #
        # و`realpath` لا `abspath`: الثانية لا تحلّ الوصلات الرمزية، فوصلةٌ
        # داخل `exports` تشير خارجها كانت تمرّ.
        root = os.path.realpath(os.path.join(export_dir, "exports", str(user_id)))
        for r in rows:
            p = os.path.realpath(os.path.join(export_dir, str(r[0]).lstrip("/")))
            if (p == root or p.startswith(root + os.sep)) and os.path.isfile(p):
                try: os.remove(p); removed += 1
                except OSError: pass
        # والمجلّد نفسه يُطوى إن خلا — لا تبقى أصدافٌ فارغة
        try:
            for dirpath, dirnames, files in os.walk(root, topdown=False):
                if not files and not os.listdir(dirpath): os.rmdir(dirpath)
        except OSError:
            pass
    return {"projects": len(pids), "files": removed}


# ــــــــــــــــــــ رموز الاستعادة والتأكيد ــــــــــــــــــــ
# الرمز يُخزَّن مجزَّأً كرمز الجلسة: من قرأ القاعدة لا يستعيد به حسابًا.

RESET_TTL  = 3600           # ساعة
VERIFY_TTL = 2 * 86400      # يومان

def issue_token(c, user_id, kind, ttl):
    tok = secrets.token_urlsafe(32)
    t = store.now()
    # رمزٌ واحدٌ نافذ لكل نوع: إصدار جديدٍ يُبطل ما قبله
    c.execute("DELETE FROM tokens WHERE user_id=? AND kind=?", (user_id, kind))
    c.execute("""INSERT INTO tokens(token_hash,user_id,kind,created_at,expires_at)
                 VALUES(?,?,?,?,?)""", (_hash_token(tok), user_id, kind, t, t + ttl))
    c.commit()
    return tok

def use_token(c, tok, kind):
    """يُستهلك مرّةً واحدة. المنتهي والمستعمَل سواءٌ في الرفض."""
    r = c.execute("SELECT * FROM tokens WHERE token_hash=? AND kind=?",
                  (_hash_token(tok or ""), kind)).fetchone()
    if not r or r["used_at"] or r["expires_at"] < store.now():
        raise AuthError("رمزٌ منتهٍ أو مستعمَل — اطلب رمزًا جديدًا")
    c.execute("UPDATE tokens SET used_at=? WHERE token_hash=?", (store.now(), r["token_hash"]))
    c.commit()
    return r["user_id"]

def request_reset(c, email, send=True):
    """لا يُفصح عن وجود البريد من عدمه — الردّ واحدٌ في الحالين.
    ويُحدّ الطلب حتى لا يُستعمل الخادمُ لإغراق صندوقٍ ببريد."""
    email = normalize_email(email)
    key = "reset:" + email
    if throttled(c, key, limit=5, window=3600):
        raise AuthError("طلباتٌ كثيرة — انتظر ساعة")
    bump(c, key, window=3600)
    u = c.execute("SELECT id,email FROM users WHERE email=? AND status='active'",
                  (email,)).fetchone()
    out = {"ok": True}
    if u:
        tok = issue_token(c, u["id"], "reset", RESET_TTL)
        store.log(c, u["id"], "reset_requested")
        if send:
            from . import mailer
            out["mail"] = mailer.reset_mail(u["email"], tok)
        out["_token"] = tok           # لا يُعاد إلى العميل — للاختبارات وحدها
    return out

def reset_password(c, token, new_password):
    p = password_problem(new_password)
    if p: raise AuthError(p)
    uid = use_token(c, token, "reset")
    h, salt, iters = hash_password(new_password)
    c.execute("UPDATE users SET pw_hash=?, pw_salt=?, pw_iter=? WHERE id=?",
              (h, salt, iters, uid))
    # كل جلسةٍ قائمة تسقط: من سرق جلسةً لا يبقى له بابٌ بعد الاستعادة
    c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    c.commit()
    store.log(c, uid, "reset_done")
    return uid

def request_verify(c, user_id, send=True):
    u = c.execute("SELECT id,email,verified_at FROM users WHERE id=?", (user_id,)).fetchone()
    if not u: raise AuthError("لا حساب")
    if u["verified_at"]: return {"ok": True, "already": True}
    tok = issue_token(c, user_id, "verify", VERIFY_TTL)
    out = {"ok": True, "_token": tok}
    if send:
        from . import mailer
        out["mail"] = mailer.verify_mail(u["email"], tok)
    return out

def verify_email(c, token):
    uid = use_token(c, token, "verify")
    c.execute("UPDATE users SET verified_at=? WHERE id=?", (store.now(), uid))
    c.commit()
    store.log(c, uid, "email_verified")
    return uid
