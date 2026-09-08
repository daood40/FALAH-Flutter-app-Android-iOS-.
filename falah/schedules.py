"""الجدولة — في الخادم لا في العميل، وبإسنادٍ إلى الطابور القائم.

**لماذا الخادم؟** مؤقّتٌ داخل التطبيق يموت بإغلاقه، ولا يعمل والهاتفُ
نائم، ويختلف توقيتُه بين جهازٍ وجهاز، ويتضاعف إن فُتح التطبيقُ على جهازين.
فالحالةُ هنا، والعاملُ ينفّذ.

**ولماذا اسمُ منطقةٍ لا إزاحة؟** الإزاحةُ تتغيّر بالتوقيت الصيفيّ: من جدول
«كلَّ يومٍ ٦ صباحًا» بإزاحةٍ محفوظةٍ استيقظ على ٥ أو ٧ بعد التحويل. واسمُ
المنطقة يبقى صحيحًا عبرها.

**والتنفيذُ لا يُضاعَف:** لكلِّ تشغيلٍ مفتاحُ تفرّدٍ مشتقٌّ من (الجدول،
اللحظة المستحقّة). تشغيلان متزامنان للكانس لا يُنشئان مهمّتين — القيدُ
الفريدُ في `schedule_runs` يمنع الثانية، ولا يُعتمد على قفلٍ في التطبيق.

والحصّةُ والصلاحيةُ تُفحصان **عند التنفيذ لا عند الإنشاء**: قد يجدول
مستخدمٌ اليومَ وتنتهي خطّتُه غدًا، فالجدولُ لا يمنح حقًّا لا يملكه.
"""
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from falah import jobs as JB
from falah import obs
from falah import store

RECURRENCE = ("once", "daily", "weekly", "monthly")
STATUS = ("active", "paused", "done", "failed")
KINDS = ("export", "video")

# سقفُ ما يملكه مستخدمٌ من جداولَ نشطة. يمنع أن يصير الجدولُ بابًا خلفيًّا
# لتجاوز حدِّ المعدّل: ألفُ جدولٍ في الدقيقة نفسِها = ألفُ مهمّة.
MAX_ACTIVE_PER_USER = 20


class ScheduleError(Exception):
    """خطأُ نطاقٍ — يترجمه `routing.DOMAIN_ERRORS` إلى ٤٠٠ برسالةٍ عربية."""


# ــــــــــــــــــــ حسابُ الاستحقاق ــــــــــــــــــــ

def _zone(tz):
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ScheduleError(f"منطقةٌ زمنيّةٌ غير معروفة: {tz}") from None


def next_run(recurrence, tz, at_minute, day_of, after=None):
    """اللحظةُ التالية بعد `after` — ثوانيَ منذ الحقبة، أو `None` لمنتهٍ.

    يُحسب في المنطقة المحلّية ثم يُحوَّل: هذا هو الفرقُ الذي يجعل «٦ صباحًا»
    تبقى ٦ صباحًا بعد التوقيت الصيفيّ.
    """
    if recurrence not in RECURRENCE:
        raise ScheduleError("تكرارٌ غير معروف")
    if not (0 <= int(at_minute) < 1440):
        raise ScheduleError("الوقتُ خارج اليوم")

    z = _zone(tz)
    now = datetime.fromtimestamp(after if after is not None else time.time(), z)
    h, m = divmod(int(at_minute), 60)
    today = now.replace(hour=h, minute=m, second=0, microsecond=0)

    if recurrence == "once":
        # مرّةً واحدةً: إن مضى وقتُها فلا تالية
        return int(today.timestamp()) if today > now else None

    if recurrence == "daily":
        t = today if today > now else today + timedelta(days=1)
        return int(t.timestamp())

    if recurrence == "weekly":
        want = int(day_of if day_of is not None else 0) % 7   # ٠=الاثنين
        t = today
        # حتّى سبعِ خطواتٍ: أوّلُ يومٍ مطابقٍ يقع بعد الآن
        for _ in range(8):
            if t.weekday() == want and t > now:
                return int(t.timestamp())
            t += timedelta(days=1)
        return None

    # monthly — يُقصر اليومُ على ٢٨ فلا يسقط في شباط
    want = max(1, min(28, int(day_of if day_of is not None else 1)))
    t = today.replace(day=want)
    if t <= now:
        t = (t.replace(day=1) + timedelta(days=32)).replace(
            day=want, hour=h, minute=m, second=0, microsecond=0)
    return int(t.timestamp())


# ــــــــــــــــــــ العمليات ــــــــــــــــــــ

def _row(r):
    d = dict(r)
    d["due_in_s"] = (d["next_run_at"] - store.now()) if d["next_run_at"] else None
    return d


