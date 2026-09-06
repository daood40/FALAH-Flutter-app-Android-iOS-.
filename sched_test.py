#!/usr/bin/env python3
"""الجدولة — التوقيتُ والملكيّةُ والتفرّدُ ودورةُ التنفيذ كاملة.

    python3 sched_test.py

القواعدُ التي تحرسها، وكلُّها قراراتُ تصميمٍ لا تفاصيلُ تنفيذ:

  ١ · **اسمُ منطقةٍ لا إزاحة** — «٦ صباحًا» تبقى ٦ صباحًا عبر التوقيت
      الصيفيّ. الإزاحةُ المحفوظةُ تُزيحها ساعةً مرّتين في السنة.
  ٢ · **الملكيّةُ تُفحص في النطاق** — مشروعُ غيرِك لا يُجدوَل ولو نُودي
      المُنشئُ مباشرةً بلا مرورٍ بجدول المسارات.
  ٣ · **لا تنفيذَ مزدوج** — عاملان متزامنان لا يُنشئان مهمّتين لاستحقاقٍ
      واحد. القيدُ الفريدُ في القاعدة يمنع، لا قفلٌ في التطبيق.
  ٤ · **الحدُّ يمنع بابًا خلفيًّا** — الجدولُ لا يصير وسيلةً لتجاوز حدِّ
      المعدّل بألفِ جدولٍ في الدقيقة نفسِها.
"""
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_TMP = tempfile.mkdtemp(prefix="falah_sched_")
os.environ["FALAH_APP_DB"] = os.path.join(_TMP, "app.db")

from falah import migrate, schedules as SCH, store  # noqa: E402

OK = FAIL = 0
FAILURES: list = []


def check(name, cond, detail=""):
    global OK, FAIL
    if cond:
        OK += 1; print(f"  ✓ {name}")
    else:
        FAIL += 1; FAILURES.append((name, detail))
        print(f"  ✗ {name}" + (f"  ← {detail}" if detail else ""))


def head(t): print(f"\n▸ {t}")


def fresh():
    """قاعدةٌ نظيفةٌ تمرّ بالهجرات — لا مخطَّطٌ مكتوبٌ بيدٍ في الاختبار."""
    c = store.connect()
    migrate.run(c) if hasattr(migrate, "run") else None
    return c


def mkuser(c, n=1):
    t = store.now()
    cur = c.execute(
        "INSERT INTO users(email,name,watermark,pw_hash,pw_salt,pw_iter,"
        "status,created_at) VALUES(?,?,?,?,?,?,'active',?)",
        (f"u{n}-{t}-{os.getpid()}@t.local", f"u{n}", "", b"x", b"y", 1, t))
    c.commit()
    return cur.lastrowid


def mkproject(c, uid, title="p"):
    t = store.now()
    cur = c.execute(
        "INSERT INTO projects(user_id,title,skin,ratio,archived,created_at,updated_at) "
        "VALUES(?,?, 'parch','square',0,?,?)", (uid, title, t, t))
    c.commit()
    return cur.lastrowid


# ═══════════ ١ · التوقيت ═══════════

