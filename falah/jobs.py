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
import hashlib, json, os, socket, sqlite3

from . import store, billing

def _int(name, default):
    try:    return max(0, int(os.environ.get(name, default)))
    except (TypeError, ValueError): return default

# ═══════════ الحدود — كلّها من متغيّرات البيئة ═══════════
STALE       = _int("FALAH_JOB_STALE", 300)      # عاملٌ صامتٌ ٥ دقائق يُعدّ متوقّفًا
KEEP        = _int("FALAH_JOB_KEEP", 7 * 86400) # عمر سجلّ المهمّة المنتهية
MAX_RETRIES = _int("FALAH_MAX_RETRIES", 2)      # محاولاتٌ إضافية بعد الأولى
BACKOFF     = _int("FALAH_BACKOFF", 5)          # ثوانٍ، تتضاعف: ٥ ثم ١٠ ثم ٢٠…
BACKOFF_MAX = _int("FALAH_BACKOFF_MAX", 300)
JOB_TIMEOUT = _int("FALAH_JOB_TIMEOUT", 600)    # سقفُ زمن المهمّة الواحدة
MAX_QUEUED  = _int("FALAH_MAX_QUEUED_PER_USER", 5)   # طابورُ المستخدم الواحد
MAX_RUNNING = _int("FALAH_MAX_RUNNING", 4)      # سقفُ ما يجري معًا في النظام كلّه
MAX_CARDS   = _int("FALAH_MAX_CARDS_PER_JOB", 60)    # أطولُ سلسلةٍ في مهمّةٍ واحدة
MAX_VIDEO_S = _int("FALAH_MAX_VIDEO_SECONDS", 180)
MAX_STORE_MB = _int("FALAH_MAX_STORAGE_MB_PER_USER", 2048)

KINDS = ("export", "video")

# ═══════════ آلة الحالات ═══════════
# خمسُ حالاتٍ لا سادسَ لها، وانتقالاتٌ معدودة. ما ليس في هذا الجدول لا يقع:
# `done → running` مثلًا يعني أن مهمّةً سُلِّمت ثمّ أُعيد تصييرها فوق نتيجتها.
STATES = ("queued", "running", "done", "failed", "canceled")
TRANSITIONS = {
    "queued":   {"running", "canceled"},
    "running":  {"done", "failed", "queued"},   # queued = إعادةٌ بعد عطبٍ عابر
    "done":     set(),                          # نهائية
    "failed":   set(),                          # نهائية — إعادةُ الطلب مهمّةٌ جديدة
    "canceled": set(),
}
TERMINAL = {"done", "failed", "canceled"}

class JobError(Exception):
    """خطأ المستخدم أو الطلب — لا يُعاد. المشروع الفارغ يبقى فارغًا."""

class JobConflict(JobError):
    """طلبٌ مكرَّرٌ لمهمّةٍ حيّة — يُردّ بالمهمّة القائمة لا بمهمّةٍ ثانية."""

class JobLimit(JobError):
    """تجاوزُ حدٍّ من حدود الموارد."""

def me():
    return f"{socket.gethostname()}:{os.getpid()}"

def can(frm, to):
    return to in TRANSITIONS.get(frm, set())

def _guard(c, job_id, to):
    """يمنع الانتقال غير المشروع عند مصدره لا بعد وقوعه."""
    r = c.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r: raise JobError("المهمّة غير موجودة")
    if not can(r["state"], to):
        raise JobError(f"انتقالٌ غير مشروع: {r['state']} ← {to}")
    return r["state"]

