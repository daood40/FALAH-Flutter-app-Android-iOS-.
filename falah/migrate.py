"""هجرات مرقَّمة لـ`app.db` — تُطبَّق مرّةً، وتُسجَّل، ولا تحذف بلا إذن.

    python3 -m falah.migrate            # يطبّق ما لم يُطبَّق
    python3 -m falah.migrate --plan     # يقول ماذا سيفعل ولا يفعل
    python3 -m falah.migrate --status   # ما طُبِّق وما بقي

القاعدة الحاكمة: **لا هجرةَ هادمةٌ تجري بصمت.** كل هجرةٍ تُصنَّف. الآمنة
(عمودٌ جديد، فهرسٌ جديد، جدولٌ جديد) تجري وحدها. والهادمة — حذفُ عمودٍ أو
جدول، أو إعادةُ بناءٍ تنقل البيانات — لا تجري إلا بـ`FALAH_ALLOW_DESTRUCTIVE=1`
مع نسخةٍ احتياطية، وتطبع قبلها ما ستفعله بالضبط.

ولماذا `IF NOT EXISTS` في `store.SCHEMA` لا يكفي؟ لأنه يُنشئ الجدول
المفقود ولا يمسّ الموجود. قاعدةٌ أُنشئت قبل عمودٍ جديد تبقى بلا العمود،
فتنكسر عند أول قراءة. الهجرات هي ما يسدّ هذا الفرق.
"""
import os, sys, time

from . import store

class MigrationError(Exception): pass

LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations(
  version    INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  applied_at INTEGER NOT NULL,
  ms         INTEGER
);
"""

def _cols(c, table):
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}

def _has_table(c, table):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                          (table,)).fetchone())

def _has_index(c, name):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                          (name,)).fetchone())

# ═══════════ الهجرات ═══════════
# كلٌّ منها: (رقم، اسم، هادمة؟، دالّة). الدالّة تتحمّل أن تُنادى على قاعدةٍ
# طُبِّق فيها ما تفعله أصلًا (idempotent) — فإعادةُ التشغيل لا تكسر شيئًا.

def m001_jobs_queue(c):
    """جدول الطابور — يُنشئه SCHEMA أيضًا؛ هنا للقواعد الأقدم منه."""
    if not _has_table(c, "jobs"):
        c.executescript(store.SCHEMA)

def m002_jobs_idempotency(c):
    """مفتاح التفرّد ووقتُ الاستحقاق والفهارس — إضافةٌ محضة."""
    have = _cols(c, "jobs")
    if "idem_key" not in have:
        c.execute("ALTER TABLE jobs ADD COLUMN idem_key TEXT")
    if "not_before" not in have:
        c.execute("ALTER TABLE jobs ADD COLUMN not_before INTEGER NOT NULL DEFAULT 0")
    c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ix_jobs_idem ON jobs(idem_key)
                 WHERE idem_key IS NOT NULL AND state IN ('queued','running')""")
    # الفهرس القديم كان على (state, created_at)؛ الجديد يضمّ not_before
    c.execute("CREATE INDEX IF NOT EXISTS ix_jobs_queue2 ON jobs(state, not_before, created_at)")

