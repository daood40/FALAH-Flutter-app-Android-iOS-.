"""طابور المهامّ الثقيلة — تصيير البطاقات والمقاطع خارج دورة الطلب.

القياس الذي أوجب هذا الملفّ: بطاقةٌ واحدة تستغرق ٣٫٢ ثانية، والمقطع ٢٦
ثانية، وكلاهما كان يجري *داخل* طلب HTTP. عشرة مستخدمين معًا يعني عشرة
خيوطٍ محبوسة، ومتصفّحًا ينتظر بلا خبر، ومهلةً تقطع العمل بعد بنائه.

المبدأ: الخادم يستقبل ويتحقّق ويحجز الحصّة ويضع المهمّة ويردّ (٢٠٢). عاملٌ
منفصل يسحبها ويُصيّر ويُحدّث الحالة. المتصفّح يستطلع حتى تكتمل.

ولماذا الطابور في SQLite لا في وسيطٍ خارجيّ؟ لأن المشروع بلا اعتمادياتٍ
خارجية عمدًا، والحمل المقيس لا يقتضي أكثر من هذا. `BEGIN IMMEDIATE` يضمن
ألا يسحب عاملان مهمّةً واحدة، وهو ما يلزم فعلًا.

ما لا يتغيّر: `verify.py` تبقى سلطة الحكم الوحيدة. العامل لا ينسخ منطقها،
بل يفتح المشروع بـ`projects.open_project` فيُعاد الفحصُ وقتَ التصيير — وهو
أدقّ من الفحص وقت الطلب، إذ قد يمرّ بينهما وقت.
"""
import json, os, socket, sqlite3, time

from . import store, billing

STALE   = int(os.environ.get("FALAH_JOB_STALE", 300))   # عاملٌ صامتٌ خمس دقائق يُعدّ متوقّفًا
KEEP    = int(os.environ.get("FALAH_JOB_KEEP", 7 * 86400))
KINDS   = ("export", "video")

class JobError(Exception): pass

def me():
    return f"{socket.gethostname()}:{os.getpid()}"

# ───────────────────────── الوضع في الطابور ─────────────────────────

def enqueue(c, user_id, kind, payload, reserved=None):
    """يضع مهمّةً ويعيد سطرها. `reserved` ما حُجز من الحصّة لأجلها."""
    if kind not in KINDS: raise JobError("نوع مهمّةٍ غير معروف")
    t = store.now()
    cur = c.execute("""INSERT INTO jobs(user_id,kind,payload,state,reserved,created_at)
                       VALUES(?,?,?,'queued',?,?)""",
                    (user_id, kind, json.dumps(payload, ensure_ascii=False),
                     json.dumps(reserved or {}, ensure_ascii=False), t))
    c.commit()
    return get(c, user_id, cur.lastrowid)

def get(c, user_id, job_id):
    """لا يُقرأ إلا سطرُ صاحبه — رقمٌ مخمَّن لا يكشف عمل غيره."""
    r = c.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    if not r: raise JobError("المهمّة غير موجودة")
    return view(r)

def listing(c, user_id, limit=20):
    rows = c.execute("""SELECT * FROM jobs WHERE user_id=?
                        ORDER BY created_at DESC LIMIT ?""", (user_id, limit)).fetchall()
    return [view(r) for r in rows]

def view(r):
    """ما يراه المتصفّح: حالةٌ وتقدّمٌ ونتيجة. الحمولة الداخلية لا تخرج."""
    return {
        "id": r["id"], "kind": r["kind"], "state": r["state"],
        "progress": r["progress"], "step": r["step"],
        "error": r["error"],
        "result": json.loads(r["result"]) if r["result"] else None,
        "attempts": r["attempts"], "created_at": r["created_at"],
        "started_at": r["started_at"], "finished_at": r["finished_at"],
        "waiting": r["state"] in ("queued", "running"),
    }

def cancel(c, user_id, job_id):
    """لا يُلغى إلا ما لم يبدأ — ما دخل التصيير يُترك ليكمل أو يفشل."""
    r = c.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    if not r: raise JobError("المهمّة غير موجودة")
    if r["state"] != "queued":
        raise JobError("لا يُلغى إلا ما لم يبدأ بعد")
    c.execute("UPDATE jobs SET state='canceled', finished_at=? WHERE id=?",
              (store.now(), job_id))
    _refund(c, r)
    c.commit()
    return get(c, user_id, job_id)

# ───────────────────────── جانب العامل ─────────────────────────