def create(c, user_id, project_id, *, kind="export", title="",
           recurrence="once", tz="UTC", at_minute=0, day_of=None):
    """يُنشئ جدولًا. **الملكيّةُ تُفحص هنا**: مشروعُ غيرِك لا يُجدوَل."""
    if kind not in KINDS:
        raise ScheduleError("نوعٌ غير مدعوم")
    owner = c.execute("SELECT user_id FROM projects WHERE id=?",
                      (project_id,)).fetchone()
    # «ليس لك» ≡ «غير موجود» — كما في بقيّة النظام، فلا يُكشف وجودُ مورِد
    if not owner or owner["user_id"] != user_id:
        raise ScheduleError("المشروع غير موجود")

    n = c.execute("SELECT COUNT(*) FROM schedules WHERE user_id=? AND status='active'",
                  (user_id,)).fetchone()[0]
    if n >= MAX_ACTIVE_PER_USER:
        raise ScheduleError(f"بلغتَ حدَّ {MAX_ACTIVE_PER_USER} جدولًا نشطًا")

    nxt = next_run(recurrence, tz, at_minute, day_of)
    if nxt is None:
        raise ScheduleError("الوقتُ المطلوب مضى — اختر وقتًا قادمًا")

    t = store.now()
    cur = c.execute(
        """INSERT INTO schedules(user_id,project_id,kind,title,recurrence,tz,
                                 at_minute,day_of,status,next_run_at,
                                 created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,'active',?,?,?)""",
        (user_id, project_id, kind, (title or "")[:120], recurrence, tz,
         int(at_minute), day_of, nxt, t, t))
    c.commit()
    obs.info("schedule.create", schedule_id=cur.lastrowid,
             recurrence=recurrence, kind=kind)
    obs.M.inc("schedules_created_total", recurrence=recurrence, kind=kind)
    return get(c, user_id, cur.lastrowid)


def get(c, user_id, sid):
    r = c.execute("SELECT * FROM schedules WHERE id=? AND user_id=?",
                  (sid, user_id)).fetchone()
    if not r:
        raise ScheduleError("الجدول غير موجود")
    return _row(r)