def m003_jobs_state_guard(c):
    """قيودُ الحالة والتقدّم — لا يقبلها SQLite إلا ببناء الجدول من جديد.

    **هادمة بالتصنيف** لأنها تنسخ الجدول وتُسقط الأصل. ما يضيع في أسوأ
    الأحوال: مهامٌّ في الطابور لم تبدأ (تُعاد بضغطة). ولا يمسّ هذا مشروعًا
    ولا نصًّا ولا حسابًا. ومع ذلك لا تجري بلا إذنٍ صريح — القاعدة أهمّ من
    الاستثناء.
    """
    sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'"
                    ).fetchone()
    if sql and "CHECK (state IN" in (sql[0] or ""): return          # مطبَّقةٌ سلفًا
    c.execute("PRAGMA foreign_keys=OFF")
    c.executescript("""
      CREATE TABLE jobs_new(
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, payload TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'queued',
        attempts INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 2,
        progress INTEGER NOT NULL DEFAULT 0,
        step TEXT, error TEXT, result TEXT, worker TEXT, reserved TEXT,
        idem_key TEXT, not_before INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL, started_at INTEGER,
        finished_at INTEGER, heartbeat INTEGER,
        CHECK (state IN ('queued','running','done','failed','canceled')),
        CHECK (attempts >= 0 AND attempts <= max_attempts + 1),
        CHECK (progress BETWEEN 0 AND 100)
      );
      INSERT INTO jobs_new SELECT id,user_id,kind,payload,state,attempts,max_attempts,
        progress,step,error,result,worker,reserved,idem_key,not_before,
        created_at,started_at,finished_at,heartbeat FROM jobs;
      DROP TABLE jobs;
      ALTER TABLE jobs_new RENAME TO jobs;
      CREATE INDEX IF NOT EXISTS ix_jobs_queue ON jobs(state, not_before, created_at);
      CREATE INDEX IF NOT EXISTS ix_jobs_user  ON jobs(user_id, created_at DESC);
      CREATE UNIQUE INDEX IF NOT EXISTS ix_jobs_idem ON jobs(idem_key)
        WHERE idem_key IS NOT NULL AND state IN ('queued','running');
    """)
    c.execute("PRAGMA foreign_keys=ON")

def m004_jobs_index_names(c):
    """يوحّد فهرس الطابور — اسمًا وتعريفًا — على المسارين.

    كشفَه تشغيلُ البوّابة على قاعدةٍ **جديدة** لا مهاجَرة، فظهر انحرافان:

      • القاعدة الجديدة تنتهي بـ`ix_jobs_queue2` ولا `ix_jobs_queue` فيها،
        لأن `SCHEMA` صارت تحمل القيود فتُرجع الهجرةَ ٠٠٣ باكرًا.
      • القاعدة المهاجَرة تحمل الاثنين، والقديمُ منهما
        `(state, created_at)` — **بلا `not_before`**، وهو العمود الذي
        يستعلم به السحبُ فعلًا. أي فهرسٌ قائمٌ لا يخدم الاستعلام القائم.

    والانحرافُ بين مسارَي الإنشاء أخطر من الفهرس نفسه: قاعدتان تُظنّان
    سواءً وليستا كذلك، فيُختبر أحدُهما ويُنشر الآخر.

    آمنةٌ بالتصنيف: الفهارس تُبنى من البيانات ولا تحملها — حذفُها وإعادةُ
    بنائها لا تمسّ صفًّا واحدًا.
    """
    if not _has_table(c, "jobs"): return
    c.execute("DROP INDEX IF EXISTS ix_jobs_queue2")
    c.execute("DROP INDEX IF EXISTS ix_jobs_queue")
    c.execute("CREATE INDEX ix_jobs_queue ON jobs(state, not_before, created_at)")

MIGRATIONS = [
    (1, "jobs_queue",        False, m001_jobs_queue),
    (2, "jobs_idempotency",  False, m002_jobs_idempotency),
    (3, "jobs_state_guard",  True,  m003_jobs_state_guard),
    (4, "jobs_index_names",  False, m004_jobs_index_names),
]

# ═══════════ المشغّل ═══════════

def applied(c):
    c.executescript(LEDGER); c.commit()
    return {r[0] for r in c.execute("SELECT version FROM schema_migrations")}

def pending(c):
    done = applied(c)
    return [m for m in MIGRATIONS if m[0] not in done]