def idem_key(user_id, kind, payload):
    """بصمةُ الطلب: صاحبه ونوعه وحمولته مرتَّبة. نقرتان على الزرّ نفسه
    تُعطيان البصمة نفسها، فلا تدخل الثانيةُ الطابور."""
    blob = json.dumps({"u": user_id, "k": kind, "p": payload},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def backoff_for(attempt):
    """تراجعٌ أُسّيّ: ٥ث ثم ١٠ ثم ٢٠… بسقف. عطبٌ عابر يُعاد بعد مهلةٍ لا فورًا،
    وإلا استهلكت المحاولاتُ الثلاثُ نفسَ اللحظة التي أعطبت الأولى."""
    return min(BACKOFF * (2 ** max(0, attempt - 1)), BACKOFF_MAX)

# ───────────────────────── الوضع في الطابور ─────────────────────────

def live_for(c, key):
    """المهمّة الحيّة بهذه البصمة، إن وُجدت."""
    return c.execute("""SELECT * FROM jobs WHERE idem_key=?
                        AND state IN ('queued','running')""", (key,)).fetchone()

def enqueue(c, user_id, kind, payload, reserved=None, max_attempts=None):
    """يضع مهمّةً ويعيد سطرها. `reserved` ما حُجز من الحصّة لأجلها.

    ثلاثةُ حرّاسٍ قبل الدخول:
      • **التفرّد** — طلبٌ مطابقٌ لمهمّةٍ حيّة يُردّ بها هي، فلا تُصيَّر مرّتين
        ولا تُحجز الحصّة مرّتين. النقرةُ المزدوجة والشبكةُ المتقطّعة تصيران
        بلا أثر.
      • **طابور المستخدم** — لا يملأ حسابٌ واحدٌ الطابورَ على غيره.
      • **حجم العمل** — سلسلةٌ أطول من الحدّ تُردّ بسببها لا تُقبل ثم تُعطب.
    """
    if kind not in KINDS: raise JobError("نوع مهمّةٍ غير معروف")

    key = idem_key(user_id, kind, payload)
    cur = live_for(c, key)
    if cur:
        raise JobConflict(json.dumps({"duplicate": True, "job": view(cur)},
                                     ensure_ascii=False))

    n = c.execute("""SELECT COUNT(*) FROM jobs WHERE user_id=?
                     AND state IN ('queued','running')""", (user_id,)).fetchone()[0]
    if n >= MAX_QUEUED:
        raise JobLimit(f"لك {n} مهامّ لم تنتهِ بعد. انتظر إحداها أو ألغِها "
                       f"(الحدّ {MAX_QUEUED}).")

    t = store.now()
    try:
        c.execute("""INSERT INTO jobs(user_id,kind,payload,state,reserved,idem_key,
                                      max_attempts,created_at)
                     VALUES(?,?,?,'queued',?,?,?,?)""",
                  (user_id, kind, json.dumps(payload, ensure_ascii=False),
                   json.dumps(reserved or {}, ensure_ascii=False), key,
                   MAX_RETRIES if max_attempts is None else max_attempts, t))
    except sqlite3.IntegrityError:
        # سباقٌ نادر: طلبان متزامنان بالبصمة نفسها. الفهرس الفريد حسم الأمر.
        cur = live_for(c, key)
        if cur: raise JobConflict(json.dumps({"duplicate": True, "job": view(cur)},
                                             ensure_ascii=False))
        raise
    jid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.commit()
    return get(c, user_id, jid)

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
        "attempts": r["attempts"], "max_attempts": r["max_attempts"],
        "created_at": r["created_at"],
        "started_at": r["started_at"], "finished_at": r["finished_at"],
        "waiting": r["state"] not in TERMINAL,
        "retry_after": max(0, (r["not_before"] or 0) - store.now()),
    }