def listing(c, user_id, limit=50):
    return [_row(r) for r in c.execute(
        "SELECT * FROM schedules WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, min(int(limit), 200)))]


def update(c, user_id, sid, **kw):
    """تعديلٌ يعيد حسابَ الاستحقاق. الحقولُ غيرُ المعلَنة تُهمَل لا تُمحى."""
    cur = get(c, user_id, sid)
    fields = {}
    for k in ("title", "recurrence", "tz", "at_minute", "day_of", "kind"):
        if k in kw and kw[k] is not None:
            fields[k] = kw[k]
    if not fields:
        return cur

    rec = fields.get("recurrence", cur["recurrence"])
    if rec not in RECURRENCE:
        raise ScheduleError("تكرارٌ غير معروف")
    if fields.get("kind", cur["kind"]) not in KINDS:
        raise ScheduleError("نوعٌ غير مدعوم")

    nxt = next_run(rec, fields.get("tz", cur["tz"]),
                   fields.get("at_minute", cur["at_minute"]),
                   fields.get("day_of", cur["day_of"]))
    sets = ", ".join(f"{k}=?" for k in fields)
    c.execute(f"UPDATE schedules SET {sets}, next_run_at=?, updated_at=? "
              f"WHERE id=? AND user_id=?",
              (*fields.values(), nxt, store.now(), sid, user_id))
    c.commit()
    obs.info("schedule.update", schedule_id=sid)
    return get(c, user_id, sid)


def set_status(c, user_id, sid, status):
    """إيقافٌ أو استئناف. والاستئنافُ يعيد حسابَ الاستحقاق من الآن —
    فلا ينفجر جدولٌ أُوقف شهرًا بتنفيذاتٍ فائتة."""
    if status not in ("active", "paused"):
        raise ScheduleError("حالةٌ غير مسموحة")
    cur = get(c, user_id, sid)
    nxt = (next_run(cur["recurrence"], cur["tz"], cur["at_minute"],
                    cur["day_of"]) if status == "active" else None)
    c.execute("UPDATE schedules SET status=?, next_run_at=?, updated_at=? "
              "WHERE id=? AND user_id=?",
              (status, nxt, store.now(), sid, user_id))
    c.commit()
    obs.info("schedule.status", schedule_id=sid, status=status)
    return get(c, user_id, sid)


def delete(c, user_id, sid):
    get(c, user_id, sid)                      # يرمي إن لم يكن له
    c.execute("DELETE FROM schedules WHERE id=? AND user_id=?", (sid, user_id))
    c.commit()
    obs.info("schedule.delete", schedule_id=sid)
    return True


def runs(c, user_id, sid, limit=20):
    """تاريخُ التنفيذ — «متى فشل ولماذا» لا «آخرُ قيمة»."""
    get(c, user_id, sid)
    return [dict(r) for r in c.execute(
        "SELECT id, at, job_id, result, error FROM schedule_runs "
        "WHERE schedule_id=? ORDER BY at DESC LIMIT ?",
        (sid, min(int(limit), 100)))]


# ــــــــــــــــــــ التنفيذ ــــــــــــــــــــ

def _idem(sid, due_at):
    """مفتاحُ تفرّدٍ لكلِّ (جدول، لحظةٍ مستحقّة). تشغيلان متزامنان يتصادمان
    على القيد الفريد فينجو أحدُهما — ولا يُعتمد على قفلٍ في التطبيق."""
    return f"sched:{sid}:{due_at}"


def due(c, now=None, limit=50):
    now = now if now is not None else store.now()
    return list(c.execute(
        "SELECT * FROM schedules WHERE status='active' AND next_run_at IS NOT NULL "
        "AND next_run_at <= ? ORDER BY next_run_at LIMIT ?", (now, limit)))


def fire(c, row):
    """ينفّذ جدولًا مستحقًّا: يضع مهمّةً في الطابور ويسجّل النتيجة.

    **لا يرمي أبدًا** — الكانسُ يمرّ على جداولَ كثيرة، وسقوطُ واحدٍ يجب
    ألّا يوقف البقيّة. كلُّ نتيجةٍ تُسجَّل في `schedule_runs`.
    """
    sid, due_at = row["id"], row["next_run_at"]
    key = _idem(sid, due_at)
    t = store.now()
    result, job_id, err = "failed", None, None

    try:
        # التفرّد أوّلًا: إن سبقنا غيرُنا خرجنا بلا عمل
        try:
            c.execute("INSERT INTO schedule_runs(schedule_id,at,result,idem_key) "
                      "VALUES(?,?,'skipped',?)", (sid, t, key))
            c.commit()
        except Exception:
            c.rollback()
            obs.debug("schedule.duplicate", schedule_id=sid)
            return None

        # **الحمولةُ تحمل هويّةَ الجدول واللحظة، لا المشروعَ وحده.**
        #
        # بصمةُ الطابور (`jobs.idem_key`) تُحسب من (المستخدم، النوع،
        # الحمولة). فلو كانت الحمولةُ `{"project": 7}` وحدها لصار كلُّ
        # جدولٍ على المشروع نفسِه بصمةً واحدة: أوّلُ تنفيذٍ يمرّ والبقيّةُ
        # تُردّ `JobConflict` — وهو ما وقع فعلًا وأمسكه الاختبار.
        #
        # وإضافةُ الهويّة لا تُضعف تفرّدَ الطابور: تصديرٌ يدويٌّ يبقى
        # حمولتَه، ونقرتان عليه تتصادمان كما كانتا. إنما تقول الحقيقة:
        # تنفيذان مجدولان مختلفان **عملان مختلفان**.
        payload = {"project": row["project_id"], "scheduled": True,
                   "schedule": sid, "due_at": due_at}
        job = JB.enqueue(c, row["user_id"], row["kind"], payload)
        job_id = job["id"] if isinstance(job, dict) else job
        result = "queued"
        obs.info("schedule.fired", schedule_id=sid, job_id=job_id,
                 kind=row["kind"])
        obs.M.inc("schedule_fired_total", kind=row["kind"], result="queued")
    except Exception as e:
        # الحصّةُ أو الطابورُ الممتلئُ أو أيُّ خطأ: يُسجَّل ويمضي الكانس
        err = str(e)[:200]
        obs.warn("schedule.fire_failed", schedule_id=sid,
                 error_type=type(e).__name__)
        obs.M.inc("schedule_fired_total", kind=row["kind"], result="failed")

    try:
        c.execute("UPDATE schedule_runs SET result=?, job_id=?, error=? "
                  "WHERE idem_key=?", (result, job_id, err, key))
        # **«مرّةً واحدة» لا تالٍ لها بعد تنفيذها — أيًّا كان الحساب.**
        # وإلا لجاز أن يُحسب لها موعدٌ لاحقٌ في اليوم نفسِه فتتكرّر، وهي
        # اسمُها «مرّةً واحدة». الدلالةُ تسبق الحساب.
        nxt = (None if row["recurrence"] == "once" else
               next_run(row["recurrence"], row["tz"], row["at_minute"],
                        row["day_of"], after=due_at))
        status = "active" if nxt else "done"
        c.execute("UPDATE schedules SET last_run_at=?, next_run_at=?, status=?, "
                  "runs=runs+1, failures=failures+?, updated_at=? WHERE id=?",
                  (t, nxt, status, 0 if result == "queued" else 1, t, sid))
        c.commit()
    except Exception:
        c.rollback()
        obs.error("schedule.bookkeeping_failed", schedule_id=sid)
    return job_id


def sweep(c, now=None, limit=50):
    """يمرّ على المستحقّ فينفّذه. يُنادى من حلقة العامل.

    يردّ عددَ ما وُضع في الطابور — لا يرمي.
    """
    n = 0
    for row in due(c, now, limit):
        if fire(c, row):
            n += 1
    if n:
        obs.M.inc("schedule_sweep_total", fired=str(min(n, 9)))
    return n