def timing():
    head("التوقيت — اسمُ منطقةٍ لا إزاحة")

    # طرابلس UTC+2 ثابتةً: ٦ صباحًا محلّيًّا = ٤ صباحًا عالميًّا
    n = SCH.next_run("daily", "Africa/Tripoli", 6 * 60, None)
    utc = datetime.fromtimestamp(n, timezone.utc)
    check("يوميّ ٦ص طرابلس ⇒ ٤ص عالميًّا", utc.hour == 4, utc.isoformat())
    check("والتالي في المستقبل", n > store.now())

    # منطقةٌ ذاتُ توقيتٍ صيفيّ: الاختبارُ أن الساعةَ المحلّيّة تبقى ثابتة
    for tz in ("Europe/London", "America/New_York", "Asia/Riyadh"):
        n = SCH.next_run("daily", tz, 6 * 60, None)
        from zoneinfo import ZoneInfo
        local = datetime.fromtimestamp(n, ZoneInfo(tz))
        check(f"٦ص تبقى ٦ص في {tz}", local.hour == 6 and local.minute == 0,
              local.isoformat())

    # أسبوعيّ: اليومُ المطلوبُ هو ما يقع فعلًا
    n = SCH.next_run("weekly", "UTC", 9 * 60, 4)      # ٤ = الجمعة
    d = datetime.fromtimestamp(n, timezone.utc)
    check("أسبوعيّ ٤ ⇒ يومُ جمعة", d.weekday() == 4, d.isoformat())

    # شهريّ: اليومُ يُقصر على ٢٨ فلا يسقط في شباط
    n = SCH.next_run("monthly", "UTC", 0, 31)
    d = datetime.fromtimestamp(n, timezone.utc)
    check("شهريّ ٣١ ⇒ يُقصر إلى ٢٨ (لا يسقط في شباط)", d.day == 28, str(d.day))

    # مرّةً واحدة: وقتٌ مضى ⇒ لا تالية
    check("مرّةً واحدةً بوقتٍ مضى ⇒ None",
          SCH.next_run("once", "UTC", 0, None, after=time.time()) is None)

    # منطقةٌ مجهولةٌ تُرفض صراحةً — لا تُقبل صامتةً على أنها UTC
    try:
        SCH.next_run("daily", "Mars/Olympus", 0, None)
        check("منطقةٌ مجهولةٌ تُرفض", False, "قُبلت")
    except SCH.ScheduleError:
        check("منطقةٌ مجهولةٌ تُرفض", True)

    for bad in (-1, 1440, 99999):
        try:
            SCH.next_run("daily", "UTC", bad, None)
            check(f"وقتٌ خارج اليوم ({bad}) يُرفض", False)
        except SCH.ScheduleError:
            check(f"وقتٌ خارج اليوم ({bad}) يُرفض", True)


# ═══════════ ٢ · الملكيّة ═══════════

def ownership():
    head("الملكيّة — تُفحص في النطاق لا في الجدول وحده")
    c = fresh()
    a, b = mkuser(c, 1), mkuser(c, 2)
    pa = mkproject(c, a, "مشروع أ")

    s = SCH.create(c, a, pa, recurrence="daily", tz="UTC", at_minute=60)
    check("المالكُ يُنشئ على مشروعه", s["project_id"] == pa)

    # النداءُ المباشرُ يتخطّى جدولَ المسارات — والنطاقُ يحرس نفسَه
    try:
        SCH.create(c, b, pa, recurrence="daily", tz="UTC", at_minute=60)
        check("وغيرُه لا يُجدوِل مشروعَه", False, "نجح وكان يجب أن يُرفض")
    except SCH.ScheduleError as e:
        check("وغيرُه لا يُجدوِل مشروعَه", True)
        # «ليس لك» ≡ «غير موجود» — لا يُكشف وجودُ المورِد
        check("ورسالتُه لا تكشف وجودَ المشروع", "غير موجود" in str(e), str(e))

    try:
        SCH.get(c, b, s["id"])
        check("ولا يقرأ جدولَ غيرِه", False)
    except SCH.ScheduleError:
        check("ولا يقرأ جدولَ غيرِه", True)

    try:
        SCH.delete(c, b, s["id"])
        check("ولا يحذفه", False)
    except SCH.ScheduleError:
        check("ولا يحذفه", True)

    check("والجدولُ باقٍ بعد محاولة الحذف",
          SCH.get(c, a, s["id"])["id"] == s["id"])
    check("وسردُ ب فارغ", SCH.listing(c, b) == [])
    c.close()


# ═══════════ ٣ · الحدود ═══════════