def production_guard(quiet=False):
    """في الإنتاج: لا هجرةَ هادمةٌ بلا نسخةٍ **مُسترجَعةٍ مُتحقَّقٍ منها**.

    الحارس هنا لا في `dbsafe.py` وحده، لأن `python3 -m falah.migrate` يُشغَّل
    مباشرةً فيتخطّى أي فحصٍ خارجيّ. ملفُّ نسخةٍ موجودٌ لا يكفي: البيان يجب
    أن يحمل `verified_at`، أي أن أحدًا فكّها وفتحها وعدّ صفوفها فعلًا.
    """
    if os.environ.get("FALAH_ENV", "development").strip().lower() not in ("production", "prod"):
        return True, ""
    import glob, json as _json
    d = os.environ.get("FALAH_BACKUP_DIR",
                       os.path.join(os.path.dirname(os.path.dirname(
                           os.path.abspath(__file__))), "backups"))
    mans = sorted(glob.glob(os.path.join(d, "*.db.gz.json")), key=os.path.getmtime,
                  reverse=True)
    for m in mans[:1]:
        try:
            if _json.load(open(m)).get("verified_at"):
                return True, ""
        except Exception:
            pass
    return False, ("إنتاجٌ + هجرةٌ هادمة + بلا نسخةٍ مُسترجَعةٍ متحقَّقٍ منها.\n"
                   "     python3 dbsafe.py backup && python3 dbsafe.py restore-test")

def run(c=None, allow_destructive=None, plan_only=False, quiet=False):
    """يطبّق ما لم يُطبَّق. يعيد (طُبِّقت، مؤجَّلةٌ لأنها هادمة)."""
    own = c is None
    c = c or store.connect()
    if allow_destructive is None:
        allow_destructive = os.environ.get("FALAH_ALLOW_DESTRUCTIVE") == "1"
    if allow_destructive and not plan_only:
        # الإذن الصريح يفتح الباب، والحارس يقف عنده. الاثنان معًا لا أحدهما.
        okg, why = production_guard()
        if not okg:
            allow_destructive = False
            if not quiet: print(f"  ⛔ الحارس أوقف الهجرات الهادمة: {why}")
    ran, held = [], []
    try:
        for ver, name, destructive, fn in pending(c):
            if destructive and not allow_destructive:
                held.append((ver, name))
                if not quiet:
                    print(f"  ⛔ {ver:03d} {name} — هادمةٌ بالتصنيف، موقوفة.\n"
                          f"     {(fn.__doc__ or '').strip().splitlines()[0]}\n"
                          f"     للتشغيل بعد نسخةٍ احتياطية: "
                          f"FALAH_ALLOW_DESTRUCTIVE=1 python3 -m falah.migrate")
                continue
            if plan_only:
                ran.append((ver, name))
                if not quiet: print(f"  → {ver:03d} {name}"
                                    + ("  (هادمة)" if destructive else ""))
                continue
            t0 = time.time()
            fn(c)
            c.execute("INSERT INTO schema_migrations(version,name,applied_at,ms) "
                      "VALUES(?,?,?,?)", (ver, name, store.now(),
                                          int((time.time() - t0) * 1000)))
            c.commit()
            ran.append((ver, name))
            if not quiet: print(f"  ✓ {ver:03d} {name}  ({(time.time()-t0)*1000:.0f} م.ث)")
        if not ran and not held and not quiet:
            print("  ✓ لا هجرةَ معلّقة")
        return ran, held
    finally:
        if own: c.close()

def status(c=None):
    own = c is None
    c = c or store.connect()
    try:
        done = applied(c)
        for ver, name, destructive, _ in MIGRATIONS:
            mark = "✓" if ver in done else ("⛔" if destructive else "·")
            print(f"  {mark} {ver:03d} {name}" + ("  (هادمة)" if destructive else ""))
        return done
    finally:
        if own: c.close()

if __name__ == "__main__":
    store.init()
    if "--status" in sys.argv: status()
    else:
        ran, held = run(plan_only="--plan" in sys.argv)
        sys.exit(2 if held and "--strict" in sys.argv else 0)
