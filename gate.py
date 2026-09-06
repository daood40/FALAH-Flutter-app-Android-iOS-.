#!/usr/bin/env python3
"""بوّابة الجودة — أمرٌ واحد، وسقوطٌ لا يُخفى.

    python3 gate.py              # الكلّ، ويقف عند أول سقوطٍ حرج
    python3 gate.py --keep-going # يُكمل ليُري كلَّ ما سقط
    python3 gate.py --list       # يعرض البوّابات ولا يشغّل
    python3 gate.py lint types   # بوّاباتٌ بعينها

القاعدة: البوّابةُ الحرجة إذا سقطت **توقّف كلَّ شيء** وتطبع:

    FAILED:  ماذا · لماذا · بأي أمر · في أي ملفّ وسطر · وما الإصلاح المقترح

ولا تُلمَّع الأرقام: ما لم يُشغَّل يُقال عنه BLOCKED، لا PASS.
"""
import argparse, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PORT = os.environ.get("PORT", "8080")
APP = f"http://localhost:{PORT}"

# (المفتاح، العنوان، الأمر، حرجة؟، اقتراحُ الإصلاح، شرطُ التوفّر)
GATES = [
    ("deps",     "ثغرات الاعتماديات",
     [PY, "-m", "pip_audit", "-r", "requirements.txt", "--progress-spinner", "off"],
     True, "ارفع الإصدارَ الذي يذكره الفحص في requirements.txt ثم أعد الاختبارات",
     lambda: shutil.which("pip-audit") or _mod("pip_audit")),
    ("lint",     "التحليل الساكن (ruff)", ["ruff", "check", "."],
     True, "ruff check . --fix — وما لا يُصلَح آليًّا يُصلَح بيدك أو يُستثنى بسببٍ مكتوب",
     lambda: shutil.which("ruff")),
    ("types",    "فحص الأنواع (mypy)", ["mypy", "."],
     True, "أضِف التعليق النوعيّ الذي يطلبه، أو أصلح الاستدعاء المخالف",
     lambda: shutil.which("mypy")),
    ("security", "الأسرار والإعداد", [PY, "security_scan.py"],
     True, "انقل السرَّ إلى ملفّ بيئةٍ خارج الشجرة (launch/CREDENTIALS.md)", None),
    ("contract", "عقد الـAPI", [PY, "api_contract.py", "--check"],
     True, "python3 api_contract.py — ثم وثّق أي مسارٍ جديد في SPEC", None),
    ("db",       "سلامة القاعدة", [PY, "dbsafe.py", "check"],
     True, "integrity_check ساقط ← استرجِع من نسخةٍ احتياطية", None),
    ("migrate",  "بروفة الهجرات على نسخة", [PY, "dbsafe.py", "migrate-check"],
     True, "لا تطبّق الهجرة على الإنتاج — راجع ما سقط في البروفة أوّلًا", None),
    ("unit",     "اختبارات الوحدة والتكامل", [PY, "tests.py"],
     True, "شغّل tests.py وحدها واقرأ أول ✗ — الرسالة تسمّي ما اختُبر", None),
    ("audit",    "الفحص الشامل عبر الشبكة", [PY, "audit.py"],
     True, "يلزمه خادمٌ يعمل — البوّابة تشغّله. اقرأ البند الساقط",
     None),
    ("ui",       "فحص الواجهة في متصفّح", [PY, "ui_audit.py"],
     True, "افتح المتصفّح على المسار نفسه وكرّر الخطوة يدويًّا", None),
    ("failure",  "الكسر المتعمَّد", [PY, "failure_test.py"],
     True, "سقوطٌ هنا يعني ضياعَ عملٍ أو رسالةً غامضة عند العطب", None),
    ("leak",     "تسريب الأخطاء والسجلّ", [PY, "leak_test.py"],
     True, "أزِل ما يُسرَّب من الردّ وانقله إلى log_error", None),
    ("isolation", "حدود المستخدم والملفّات", [PY, "isolation_test.py"],
     True, "سقوطٌ هنا يعني أن مستخدمًا يبلغ مورِدَ غيره — أوقف كلَّ شيء وأصلحه",
     None),
    ("authz",    "طبقة الإذن", [PY, "authz_test.py"],
     True, "سقوطٌ هنا يعني قرارَ إذنٍ خاطئًا أو مسارًا بلا سياسة — أوقف كلَّ شيء وأصلحه",
     None),
    ("rbac",     "الأدوار والتدقيق", [PY, "rbac_test.py"],
     True, "سقوطٌ هنا يعني تصعيدَ امتيازٍ ممكنًا أو سجلًّا لا يُوثق به — أوقف كلَّ شيء",
     None),
    ("invariants", "الثوابت الأمنية", [PY, "invariants.py"],
     True, "خرقُ ثابتٍ أمنيّ — اقرأ اسمَه ومعناه في المخرَج. لا يُخفَّف ثابتٌ لتمرّ بوّابة",
     None),
    ("sched",    "الجدولة", [PY, "sched_test.py"],
     True, "سقوطٌ هنا يعني إمّا توقيتًا ينزاح بالتوقيت الصيفيّ، وإمّا جدولًا "
           "يُنفَّذ مرّتين، وإمّا مشروعَ غيرِك يُجدوَل",
     None),
    ("obs",      "المراقبة", [PY, "obs_test.py"],
     True, "سقوطٌ هنا يعني إمّا سرًّا في سجلّ، وإمّا انفجارًا عدديًّا في "
           "المقاييس، وإمّا عطبَ مراقبةٍ يُسقط طلبًا. ولا يُخفَّف الفاحص",
     None),
    ("cors",     "حدودُ الأصل", [PY, "cors_test.py"],
     True, "سقوطٌ هنا يعني إمّا أصلًا غريبًا يقرأ ردًّا يحمل جلسة، وإمّا عميلًا "
           "أصليًّا لا يستطيع الدخول. ولا يُوسَّع الأصلُ لتمرّ بوّابة",
     None),
    ("docker",   "إعداد الحاوية", None,
     True, "docker compose config يشرح الخطأ", None),
    ("build",    "بناء صورة الحاوية", ["docker", "build", "-t", "falah:gate", "."],
     False, "شغّل عفريت docker ثم أعد",
     lambda: _docker_up()),
]

