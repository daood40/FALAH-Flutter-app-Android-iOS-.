#!/usr/bin/env python3
"""سلامة قاعدة التطبيق — فحصٌ ونسخٌ واسترجاعٌ وبروفةُ هجرة.

    python3 dbsafe.py check           # سلامةٌ وأعدادٌ وحالة الهجرات
    python3 dbsafe.py backup          # نسخةٌ حيّة موقَّعةٌ ببصمتها
    python3 dbsafe.py restore-test    # يسترجع آخر نسخةٍ ويتحقّق منها فعلًا
    python3 dbsafe.py migrate-check   # يُجري الهجرات على **نسخةٍ** ويقارن
    python3 dbsafe.py guard           # هل يجوز تشغيل هجرةٍ هادمة الآن؟

القاعدة الحاكمة، وهي التي وُجد هذا الملفّ من أجلها:

    إنتاج + هجرةٌ هادمة + بلا نسخةٍ مُستَرجَعةٍ مُتحقَّقٍ منها  =  ممنوع

ولا يكفي وجود ملفّ نسخة: النسخة التي لم تُسترجَع ليست نسخة، هي ملفٌّ
يُظنّ به الخير. لذلك `restore-test` يفكّها ويفتحها ويعدّ صفوفها ويشغّل
`integrity_check` عليها — ثم يقول.

و`migrate-check` لا يلمس قاعدتك أبدًا: ينسخها، ويهاجر النسخة، ويقارن
الأعداد صفًّا صفًّا قبل وبعد. فإن نقص شيءٌ ظهر قبل أن يقع.
"""
import gzip, hashlib, json, os, shutil, sqlite3, subprocess, sys, tempfile, time
from collections.abc import Callable

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from falah import store, migrate as MG           # noqa: E402

BACKUPS = os.environ.get("FALAH_BACKUP_DIR", os.path.join(HERE, "backups"))
# «إنتاج» ليس تخمينًا: يُعلَن صراحةً. وما لم يُعلَن يُعامَل معاملة التطوير.
ENV = os.environ.get("FALAH_ENV", "development").strip().lower()

OK = FAIL = 0
def ok(msg, cond, detail=""):
    global OK, FAIL
    if cond: OK += 1; print(f"  ✓ {msg}" + (f"  ({detail})" if detail else ""))
    else:    FAIL += 1; print(f"  ✗ {msg}" + (f"  ← {detail}" if detail else ""))
    return cond

def head(t): print(f"\n▸ {t}")

# ───────────────────────── أدوات ─────────────────────────