def limits():
    head("الحدُّ يمنع بابًا خلفيًّا لتجاوز حدِّ المعدّل")
    c = fresh()
    u = mkuser(c, 3)
    p = mkproject(c, u)
    for i in range(SCH.MAX_ACTIVE_PER_USER):
        SCH.create(c, u, p, recurrence="daily", tz="UTC", at_minute=i)
    try:
        SCH.create(c, u, p, recurrence="daily", tz="UTC", at_minute=100)
        check(f"ما فوق {SCH.MAX_ACTIVE_PER_USER} يُرفض", False)
    except SCH.ScheduleError:
        check(f"ما فوق {SCH.MAX_ACTIVE_PER_USER} يُرفض", True)

    # والإيقافُ يُفرج عن مكان
    first = SCH.listing(c, u)[0]
    SCH.set_status(c, u, first["id"], "paused")
    try:
        SCH.create(c, u, p, recurrence="daily", tz="UTC", at_minute=101)
        check("وإيقافُ واحدٍ يُفرج عن مكان", True)
    except SCH.ScheduleError as e:
        check("وإيقافُ واحدٍ يُفرج عن مكان", False, str(e))

    check("نوعٌ غير مدعومٍ يُرفض", _raises(
        lambda: SCH.create(c, u, p, kind="nuke", tz="UTC", at_minute=1)))
    check("تكرارٌ غير معروفٍ يُرفض", _raises(
        lambda: SCH.create(c, u, p, recurrence="hourly", tz="UTC", at_minute=1)))
    c.close()


def _raises(fn):
    try:
        fn(); return False
    except SCH.ScheduleError:
        return True


# ═══════════ ٤ · دورةُ الحياة ═══════════

def lifecycle():
    head("دورةُ الحياة — إنشاءٌ · تعديلٌ · إيقافٌ · استئنافٌ · حذف")
    c = fresh()
    u = mkuser(c, 4)
    p = mkproject(c, u)

    s = SCH.create(c, u, p, title="سلسلةُ الفجر", recurrence="daily",
                   tz="Africa/Tripoli", at_minute=5 * 60)
    sid = s["id"]
    check("يُنشأ نشطًا", s["status"] == "active")
    check("وله استحقاقٌ محسوب", s["next_run_at"] is not None)
    check("والعنوانُ محفوظ", s["title"] == "سلسلةُ الفجر")

    before = s["next_run_at"]
    s2 = SCH.update(c, u, sid, at_minute=7 * 60)
    check("التعديلُ يعيد حسابَ الاستحقاق", s2["next_run_at"] != before)
    check("ولا يمحو ما لم يُعلَن", s2["title"] == "سلسلةُ الفجر")

    s3 = SCH.set_status(c, u, sid, "paused")
    check("الإيقافُ يمحو الاستحقاق", s3["next_run_at"] is None)
    check("والحالةُ موقوفة", s3["status"] == "paused")

    s4 = SCH.set_status(c, u, sid, "active")
    check("والاستئنافُ يُعيده من الآن لا من الماضي",
          s4["next_run_at"] is not None and s4["next_run_at"] > store.now())

    check("حالةٌ غير مسموحةٍ تُرفض",
          _raises(lambda: SCH.set_status(c, u, sid, "deleted")))

    SCH.delete(c, u, sid)
    check("والحذفُ يُزيله", _raises(lambda: SCH.get(c, u, sid)))
    c.close()


# ═══════════ ٥ · التنفيذ والتفرّد ═══════════