def _mod(name):
    try:    __import__(name); return True
    except Exception: return False

def _docker_up():
    if not shutil.which("docker"): return False
    r = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    return r.returncode == 0

# ───────────────────────── تشغيل ─────────────────────────

def find_where(output):
    """يستخرج ملفًّا وسطرًا من مخرجات الأداة — أيًّا كانت صيغتها."""
    for pat in (r'File "([^"]+)", line (\d+)',
                r"--> ([\w./\\-]+\.py):(\d+)",
                r"^([\w./\\-]+\.py):(\d+):",
                r"([\w./\\-]+\.py):(\d+)"):
        m = re.search(pat, output, re.M)
        if m: return m.group(1), m.group(2)
    return None, None

def first_failure(output):
    """أوّلُ سطرٍ يصف السقوط — لا آخرُ سطرٍ في المخرجات."""
    for line in output.splitlines():
        if line.strip().startswith("✗") or line.startswith("  ✗"):
            return line.strip()
    for line in output.splitlines():
        if re.search(r"\b(error|Error|FAIL|فشل|سقط)\b", line): return line.strip()
    return (output.strip().splitlines() or ["—"])[-1][:200]

def run_gate(g, env, timeout=1800):
    key, title, cmd, critical, fix, avail = g
    if key == "docker":
        cmd = ["docker", "compose", "-f", "deploy/docker-compose.yml", "config"]
        env = dict(env, FALAH_DOMAIN=env.get("FALAH_DOMAIN", "gate.example.com"))
        if not shutil.which("docker"):
            return "BLOCKED", "لا docker في هذه البيئة", "", 0.0
    if avail is not None and not avail():
        why = {"deps": "pip-audit غير مثبَّت أو لا شبكة",
               "build": "عفريت docker غير مشتغل",
               "lint": "ruff غير مثبَّت", "types": "mypy غير مثبَّت"}.get(key, "غير متاح")
        return "BLOCKED", why, "", 0.0
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=HERE, env=env, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "FAIL", f"تجاوز {timeout}ث", "", time.time() - t0
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 and key == "deps" and re.search(
            r"Failed to upgrade|ConnectionError|Temporary failure|"
            r"Network is unreachable|Could not find a version|resolve", out, re.I):
        # فرقٌ جوهريّ: «لا شبكة» ليس «لا ثغرات» وليس «فيه ثغرات».
        # الخلط بينها يجعل انقطاعَ الشبكة يبدو نجاحًا أو يبدو عطبًا في الشيفرة.
        return "BLOCKED", "لا وصولَ إلى قاعدة الثغرات (شبكة)", out, time.time() - t0
    return ("PASS" if r.returncode == 0 else "FAIL"), "", out, time.time() - t0

LOGS = os.environ.get("FALAH_GATE_LOGS", os.path.join(HERE, ".gate-logs"))