def counts(path):
    """أعدادُ صفوف كل جدول — مقياسُ «هل بقيت البيانات؟»."""
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        out = {}
        for (t,) in c.execute("""SELECT name FROM sqlite_master WHERE type='table'
                                 AND name NOT LIKE 'sqlite_%' ORDER BY name"""):
            out[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        return out
    finally:
        c.close()

def integrity(path):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return (c.execute("PRAGMA integrity_check").fetchone()[0],
                c.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        c.close()

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def live_copy(src, dst):
    """نسخةٌ متّسقة والخدمة تعمل — واجهة `backup` في SQLite لا `cp`.
    نسخُ الملفّ بـ`cp` مع WAL قد يلتقط حالةً نصفَ مكتوبة."""
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    try:
        with d: s.backup(d)
    finally:
        s.close(); d.close()
    return dst

def latest_backup():
    if not os.path.isdir(BACKUPS): return None
    gz = sorted((f for f in os.listdir(BACKUPS) if f.endswith(".db.gz")),
                key=lambda f: os.path.getmtime(os.path.join(BACKUPS, f)), reverse=True)
    return os.path.join(BACKUPS, gz[0]) if gz else None

def manifest_of(gz):
    p = gz + ".json"
    return json.load(open(p)) if os.path.exists(p) else None

# ───────────────────────── الأوامر ─────────────────────────

def ensure(path):
    """يُنشئ قاعدةَ تطبيقٍ فارغةً إن لم توجد — كما يفعل الخادم عند إقلاعه.

    أوّلُ تشغيلٍ بعد `git clone` لا قاعدةَ فيه. وسقوطُ البوّابة حينها يقول
    للمطوّر الجديد إن شيئًا معطوب، والحقيقة أنه لم يبدأ بعد. الإنشاء هنا
    إضافةٌ محضة لا تمسّ قاعدةً قائمة.
    """
    if os.path.exists(path): return False
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    store.init(path).close()
    return True

def cmd_check(path=None):
    path = path or store.APP_DB
    head(f"فحص القاعدة — {os.path.basename(path)}")
    if ensure(path):
        print("    (لم تكن موجودة — أُنشئت فارغةً كما يفعل الخادم)")
    ok("القاعدة موجودة", True, f"{os.path.getsize(path)/1048576:.1f} م.ب")

    ic, fk = integrity(path)
    ok("integrity_check", ic == "ok", ic)
    ok("foreign_key_check", not fk, f"{len(fk)} خرقًا" if fk else "")

    cs = counts(path)
    print(f"    الجداول: {len(cs)} · الصفوف: {sum(cs.values())}")
    for t, n in sorted(cs.items()): print(f"      {t:<20} {n:>7}")

    c = store.connect(path)
    try:
        applied = MG.applied(c)
        pend = MG.pending(c)
        ver = max(applied) if applied else 0
        print(f"\n    database version : {ver}")
        print(f"    pending          : {[f'{m[0]:03d}:{m[1]}' for m in pend] or 'لا شيء'}")
        dest = [f"{m[0]:03d}:{m[1]}" for m in pend if m[2]]
        print(f"    destructive      : {dest or 'لا شيء'}")
        if "jobs" in cs:
            st = dict(c.execute("SELECT state, COUNT(*) FROM jobs GROUP BY state").fetchall())
            print(f"    حالات المهامّ     : {st or 'فارغ'}")
    finally:
        c.close()

    b = latest_backup()
    if b:
        m = manifest_of(b)
        age = (time.time() - os.path.getmtime(b)) / 3600
        print(f"\n    backup status    : {os.path.basename(b)} · قبل {age:.1f} ساعة")
        print(f"    restore verified : "
              f"{'نعم — ' + m['verified_at'] if m and m.get('verified_at') else '**لا**'}")
    else:
        print("\n    backup status    : **لا نسخة**")
    print(f"    environment      : {ENV}")
    return FAIL == 0

def cmd_backup(path=None, quiet=False):
    """نسخةٌ حيّة + بيانٌ يحمل بصمتها وأعدادها. البيان هو ما يجعل الاسترجاع
    قابلًا للتحقّق: نقارن ما استُرجع بما نُسخ، لا نثق بالحجم."""
    path = path or store.APP_DB
    os.makedirs(BACKUPS, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw = os.path.join(BACKUPS, f"app-{stamp}.db")
    live_copy(path, raw)
    ic, fk = integrity(raw)
    if ic != "ok" or fk:
        os.remove(raw)
        raise SystemExit(f"النسخة نفسها معطوبة ({ic}) — لم تُحفظ")
    cs = counts(raw)
    with open(raw, "rb") as fi, gzip.open(raw + ".gz", "wb") as fo:
        shutil.copyfileobj(fi, fo)
    digest = sha256(raw)
    os.remove(raw)
    man = {"source": os.path.abspath(path), "created_at": stamp,
           "sha256_uncompressed": digest, "bytes_gz": os.path.getsize(raw + ".gz"),
           "counts": cs, "integrity": ic, "env": ENV, "verified_at": None,
           "migrations": sorted(MG.applied(store.connect(path)))}
    json.dump(man, open(raw + ".gz.json", "w"), ensure_ascii=False, indent=2)
    if not quiet:
        head("نسخةٌ احتياطية")
        ok("نُسخت وسُلِّمت", True, os.path.basename(raw + ".gz"))
        ok("سليمةٌ قبل الضغط", ic == "ok")
        print(f"    {sum(cs.values())} صفًّا في {len(cs)} جدولًا · "
              f"{man['bytes_gz']/1024:.0f} ك.ب")
        print(f"    البصمة: {digest[:16]}…")
        print("    ⚠ لم تُسترجَع بعد — شغّل `restore-test` قبل أن تُعدّها نسخة.")
    return raw + ".gz"

def cmd_restore_test(gz=None):
    """يفكّها ويفتحها ويعدّها ويشغّل عليها التطبيق — ثم يوقّع البيان."""
    head("اختبار الاسترجاع")
    gz = gz or latest_backup()
    if not ok("توجد نسخة", bool(gz), "" if gz else "لا شيء في " + BACKUPS): return False
    print(f"    {os.path.basename(gz)}")
    man = manifest_of(gz)
    if not ok("النسخة معها بيانُها", bool(man)): return False

    tmp = tempfile.mkdtemp(prefix="falah-restore-")
    out = os.path.join(tmp, "restored.db")
    try:
        with gzip.open(gz, "rb") as fi, open(out, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        ok("فُكّت", os.path.getsize(out) > 0, f"{os.path.getsize(out)/1048576:.1f} م.ب")
        ok("البصمة تطابق ما نُسخ", sha256(out) == man["sha256_uncompressed"])

        ic, fk = integrity(out)
        ok("integrity_check على المسترجَعة", ic == "ok", ic)
        ok("foreign_key_check على المسترجَعة", not fk)

        cs = counts(out)
        same = cs == man["counts"]
        ok("الأعداد مطابقةٌ جدولًا جدولًا", same,
           str({k: (man["counts"].get(k), v) for k, v in cs.items()
                if man["counts"].get(k) != v}) if not same else
           f"{sum(cs.values())} صفًّا")

        # الاختبار الحقيقيّ: هل يقلع التطبيق عليها ويردّ؟
        env = dict(os.environ, FALAH_APP_DB=out, PORT="8123",
                   FALAH_INLINE_WORKER="0")
        p = subprocess.Popen([sys.executable, "app.py"], cwd=HERE, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             start_new_session=True)
        try:
            import urllib.request
            live = ready = False
            for _ in range(60):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8123/healthz", timeout=2) as r:
                        live = r.status == 200; break
                except Exception: time.sleep(0.5)
            ok("التطبيق يقلع على القاعدة المسترجَعة", live)
            if live:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8123/readyz", timeout=5) as r:
                        ready = json.loads(r.read())["ready"]
                except Exception as e:
                    ready = False; print("   ", type(e).__name__)
                ok("ويعلن جاهزيّته", ready)
                # قراءةٌ حقيقية من بياناتٍ مسترجَعة
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8123/app/plans", timeout=5) as r:
                        plans = json.loads(r.read())
                    ok("ويخدم طلبًا فعليًّا", len(plans.get("plans", [])) == 3)
                except Exception as e:
                    ok("ويخدم طلبًا فعليًّا", False, type(e).__name__)
        finally:
            p.kill(); p.wait(timeout=15)

        if FAIL == 0:
            man["verified_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            man["verified_counts"] = cs
            json.dump(man, open(gz + ".json", "w"), ensure_ascii=False, indent=2)
            print(f"\n    وُقِّع البيان: الاسترجاع متحقَّقٌ منه في {man['verified_at']}")
        return FAIL == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def cmd_migrate_check(path=None, seed_states=True):
    """بروفةُ هجرةٍ على نسخةٍ من القاعدة الحقيقية — لا على قاعدةٍ فارغة.

    الفرق جوهريّ: هجرةٌ تعيد بناء جدولٍ تنجح دائمًا على جدولٍ فارغ. الاختبار
    الحقيقيّ أن تنجح على جدولٍ فيه صفوفٌ في كل حالة، وأن تُبقيها كما هي.
    """
    path = path or store.APP_DB
    head("بروفة الهجرات على نسخةٍ من القاعدة الحقيقية")
    if ensure(path):
        print("    (لم تكن موجودة — أُنشئت فارغةً؛ البروفة على قاعدةٍ جديدة)")
    tmp = tempfile.mkdtemp(prefix="falah-migchk-")
    work = os.path.join(tmp, "copy.db")
    try:
        live_copy(path, work)
        ok("نُسخت القاعدة للبروفة", os.path.exists(work),
           f"{os.path.getsize(work)/1048576:.1f} م.ب")

        # القاعدة الحيّة قد تخلو من بعض الحالات؛ نزرعها لتُختبر كلُّها
        if seed_states:
            c = sqlite3.connect(work)
            row = c.execute("SELECT user_id, kind, payload FROM jobs LIMIT 1").fetchone()
            if row:
                t = int(time.time())
                for i, st in enumerate(("queued", "running", "failed", "canceled")):
                    c.execute("""INSERT INTO jobs(user_id,kind,payload,state,attempts,
                                 max_attempts,progress,step,created_at,started_at,heartbeat)
                                 VALUES(?,?,?,?,?,2,?,?,?,?,?)""",
                              (row[0], row[1], row[2], st, 1 if st != "queued" else 0,
                               50 if st == "running" else 0, f"بذرة {st}", t, t, t))
                c.commit()
            c.close()
            print("    زُرعت صفوفٌ في كل حالةٍ لتُختبر الهجرة عليها")

        before = counts(work)
        st_before = dict(sqlite3.connect(work).execute(
            "SELECT state, COUNT(*) FROM jobs GROUP BY state").fetchall())
        rows_before = sqlite3.connect(work).execute(
            "SELECT id,user_id,kind,state,attempts,created_at FROM jobs ORDER BY id").fetchall()
        print(f"    قبل: {sum(before.values())} صفًّا · حالات المهامّ {st_before}")

        c = store.connect(work)
        try:
            ran, held = MG.run(c, allow_destructive=True, quiet=True)
        finally:
            c.close()
        ok("جرت الهجرات المعلّقة", True, str([f"{v:03d}:{n}" for v, n in ran]) or "لا شيء")

        after = counts(work)
        st_after = dict(sqlite3.connect(work).execute(
            "SELECT state, COUNT(*) FROM jobs GROUP BY state").fetchall())
        rows_after = sqlite3.connect(work).execute(
            "SELECT id,user_id,kind,state,attempts,created_at FROM jobs ORDER BY id").fetchall()

        # `schema_migrations` يُتوقَّع أن ينمو بعدد ما جرى — وهو سجلُّ الهجرات
        # نفسه. استثناؤه ليس تساهلًا: نموُّه يُقاس بدقّةٍ في السطر الذي يليه.
        lost = {k: (before[k], after.get(k)) for k in before
                if k != "schema_migrations" and before[k] != after.get(k)}
        ok("لا صفَّ ضاع في أي جدول", not lost, str(lost))
        grew = after.get("schema_migrations", 0) - before.get("schema_migrations", 0)
        ok("سجلّ الهجرات نما بعدد ما جرى لا أكثر", grew == len(ran),
           f"{before.get('schema_migrations')} → {after.get('schema_migrations')} "
           f"مقابل {len(ran)} هجرة")
        ok("حالات المهامّ كما هي", st_before == st_after, f"{st_before} → {st_after}")
        ok("صفوف المهامّ نفسها حرفًا بحرف", rows_before == rows_after,
           f"{len(rows_before)} → {len(rows_after)}")

        ic, fk = integrity(work)
        ok("integrity_check بعد الهجرة", ic == "ok", ic)
        ok("foreign_key_check بعد الهجرة", not fk)

        c2 = sqlite3.connect(work)
        sql = c2.execute("SELECT sql FROM sqlite_master WHERE name='jobs'").fetchone()[0]
        ok("القيود صارت في الجدول", "CHECK (state IN" in sql)
        idx = {r[0] for r in c2.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='jobs'")}
        ok("الفهارس أُعيدت كلّها", {"ix_jobs_queue", "ix_jobs_user", "ix_jobs_idem"} <= idx,
           str(sorted(idx)))

        # القيد يمنع فعلًا لا شكلًا. وعلى جدولٍ فارغ لا صفَّ يُخالَف به،
        # فتُدرَج حالةٌ خاطئة مباشرةً — وهي الصورة الأصدق للاختبار أصلًا.
        u = c2.execute("SELECT id FROM users LIMIT 1").fetchone()
        bad = prog = False
        if u:
            try:
                c2.execute("""INSERT INTO jobs(user_id,kind,payload,state,created_at)
                              VALUES(?,'export','{}','لا-حالة',0)""", (u[0],))
                c2.commit()
            except sqlite3.IntegrityError:
                bad = True
            try:
                c2.execute("""INSERT INTO jobs(user_id,kind,payload,state,progress,created_at)
                              VALUES(?,'export','{}','queued',500,0)""", (u[0],))
                c2.commit()
            except sqlite3.IntegrityError:
                prog = True
            c2.execute("DELETE FROM jobs WHERE created_at=0"); c2.commit()
            ok("القيد يرفض حالةً غير معروفة فعلًا", bad)
            ok("والقيد يرفض تقدّمًا خارج ٠–١٠٠", prog)
        else:
            print("    (لا مستخدمين في القاعدة — القيود تُختبر في tests.py)")
        c2.close()

        # تكرار التشغيل لا يكرّر شيئًا
        c3 = store.connect(work)
        try:
            again = MG.run(c3, allow_destructive=True, quiet=True)
        finally:
            c3.close()
        ok("إعادة التشغيل لا تُعيد هجرةً طُبِّقت", again == ([], []), str(again))
        ok("الأعداد لم تتغيّر بإعادة التشغيل", counts(work) == after)
        return FAIL == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def cmd_guard():
    """الحارس: هل يجوز تشغيل هجرةٍ هادمة على هذه القاعدة الآن؟"""
    head("حارس الهجرات الهادمة")
    c = store.connect()
    try:
        dest = [(v, n) for v, n, d, _ in MG.pending(c) if d]
    finally:
        c.close()
    if not dest:
        print("  · لا هجرةَ هادمةٌ معلّقة — لا شيء يُحرس.")
        return True

    print(f"  معلّقة: {[f'{v:03d}:{n}' for v, n in dest]}")
    b = latest_backup()
    man = manifest_of(b) if b else None
    verified = bool(man and man.get("verified_at"))
    allowed = os.environ.get("FALAH_ALLOW_DESTRUCTIVE") == "1"
    prod = ENV in ("production", "prod")

    ok("توجد نسخةٌ احتياطية", bool(b), os.path.basename(b) if b else "لا شيء")
    ok("والنسخة استُرجعت وتُحقّق منها",
       verified, man.get("verified_at") if man and man.get("verified_at") else "لم تُسترجَع")
    print(f"    environment: {ENV} · FALAH_ALLOW_DESTRUCTIVE={'1' if allowed else 'غير مضبوط'}")

    if prod and not verified:
        print("\n  ⛔ ممنوع: **إنتاج + هجرةٌ هادمة + بلا نسخةٍ مُسترجَعة**.")
        print("     python3 dbsafe.py backup && python3 dbsafe.py restore-test")
        return False
    if prod and not allowed:
        print("\n  ⛔ موقوف: الإنتاج يحتاج إذنًا صريحًا (FALAH_ALLOW_DESTRUCTIVE=1).")
        return False
    if not prod:
        print("\n  · بيئةُ تطوير — الحارس لا يمنع، لكن `migrate-check` يبقى واجبًا.")
    return True

# ───────────────────────── التشغيل ─────────────────────────

# النوعُ مكتوبٌ صراحةً لأنّ أنواعَ الرجوع مختلفة، فيستنتج mypy `object`
# ويرفض النداءَ في السطر ٤٠٤. والرجوعُ `object` مقصود: الشرطُ أدناه
# `r is not False` وحدَه، فأيُّ قيمةٍ غيرِ False تعني نجاحًا.
CMDS: dict[str, Callable[[], object]] = {
    "check": cmd_check, "backup": cmd_backup, "restore-test": cmd_restore_test,
    "migrate-check": cmd_migrate_check, "guard": cmd_guard}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd not in CMDS:
        print(f"أوامر: {' · '.join(CMDS)}"); sys.exit(2)
    r = CMDS[cmd]()
    print(f"\n{'—'*40}\nنجح {OK} · سقط {FAIL}" if (OK or FAIL) else "")
    sys.exit(0 if (r is not False and FAIL == 0) else 1)