def cancel(c, user_id, job_id):
    """لا يُلغى إلا ما لم يبدأ — ما دخل التصيير يُترك ليكمل أو يفشل."""
    r = c.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    if not r: raise JobError("المهمّة غير موجودة")
    if not can(r["state"], "canceled"):
        raise JobError("لا يُلغى إلا ما لم يبدأ بعد")
    c.execute("""UPDATE jobs SET state='canceled', step='أُلغيت', finished_at=?
                 WHERE id=? AND state='queued'""", (store.now(), job_id))
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
        # سقفُ التزامن: عاملٌ إضافيّ لا يبدأ عملًا خامسًا فيخنق الذاكرة
        running = c.execute("SELECT COUNT(*) FROM jobs WHERE state='running'").fetchone()[0]
        if running >= MAX_RUNNING:
            c.execute("COMMIT"); return None
        # `not_before` يحترم التراجع الأُسّيّ: المعادُ لا يُسحب قبل مهلته
        r = c.execute("""SELECT * FROM jobs WHERE state='queued' AND not_before<=?
                         ORDER BY created_at LIMIT 1""", (t,)).fetchone()
        if not r:
            c.execute("COMMIT"); return None
        c.execute("""UPDATE jobs SET state='running', attempts=attempts+1,
                     started_at=COALESCE(started_at,?), heartbeat=?, worker=?,
                     progress=0, step='بدأ' WHERE id=? AND state='queued'""",
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
    _guard(c, job_id, "done")           # `done → done` أو `failed → done` لا يقع
    t = store.now()
    c.execute("""UPDATE jobs SET state='done', progress=100, step='تمّ',
                 result=?, error=NULL, finished_at=?, heartbeat=?
                 WHERE id=? AND state='running'""",
              (json.dumps(result, ensure_ascii=False), t, t, job_id))
    c.commit()

def fail(c, job_id, message, retry=True):
    """يُعاد إلى الطابور ما لم تنفد المحاولات، بعد مهلةٍ تتضاعف. وعند الفشل
    النهائيّ تُردّ الحصّة المحجوزة — فلا يُحاسَب أحدٌ على عملٍ لم يخرج له."""
    r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r: return None
    # ليست جاريةً: إمّا انتهت، وإمّا أعادها `reap` بعدما ظُنّ العاملُ منقطعًا
    # ثمّ أفاق فأبلغ عن فشله. في الحالتين لا تُمسّ — الأخير لا يهدم الأوّل.
    if r["state"] != "running": return False
    t = store.now()
    again = retry and r["attempts"] < r["max_attempts"]
    if again:
        wait = backoff_for(r["attempts"])
        _guard(c, job_id, "queued")
        c.execute("""UPDATE jobs SET state='queued', error=?, step=?,
                     not_before=?, heartbeat=? WHERE id=? AND state='running'""",
                  (str(message)[:500], f"سيُعاد بعد {wait}ث", t + wait, t, job_id))
    else:
        _guard(c, job_id, "failed")
        c.execute("""UPDATE jobs SET state='failed', error=?, step='فشل',
                     finished_at=?, heartbeat=? WHERE id=? AND state='running'""",
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
    t = store.now()
    cut = t - (stale if stale is not None else STALE)
    rows = c.execute("""SELECT * FROM jobs WHERE state='running'
                        AND COALESCE(heartbeat, started_at, 0) < ?""", (cut,)).fetchall()
    # ومهمّةٌ تنبض لكنها تجاوزت سقفَ زمنها: عالقةٌ لا منقطعة، وتُقطع
    stuck = c.execute("""SELECT * FROM jobs WHERE state='running'
                         AND started_at IS NOT NULL AND started_at < ?""",
                      (t - JOB_TIMEOUT,)).fetchall()
    seen, n = set(), 0
    for r, why in [(x, "انقطع العامل") for x in rows] + \
                  [(x, f"تجاوزت سقف الزمن ({JOB_TIMEOUT}ث)") for x in stuck]:
        if r["id"] in seen: continue
        seen.add(r["id"]); n += 1
        if r["attempts"] < r["max_attempts"]:
            c.execute("""UPDATE jobs SET state='queued', step=?, error=?, not_before=?
                         WHERE id=? AND state='running'""",
                      (why, why, t + backoff_for(r["attempts"]), r["id"]))
        else:
            c.execute("""UPDATE jobs SET state='failed', error=?, step='فشل',
                         finished_at=? WHERE id=? AND state='running'""",
                      (why, t, r["id"]))
            _refund(c, r)
    c.commit()
    return n

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
    d["capacity"] = MAX_RUNNING
    d["saturated"] = d["running"] >= MAX_RUNNING
    # آخرُ نبضٍ من أيّ عامل — به تُعرف حياةُ العمّال من الخادم
    hb = c.execute("SELECT MAX(heartbeat) FROM jobs").fetchone()[0]
    d["last_worker_beat"] = hb
    d["worker_silent_for"] = (store.now() - hb) if hb else None
    return d

# ───────────────────────── تنفيذ المهمّة ─────────────────────────
# المنطق هنا هو نفسه الذي كان في المسار، منقولًا لا مُعادًا كتابته.

def _user_mb(here, user_id):
    """ما يشغله صاحبُ الحساب من صادرات، بالميغابايت."""
    root = os.path.join(here, "exports", str(user_id))
    total = 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            try:    total += os.path.getsize(os.path.join(dirpath, f))
            except OSError: pass
    return total / 1048576

def limits():
    """الحدود النافذة الآن — تُعرض في `/app/limits` فيعرفها المستخدم قبل أن يصطدم بها."""
    return {"max_queued_per_user": MAX_QUEUED, "max_running": MAX_RUNNING,
            "max_cards_per_job": MAX_CARDS, "max_video_seconds": MAX_VIDEO_S,
            "max_storage_mb_per_user": MAX_STORE_MB, "job_timeout_seconds": JOB_TIMEOUT,
            "max_retries": MAX_RETRIES, "backoff_seconds": BACKOFF,
            "stale_after_seconds": STALE}

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
            if len(st["items"]) > MAX_CARDS:
                raise JobLimit(f"السلسلة {len(st['items'])} بطاقة، والحدّ {MAX_CARDS} "
                               f"في المهمّة الواحدة. قسّمها على مشروعين.")
            if _user_mb(here, u["id"]) > MAX_STORE_MB:
                raise JobLimit(f"بلغتَ حدّ التخزين ({MAX_STORE_MB} م.ب). "
                               f"نزّل صادراتك القديمة ثم أعد المحاولة.")
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
            if _user_mb(here, u["id"]) > MAX_STORE_MB:
                raise JobLimit(f"بلغتَ حدّ التخزين ({MAX_STORE_MB} م.ب). "
                               f"نزّل صادراتك القديمة ثم أعد المحاولة.")
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
            if dur > MAX_VIDEO_S:
                os.path.isfile(out) and os.remove(out)
                raise JobLimit(f"المقطع {dur:.0f} ثانية، والحدّ {MAX_VIDEO_S}. "
                               f"اختر آياتٍ أقلّ.")
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

# ═══════════ تصنيف الأخطاء ═══════════
# لا يُعاد إلا ما يُرجى أن ينجح في المرّة الثانية. إعادةُ خطأِ المستخدم
# ثلاثَ مرّاتٍ تُنفق ثلاثةَ أضعاف الوقت لتصل إلى النتيجة نفسها.
NO_RETRY = (
    JobError,                 # وأبناؤها: JobConflict، JobLimit
    ValueError, TypeError, KeyError,   # حمولةٌ فاسدة — لن تصلح بالتكرار
    PermissionError, FileNotFoundError,
)
RETRYABLE = (
    TimeoutError, ConnectionError, OSError,    # شبكةٌ أو قرصٌ أو قِدرٌ ممتلئ
    sqlite3.OperationalError,                  # قاعدةٌ مقفلة لحظةً
    MemoryError,
)

def retryable(exc):
    """القاعدة: ما صُنِّف صراحةً بلا إعادة لا يُعاد، وما عداه يُعاد مرّتين.
    المجهولُ يُعاد لأن أغلب المجهول عابر — وسقفُ المحاولات يحدّ الخسارة."""
    if isinstance(exc, NO_RETRY): return False
    return True

def run_once(content_db, here, path=None, worker=None):
    """يسحب مهمّةً واحدة ويُنفّذها. يعيد المهمّة المنفَّذة أو None."""
    job = claim(path, worker)
    if not job: return None
    c = store.connect(path)
    try:
        try:
            res = perform(job, content_db, here, c)
        except Exception as e:
            rt = retryable(e)
            msg = str(e) if isinstance(e, JobError) else f"{type(e).__name__}: {e}"
            again = fail(c, job["id"], msg, retry=rt)
            return {**job, "ok": False, "error": msg,
                    "retryable": rt, "requeued": bool(again)}
        # الحصّة حُجزت عند الوضع في الطابور، فلا تُستهلك هنا مرّةً ثانية.
        complete(c, job["id"], res)
        return {**job, "ok": True, "result": res}
    finally:
        c.close()