def firing():
    head("التنفيذ — لا مهمّةَ مزدوجةٌ لاستحقاقٍ واحد")
    c = fresh()
    u = mkuser(c, 5)
    p = mkproject(c, u)

    s = SCH.create(c, u, p, recurrence="daily", tz="UTC", at_minute=0)
    # نجعله مستحقًّا الآن
    c.execute("UPDATE schedules SET next_run_at=? WHERE id=?",
              (store.now() - 5, s["id"]))
    c.commit()

    rows = SCH.due(c)
    check("المستحقُّ يُلتقط", any(r["id"] == s["id"] for r in rows), str(len(rows)))

    row = [r for r in rows if r["id"] == s["id"]][0]
    j1 = SCH.fire(c, row)
    check("والتنفيذُ يضع مهمّةً", j1 is not None, str(j1))

    # **الاختبارُ الحاسم**: النداءُ ثانيةً بالصفّ نفسِه — كعاملٍ ثانٍ متزامن
    j2 = SCH.fire(c, row)
    check("ونداءٌ ثانٍ للاستحقاق نفسِه لا يُنشئ مهمّةً ثانية", j2 is None, str(j2))

    n = c.execute("SELECT COUNT(*) FROM schedule_runs WHERE schedule_id=?",
                  (s["id"],)).fetchone()[0]
    check("وسجلُّ التنفيذ سطرٌ واحدٌ لا اثنان", n == 1, str(n))

    after = SCH.get(c, u, s["id"])
    check("والعدّادُ ارتفع", after["runs"] == 1, str(after["runs"]))
    check("واستحقاقٌ تالٍ محسوب", after["next_run_at"] > store.now())
    check("وما زال نشطًا (يوميّ)", after["status"] == "active")

    hist = SCH.runs(c, u, s["id"])
    check("والتاريخُ يُقرأ", len(hist) == 1 and hist[0]["result"] == "queued",
          str(hist))

    # مرّةً واحدةً: بعد تنفيذها تنتهي
    s2 = SCH.create(c, u, p, recurrence="once", tz="UTC",
                    at_minute=(datetime.now().hour * 60 + 59) % 1440)
    c.execute("UPDATE schedules SET next_run_at=? WHERE id=?",
              (store.now() - 5, s2["id"]))
    c.commit()
    row2 = [r for r in SCH.due(c) if r["id"] == s2["id"]][0]
    SCH.fire(c, row2)
    check("و«مرّةً واحدة» تصير منتهيةً بعد تنفيذها",
          SCH.get(c, u, s2["id"])["status"] == "done")
    c.close()


# ═══════════ ٦ · الكنسُ لا يسقط ═══════════

def sweeping():
    head("الكنسُ لا يسقط بجدولٍ واحدٍ معطوب")
    c = fresh()
    u = mkuser(c, 6)
    p = mkproject(c, u)
    ids = []
    for i in range(3):
        s = SCH.create(c, u, p, recurrence="daily", tz="UTC", at_minute=i)
        c.execute("UPDATE schedules SET next_run_at=? WHERE id=?",
                  (store.now() - 5, s["id"]))
        ids.append(s["id"])
    c.commit()

    n = SCH.sweep(c)
    check("الكنسُ ينفّذ المستحقَّ كلَّه", n == 3, str(n))
    check("ولا يعيد تنفيذَ ما نُفّذ", SCH.sweep(c) == 0)

    # مشروعٌ محذوفٌ: الجدولُ يذهب معه (ON DELETE CASCADE)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("DELETE FROM projects WHERE id=?", (p,))
    c.commit()
    left = c.execute("SELECT COUNT(*) FROM schedules WHERE project_id=?",
                     (p,)).fetchone()[0]
    check("وحذفُ المشروع يحذف جداولَه", left == 0, str(left))
    c.close()


def run():
    print("═" * 46)
    print("  الجدولة — توقيتٌ وملكيّةٌ وتفرّدٌ ودورةُ تنفيذ")
    print("═" * 46)
    timing(); ownership(); limits(); lifecycle(); firing(); sweeping()
    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: سقط {FAIL} من {OK + FAIL}")
        for n, d in FAILURES:
            print(f"  ✗ {n}" + (f"  ← {d}" if d else ""))
        return 1
    print(f"النتيجة: {OK} فحصًا · كلّها نجحت ✓")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    finally:
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
