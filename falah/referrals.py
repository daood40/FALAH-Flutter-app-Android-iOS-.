"""الإحالات — دعوةٌ تُكافأ بعد عملٍ حقيقيّ لا بعد تسجيلٍ فارغ.

القاعدة: **لا تُصرف مكافأةٌ على اسمٍ في جدول.** المدعوّ يُحسب حين يُنتج
شيئًا فعلًا (بطاقة تجاوزت الفحص)، لا حين يملأ استمارة. هذا يقطع أكثر
الحيل شيوعًا: حساباتٌ تُفتح لتُحصد.

وثلاثة أبوابٍ مغلقة: لا يحيل أحدٌ نفسه، ولا يُحال المرءُ مرّتين، ولا
يتجاوز المحيلُ سقفًا شهريًّا — فمن تجاوزه فأمرُه إلى مراجعةٍ بشرية لا إلى
منعٍ صامت.
"""
import hashlib, os, secrets, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from falah import store, billing

ALPHABET   = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # بلا حروفٍ تلتبس بالأرقام
CODE_LEN   = 7
REWARD_DAYS   = 14          # للمحيل عن كل مدعوٍّ استحقّ
INVITEE_DAYS  = 14          # وللمدعوّ نفسه، من لحظة التسجيل
REWARD_PLAN   = "creator"
MONTHLY_CAP   = 20          # سقف المكافآت الشهرية للمحيل الواحد

class ReferralError(Exception): pass

# ───────────────────────── الرمز ─────────────────────────

def code_for(c, user_id):
    """رمز المستخدم — يُنشأ مرّةً ويبقى."""
    r = c.execute("SELECT code FROM referral_codes WHERE user_id=?", (user_id,)).fetchone()
    if r: return r["code"]
    for _ in range(24):
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
        try:
            c.execute("INSERT INTO referral_codes(code,user_id,created_at) VALUES(?,?,?)",
                      (code, user_id, store.now()))
            c.commit(); return code
        except Exception:
            continue                      # تصادمٌ نادر — يُعاد الاختيار
    raise ReferralError("تعذّر توليد رمز")

def owner_of(c, code):
    r = c.execute("SELECT user_id FROM referral_codes WHERE code=?",
                  ((code or "").strip().upper(),)).fetchone()
    return r["user_id"] if r else None

# ───────────────────────── التسجيل بالإحالة ─────────────────────────

def attach(c, invitee_id, code):
    """يربط مدعوًّا برمزٍ عند التسجيل. لا يصرف شيئًا للمحيل بعد."""
    code = (code or "").strip().upper()
    if not code: return None
    ref = owner_of(c, code)
    if ref is None:
        raise ReferralError("رمز الدعوة غير معروف")
    if ref == invitee_id:
        raise ReferralError("لا يُحيل المرء نفسه")
    if c.execute("SELECT 1 FROM referrals WHERE invitee_id=?", (invitee_id,)).fetchone():
        raise ReferralError("هذا الحساب محالٌ من قبل")
    c.execute("""INSERT INTO referrals(code,referrer_id,invitee_id,status,created_at)
                 VALUES(?,?,?,'pending',?)""", (code, ref, invitee_id, store.now()))
    c.commit()
    # المدعوّ يأخذ حقّه فورًا — هو لم يُحتَل عليه، وهو الذي جاء
    billing.grant(c, invitee_id, REWARD_PLAN, days=INVITEE_DAYS,
                  provider="referral", note=f"دعوة {code}")
    store.log(c, invitee_id, "referral_joined", code)
    store.log(c, ref, "referral_pending", str(invitee_id))
    return {"referrer_id": ref, "code": code, "invitee_days": INVITEE_DAYS}

def qualify(c, invitee_id, reason="أنتج بطاقةً مفحوصة"):
    """يُستدعى حين يُنجز المدعوّ عملًا حقيقيًّا. هنا وحدها تُصرف المكافأة."""
    r = c.execute("SELECT * FROM referrals WHERE invitee_id=? AND status='pending'",
                  (invitee_id,)).fetchone()
    if not r: return None
    t = store.now()
    month_start = t - 30 * 86400
    n = c.execute("""SELECT COUNT(*) FROM referrals WHERE referrer_id=?
                     AND status='rewarded' AND rewarded_at>?""",
                  (r["referrer_id"], month_start)).fetchone()[0]
    if n >= MONTHLY_CAP:
        # لا يُمنع صامتًا: يُعلَّق ويُعرض على المراجعة، فقد يكون داعيةً حقًّا
        c.execute("UPDATE referrals SET status='qualified', qualified_at=?, reason=? WHERE id=?",
                  (t, f"بلغ السقف الشهري ({MONTHLY_CAP}) — بانتظار مراجعة", r["id"]))
        c.commit()
        store.log(c, r["referrer_id"], "referral_capped", str(invitee_id))
        return {"status": "qualified", "capped": True}
    c.execute("UPDATE referrals SET status='rewarded', qualified_at=?, rewarded_at=?, reason=? "
              "WHERE id=?", (t, t, reason, r["id"]))
    c.commit()
    billing.grant(c, r["referrer_id"], REWARD_PLAN, days=REWARD_DAYS,
                  provider="referral", note=f"إحالة {invitee_id}")
    store.log(c, r["referrer_id"], "referral_rewarded", f"{invitee_id}:{REWARD_DAYS}d")
    return {"status": "rewarded", "days": REWARD_DAYS, "referrer_id": r["referrer_id"]}

def reject(c, referral_id, reason):
    """رفضٌ يدويّ عند ثبوت التحايل — ويُسحب ما مُنح إن كان قد مُنح."""
    r = c.execute("SELECT * FROM referrals WHERE id=?", (referral_id,)).fetchone()
    if not r: raise ReferralError("لا إحالة بهذا الرقم")
    c.execute("UPDATE referrals SET status='rejected', reason=? WHERE id=?", (reason, referral_id))
    c.commit()
    store.log(c, r["referrer_id"], "referral_rejected", f"{r['invitee_id']}:{reason}")
    return True

# ───────────────────────── العرض ─────────────────────────

def summary(c, user_id):
    code = code_for(c, user_id)
    rows = c.execute("""SELECT r.status, r.created_at, r.rewarded_at, u.name, u.email
                        FROM referrals r LEFT JOIN users u ON u.id=r.invitee_id
                        WHERE r.referrer_id=? ORDER BY r.created_at DESC LIMIT 100""",
                     (user_id,)).fetchall()
    counts = {"pending": 0, "qualified": 0, "rewarded": 0, "rejected": 0}
    for r in rows: counts[r["status"]] = counts.get(r["status"], 0) + 1
    base = os.environ.get("FALAH_ORIGIN", "").rstrip("/")
    return {
        "code": code,
        "link": (base + "/?ref=" + code) if base else ("?ref=" + code),
        "counts": counts,
        "days_earned": counts["rewarded"] * REWARD_DAYS,
        "reward_days": REWARD_DAYS, "invitee_days": INVITEE_DAYS,
        "reward_plan": billing.plan_of(REWARD_PLAN)["name"],
        "cap": MONTHLY_CAP,
        "rule": "تُصرف المكافأة حين يُنتج المدعوّ بطاقةً مفحوصة، لا عند تسجيله.",
        "invites": [{"status": r["status"],
                     # لا يُكشف بريدٌ كامل لأحد: أوّلُه وحده يكفي للتعرّف
                     "who": (r["name"] or (r["email"] or "")[:3] + "…"),
                     "at": r["created_at"], "rewarded_at": r["rewarded_at"]} for r in rows],
    }