def serve(env):
    """يشغّل الخادم والعامل للبوّابات التي تحتاج شبكة."""
    os.makedirs(LOGS, exist_ok=True)
    subprocess.run(["bash", "-c", f"fuser -k {PORT}/tcp 2>/dev/null || true"],
                   capture_output=True)
    time.sleep(1)
    e = dict(env, FALAH_INLINE_WORKER="0")
    a = subprocess.Popen([PY, "app.py"], cwd=HERE, env=e,
                         stdout=open(os.path.join(LOGS, "app.log"), "w"),
                         stderr=subprocess.STDOUT, start_new_session=True)
    w = subprocess.Popen([PY, "worker.py"], cwd=HERE, env=e,
                         stdout=open(os.path.join(LOGS, "worker.log"), "w"),
                         stderr=subprocess.STDOUT, start_new_session=True)
    import urllib.request
    for _ in range(80):
        try:
            with urllib.request.urlopen(f"{APP}/healthz", timeout=2) as r:
                if r.status == 200: return a, w, True
        except Exception: time.sleep(0.5)
    return a, w, False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*")
    ap.add_argument("--keep-going", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for k, t, _, c, _, _ in GATES:
            print(f"  {k:<10} {'حرجة' if c else 'غير حرجة':<10} {t}")
        return 0

    gates = [g for g in GATES if not a.only or g[0] in a.only]
    # حزم الفحص تسجّل عشرات الحسابات من عنوانٍ واحد، فتبلغ حدَّ التسجيل
    # «لكل عنوان». التجاوز يُعلَن هنا صراحةً ولا يُضعَّف الافتراضيُّ في الإنتاج.
    #
    env = dict(os.environ, APP=APP, API=APP, FALAH_RATE_REGISTER="10000")
    results, srv = [], None
    needs_net = {"audit", "ui"}

    print("═" * 62)
    print("  QUALITY GATE — فَلاح")
    print("═" * 62)
    try:
        for g in gates:
            key, title, _, critical, fix, _ = g
            if key in needs_net and srv is None:
                srv = serve(env)
                if not srv[2]:
                    print(f"\n  ✗ {'الخادم لم يقم':<34} FAIL")
                    print("\nFAILED:\n  reason  : الخادم لم يستجب لـ/healthz")
                    print(f"  command : python3 app.py\n  file    : {LOGS}/app.log")
                    print(f"  fix     : اقرأ {LOGS}/app.log — "
                          "الغالب إعدادٌ ناقص أو منفذٌ مشغول")
                    return 1
            status, why, out, secs = run_gate(g, env)
            results.append((key, title, status, why, secs))
            mark = {"PASS": "✓", "FAIL": "✗", "BLOCKED": "!"}[status]
            tail = f"  ({why})" if why else (f"  {secs:.0f}ث" if secs > 2 else "")
            print(f"  {mark} {title:<34} {status}{tail}")

            if status == "FAIL":
                f, ln = find_where(out)
                print("\n" + "─" * 62)
                print("FAILED:")
                print(f"  gate    : {key} — {title}")
                print(f"  reason  : {first_failure(out)[:180]}")
                print(f"  command : make {key}" if key in
                      ("lint", "types", "security", "contract", "unit", "audit", "authz", "rbac", "invariants",
                       "ui", "failure", "leak", "deps", "cors", "obs", "sched")
                      else f"  command : {' '.join(g[2] or [])}")
                print(f"  file    : {f or '—'}" + (f":{ln}" if ln else ""))
                print(f"  fix     : {fix}")
                print("─" * 62)
                if critical and not a.keep_going:
                    print("\nQUALITY_GATE = FAIL  (توقّفت عند أول سقوطٍ حرج)")
                    return 1
    finally:
        if srv:
            for p in srv[:2]:
                try: p.kill(); p.wait(timeout=10)
                except Exception: pass

    print("\n" + "═" * 62)
    fails = [r for r in results if r[2] == "FAIL"]
    blocked = [r for r in results if r[2] == "BLOCKED"]
    passed = [r for r in results if r[2] == "PASS"]
    print(f"  PASS {len(passed)} · FAIL {len(fails)} · BLOCKED {len(blocked)}")
    for k, t, s, why, _ in blocked:
        print(f"    ! {t}: {why} — **لا يُحسب نجاحًا**")
    for k, t, s, why, _ in fails:
        print(f"    ✗ {t}")
    print("═" * 62)
    print("QUALITY_GATE = " + ("FAIL" if fails else "PASS"))
    if blocked:
        print("ملاحظة: بواباتٌ محجوبة لم تُشغَّل — النتيجة أعلاه لا تشملها.")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