def claim(path=None, worker=None):
    """يسحب مهمّةً واحدة ذرّيًّا. `BEGIN IMMEDIATE` يقفل الكتابة، فلا يسحب
    عاملان السطرَ نفسه. يعيد dict الحمولة أو None إن خلا الطابور."""
    c = sqlite3.connect(path or store.APP_DB, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("BEGIN IMMEDIATE")
        t = store.now()
        r = c.execute("""SELECT * FROM jobs WHERE state='queued'
                         ORDER BY created_at LIMIT 1""").fetchone()
        if not r:
            c.execute("COMMIT"); return None
        c.execute("""UPDATE jobs SET state='running', attempts=attempts+1,
                     started_at=COALESCE(started_at,?), heartbeat=?, worker=?,
                     progress=0, step='بدأ' WHERE id=?""",
                  (t, t, worker or me(), r["id"]))
        c.execute("COMMIT")
        return {"id": r["id"], "user_id": r["user_id"], "kind": r["kind"],
                "payload": json.loads(r["payload"]),
                "reserved": json.loads(r["reserved"] or "{}"),
                "attempts": r["attempts"] + 1, "max_attempts": r["max_attempts"]}
    except Exception:
        try: c.execute("ROLLBACK")
        except Exception: pass
        raise
    finally:
        c.close()

def beat(c, job_id, progress=None, step=None):
    """نبضٌ وتقدّم. يُنادى أثناء العمل الطويل ليعرف المستخدم أين وصل."""
    f, v = ["heartbeat=?"], [store.now()]
    if progress is not None: f.append("progress=?"); v.append(max(0, min(100, int(progress))))
    if step is not None:     f.append("step=?");     v.append(step)
    v.append(job_id)
    c.execute(f"UPDATE jobs SET {','.join(f)} WHERE id=?", v)
    c.commit()

def complete(c, job_id, result):
    t = store.now()
    c.execute("""UPDATE jobs SET state='done', progress=100, step='تمّ',
                 result=?, error=NULL, finished_at=?, heartbeat=? WHERE id=?""",
              (json.dumps(result, ensure_ascii=False), t, t, job_id))
    c.commit()

def fail(c, job_id, message, retry=True):
    """يُعاد إلى الطابور ما لم تنفد المحاولات. وعند الفشل النهائيّ تُردّ
    الحصّة المحجوزة — فلا يُحاسَب أحدٌ على عملٍ لم يخرج له."""
    r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r: return
    t = store.now()
    again = retry and r["attempts"] < r["max_attempts"]
    if again:
        c.execute("""UPDATE jobs SET state='queued', error=?, step='سيُعاد',
                     heartbeat=? WHERE id=?""", (str(message)[:500], t, job_id))
    else:
        c.execute("""UPDATE jobs SET state='failed', error=?, step='فشل',
                     finished_at=?, heartbeat=? WHERE id=?""",
                  (str(message)[:500], t, t, job_id))
        _refund(c, r)
    c.commit()
    return again

def _refund(c, r):
    for metric, n in (json.loads(r["reserved"] or "{}") or {}).items():
        try:    billing.release(c, r["user_id"], metric, int(n))
        except Exception: pass

def reap(c, stale=None):
    """يعيد إلى الطابور ما تركه عاملٌ توقّف. بلا هذا تبقى المهمّة «تجري»
    إلى الأبد إن قُتلت العملية في منتصفها."""
    cut = store.now() - (stale if stale is not None else STALE)
    rows = c.execute("""SELECT * FROM jobs WHERE state='running'
                        AND COALESCE(heartbeat, started_at, 0) < ?""", (cut,)).fetchall()
    for r in rows:
        if r["attempts"] < r["max_attempts"]:
            c.execute("UPDATE jobs SET state='queued', step='انقطع العامل' WHERE id=?", (r["id"],))
        else:
            c.execute("""UPDATE jobs SET state='failed', error='انقطع العامل',
                         finished_at=? WHERE id=?""", (store.now(), r["id"]))
            _refund(c, r)
    c.commit()
    return len(rows)

def sweep(c, keep=None):
    """يحذف المنتهيةَ القديمة. الملفّات المصدَّرة تبقى — يُحذف سجلّ المهمّة لا ثمرتها."""
    cut = store.now() - (keep if keep is not None else KEEP)
    n = c.execute("""DELETE FROM jobs WHERE state IN ('done','failed','canceled')
                     AND finished_at < ?""", (cut,)).rowcount
    c.commit()
    return n

def stats(c):
    d = {s: 0 for s in ("queued", "running", "done", "failed", "canceled")}
    for r in c.execute("SELECT state, COUNT(*) n FROM jobs GROUP BY state"):
        d[r["state"]] = r["n"]
    oldest = c.execute("SELECT MIN(created_at) FROM jobs WHERE state='queued'").fetchone()[0]
    d["oldest_wait"] = (store.now() - oldest) if oldest else 0
    return d

# ───────────────────────── تنفيذ المهمّة ─────────────────────────
# المنطق هنا هو نفسه الذي كان في المسار، منقولًا لا مُعادًا كتابته.

def perform(job, content_db, here, c=None):
    """يُصيّر فعليًّا. يُنادى من العامل ومن الاختبارات سواء."""
    from falah import projects as P, referrals as REF
    own = c is None
    c = c or store.connect()
    content = sqlite3.connect(f"file:{content_db}?mode=ro", uri=True)
    content.row_factory = sqlite3.Row
    try:
        u = c.execute("SELECT * FROM users WHERE id=?", (job["user_id"],)).fetchone()
        if not u: raise JobError("صاحب المهمّة غير موجود")
        pl = job["payload"]
        pid = int(pl["project"])
        st = P.open_project(c, content, u["id"], pid)
        proj = st["project"]

        if job["kind"] == "export":
            import carousel as CR
            if not st["items"]:      raise JobError("المشروع فارغ")
            if not st["exportable"]: raise JobError("فيه عناصر محجوبة أو منحرفة — راجعها أولًا")
            beat(c, job["id"], 10, "يُجهّز البطاقات")
            cards = []
            for i in st["items"]:
                p_, t_ = i["checks_now"].split("/")
                rep = {"ok": True, "passed": int(p_), "total": int(t_),
                       "failed": [], "stages": []}
                cards.append((i["kind"], i["card"], rep, f"{i['pos']:02d}_{i['kind']}"))
            plan = CR.plan_of(cards, [], proj["title"])
            outdir = os.path.join(here, "exports", str(u["id"]), str(pid))
            beat(c, job["id"], 25, f"يُصيّر {len(cards)} بطاقة")
            files, _, _ = CR.render_plan(
                plan, proj["skin"], proj["ratio"],
                proj["watermark"] or u["watermark"] or "قناتك", False, outdir,
                falah_mark=billing.allows(c, u["id"], "falah_mark"))
            beat(c, job["id"], 90, "يُسجّل")
            P.record_export(c, u["id"], pid, "carousel", outdir, proj["ratio"],
                            proj["skin"], f"{plan['checks']}/{plan['checks']}")
            try:    REF.qualify(c, u["id"])
            except Exception: pass
            return {"files": [os.path.relpath(f, here) for f in files],
                    "caption": plan["caption"], "sources": plan["sources"],
                    "dir": os.path.relpath(outdir, here)}

        if job["kind"] == "video":
            import video as VD
            it = next((x for x in st["items"] if x["id"] == int(pl["item"])), None)
            if not it:                 raise JobError("العنصر غير موجود")
            if it["kind"] != "quran":  raise JobError("المقطع للآيات فقط")
            if it["state"] != "ok":
                raise JobError("العنصر يحتاج مراجعة: " + (it.get("why") or ""))
            reciter = pl.get("reciter") or "alafasy"
            if not content.execute("SELECT code FROM reciters WHERE code=?",
                                   (reciter,)).fetchone():
                raise JobError("القارئ غير مسجَّل")
            ref = it["ref"]
            outdir = os.path.join(here, "exports", str(u["id"]), str(pid))
            os.makedirs(outdir, exist_ok=True)
            out = os.path.join(outdir, f"clip_{ref['surah']}-{ref['ayah']}_{reciter}.mp4")
            beat(c, job["id"], 20, "يجلب التلاوة ويُصيّر")
            try:
                _, name, dur, rep = VD.build(
                    int(ref["surah"]), int(ref["ayah"]),
                    int(ref["to"]) if ref.get("to") else None, reciter,
                    proj["skin"], proj["ratio"],
                    proj["watermark"] or u["watermark"] or "قناتك", out)
            except SystemExit as e:
                raise JobError(str(e))
            beat(c, job["id"], 90, "يُسجّل")
            P.record_export(c, u["id"], pid, "mp4", out, proj["ratio"], proj["skin"],
                            f"{rep['passed']}/{rep['total']}")
            try:    REF.qualify(c, u["id"])
            except Exception: pass
            return {"file": os.path.relpath(out, here), "reciter": name,
                    "seconds": round(dur, 1)}

        raise JobError("نوع مهمّةٍ غير معروف")
    finally:
        content.close()
        if own: c.close()

# أخطاء المستخدم لا تُعاد محاولتها — المشروع الفارغ يبقى فارغًا مهما كُرِّر
NO_RETRY = (JobError,)

def run_once(content_db, here, path=None, worker=None):
    """يسحب مهمّةً واحدة ويُنفّذها. يعيد المهمّة المنفَّذة أو None."""
    job = claim(path, worker)
    if not job: return None
    c = store.connect(path)
    try:
        try:
            res = perform(job, content_db, here, c)
        except NO_RETRY as e:
            fail(c, job["id"], str(e), retry=False)
            return {**job, "ok": False, "error": str(e)}
        except Exception as e:
            again = fail(c, job["id"], f"{type(e).__name__}: {e}", retry=True)
            return {**job, "ok": False, "error": str(e), "requeued": bool(again)}
        # الحصّة حُجزت عند الوضع في الطابور، فلا تُستهلك هنا مرّةً ثانية.
        complete(c, job["id"], res)
        return {**job, "ok": True, "result": res}
    finally:
        c.close()
