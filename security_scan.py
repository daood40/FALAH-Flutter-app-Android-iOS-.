#!/usr/bin/env python3
"""فحصٌ أمنيّ يسبق كل دفعة — أسرارٌ وإعدادٌ وصلاحيات.

    python3 security_scan.py           # يفحص ما يتتبّعه git (أو الشجرة كلّها)
    python3 security_scan.py --all     # الشجرة كلّها بما لا يتتبّعه git

يخرج بحالة ١ إن وُجد `critical` أو `high` — فيسقط خطّ التكامل. القاعدة
المكتوبة في `launch/CREDENTIALS.md`: المفتاح في ملفّ بيئةٍ بصلاحية ٦٠٠
خارج شجرة المصدر، لا في الشيفرة ولا في `docker-compose` ولا في الواجهة.

ما لا يفعله هذا الملفّ: لا يفحص ثغرات الاعتماديات (يلزمه `pip-audit` وهو
غير مثبَّت هنا) — والنقص مذكورٌ صراحةً في المخرجات لا مسكوتٌ عنه.
"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# نمطٌ، وصفٌ، خطورة. الأنماط تصف *شكل* السرّ لا اسمه، فلا تفوتها التسمية.
PATTERNS = [
    (r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----",
     "مفتاحٌ خاصّ مكتوبٌ في ملفّ", "critical"),
    (r"\bAIza[0-9A-Za-z_\-]{35}\b",           "مفتاح Google API", "critical"),
    (r"\bsk_live_[0-9A-Za-z]{16,}",           "مفتاح Stripe حيّ", "critical"),
    (r"\bghp_[0-9A-Za-z]{36}\b",              "رمز GitHub", "critical"),
    (r"\bxox[baprs]-[0-9A-Za-z\-]{10,}",      "رمز Slack", "critical"),
    (r"\bAKIA[0-9A-Z]{16}\b",                 "مفتاح AWS", "critical"),
    (r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}",
     "رمز JWT موقَّع", "high"),
    (r"(?i)\b(password|passwd|secret|api[_-]?key|token|private[_-]?key)\s*[:=]\s*"
     r"['\"][^'\"\s${}]{12,}['\"]", "سرٌّ مكتوبٌ في الشيفرة", "high"),
]

# استثناءاتٌ مبرَّرة: اختباراتٌ تُثبت غياب السرّ، وكلماتُ مرورٍ اختباريةٌ
# ظاهرةٌ في المحرّك نفسه، وأمثلةٌ في ملفّات البيئة النموذجية.
ALLOW = [
    (r"tests\.py$",       "اختبارٌ يتحقّق من غياب السرّ أو يستعمل كلمةً اختبارية"),
    (r"audit\.py$",       "فحصٌ يستعمل حسابًا اختباريًّا"),
    (r"ui_audit\.py$",    "فحص واجهةٍ يستعمل حسابًا اختباريًّا"),
    (r"\.env\.example$",  "قالبٌ بلا قيمٍ حقيقية"),
    (r"security_scan\.py$", "هذا الملفّ نفسه — أنماط الكشف"),
    (r"launch/CREDENTIALS\.md$", "سياسةُ المفاتيح، لا مفاتيح"),
]

SKIP_DIRS = {".git", "__pycache__", "node_modules", "raw", "templates",
             "exports", "out", "backups", "review", "review_sample",
             ".ruff_cache", ".mypy_cache", "fonts", "icons"}
SKIP_EXT  = {".png", ".jpg", ".jpeg", ".mp4", ".zip", ".ttf", ".woff2",
             ".db", ".b64", ".pyc", ".gz"}

def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=HERE, capture_output=True,
                             text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return [f for f in out.stdout.splitlines() if f]
    except Exception:
        pass
    return None

def walk_files():
    got = []
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            p = os.path.relpath(os.path.join(root, f), HERE)
            if os.path.splitext(f)[1].lower() not in SKIP_EXT:
                got.append(p)
    return got

def allowed(path):
    for pat, why in ALLOW:
        if re.search(pat, path): return why
    return None

# قيمةٌ لا تكون سرًّا مهما كان اسم متغيّرها: رابطٌ أو مسارٌ أو اسمُ نطاق أو
# مرجعُ متغيّر بيئة. بلا هذا يبلّغ الفاحصُ عن `TOKEN = "https://…/token"`.
NOT_SECRET = re.compile(
    r"^(https?://|/|\./|\$|\{|<|[A-Z_]+$|[a-z0-9.-]+\.[a-z]{2,}$)|"
    r"^[a-z_.\-/]+$", re.I)

def looks_secret(value):
    v = value.strip().strip("'\"")
    if NOT_SECRET.match(v): return False
    kinds = sum(bool(re.search(p, v)) for p in (r"[a-z]", r"[A-Z]", r"\d"))
    return kinds >= 2 and len(v) >= 12

def scan_secrets(files):
    found = []
    for rel in files:
        if os.path.splitext(rel)[1].lower() in SKIP_EXT: continue
        full = os.path.join(HERE, rel)
        if not os.path.isfile(full) or os.path.getsize(full) > 3_000_000: continue
        try:    text = open(full, encoding="utf-8", errors="ignore").read()
        except Exception: continue
        why = allowed(rel)
        for pat, desc, sev in PATTERNS:
            for m in re.finditer(pat, text):
                # نمط «سرٌّ في الشيفرة» وحده يحمل مجموعةَ قيمة يُفحص شكلها
                if desc == "سرٌّ مكتوبٌ في الشيفرة":
                    val = m.group(0).split("=", 1)[-1].split(":", 1)[-1]
                    if not looks_secret(val): continue
                line = text[:m.start()].count("\n") + 1
                found.append({"file": rel, "line": line, "what": desc,
                              "severity": "info" if why else sev,
                              "note": why or ""})
    return found

def scan_config(files):
    """إعدادٌ خاطئٌ يفتح البابَ ولو لم يُسرَّب مفتاح."""
    out = []
    def add(sev, what, where, note=""):
        out.append({"file": where, "line": 0, "what": what,
                    "severity": sev, "note": note})

    # ١ · أسرارٌ في docker-compose بصيغة environment: (تظهر في `docker inspect`)
    dc = os.path.join(HERE, "deploy", "docker-compose.yml")
    if os.path.isfile(dc):
        t = open(dc, encoding="utf-8").read()
        for m in re.finditer(r"^\s+([A-Z_]*(?:KEY|SECRET|PASSWORD|TOKEN))\s*:\s*"
                             r"[\"']?(?!\$\{)([^\"'\s#][^\n]*)", t, re.M):
            add("high", f"سرٌّ مكتوبٌ في compose: {m.group(1)}", "deploy/docker-compose.yml",
                "يجب أن يأتي من env_file أو ${...}")

    # ٢ · الكعكة والنطاق في الإنتاج
    if os.path.isfile(dc):
        t = open(dc, encoding="utf-8").read()
        if "FALAH_SECURE" not in t:
            add("high", "النشر بلا FALAH_SECURE — كعكةٌ تسافر بلا تشفير",
                "deploy/docker-compose.yml")
        if "FALAH_ORIGIN" not in t:
            add("high", "النشر بلا FALAH_ORIGIN — لا حارسَ لمصدر الطلب",
                "deploy/docker-compose.yml")

    # ٣ · مفتاحٌ خاصّ في الشجرة ولو لم يتتبّعه git
    for root, dirs, fs in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fs:
            if f.endswith((".p8", ".pem", ".key", ".p12", ".pfx")):
                rel = os.path.relpath(os.path.join(root, f), HERE)
                tracked = tracked_files() or []
                add("critical" if rel in tracked else "medium",
                    "ملفّ مفتاحٍ في الشجرة", rel,
                    "متتبَّعٌ في git!" if rel in tracked else "غير متتبَّع — احذفه أو انقله خارجها")

    # ٤ · صلاحيات ملفّات البيئة
    for f in os.listdir(HERE):
        if f == ".env" or f.startswith(".env."):
            if f == ".env.example": continue
            mode = oct(os.stat(os.path.join(HERE, f)).st_mode)[-3:]
            if mode != "600":
                add("high", f"ملفّ بيئةٍ بصلاحية {mode} لا ٦٠٠", f)

    # ٥ · مسارات كتابةٍ بلا حارس CSRF
    ap = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    if "guard_csrf" not in ap.split("def do_POST")[1][:400]:
        add("critical", "do_POST بلا حارس CSRF", "app.py")

    # ٦ · إعدادٌ ضعيفٌ افتراضيًّا
    if 'os.environ.get("FALAH_ADMIN_KEY", "")' in ap and 'if not ADMIN_KEY' not in ap:
        add("high", "مفتاح الإدارة قد يكون فارغًا بلا حراسة", "app.py")

    return out

def main():
    files = (walk_files() if "--all" in sys.argv else (tracked_files() or walk_files()))
    issues = scan_secrets(files) + scan_config(files)
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    issues.sort(key=lambda x: order.get(x["severity"], 9))

    counts = {s: sum(1 for i in issues if i["severity"] == s) for s in order}
    print(f"▸ فحصٌ أمنيّ — {len(files)} ملفًّا")
    for i in issues:
        mark = {"critical": "✗", "high": "✗", "medium": "!", "low": "!", "info": "·"}[i["severity"]]
        loc = f"{i['file']}:{i['line']}" if i["line"] else i["file"]
        print(f"  {mark} [{i['severity']:<8}] {loc}  {i['what']}"
              + (f"  — {i['note']}" if i["note"] else ""))
    if not issues: print("  ✓ لا شيء")

    print("\n  ملاحظةٌ صريحة: هذا الفحص لا يشمل ثغرات الاعتماديات "
          "(يلزمه pip-audit وهو غير مثبَّتٍ في هذه البيئة).")
    bad = counts["critical"] + counts["high"]
    print(f"\nالنتيجة: critical={counts['critical']} · high={counts['high']} · "
          f"medium={counts['medium']} · info={counts['info']}")
    if bad:
        print("QUALITY_GATE = FAIL — لا يُدفع شيءٌ وفيه critical أو high")
        return 1
    print("QUALITY_GATE = PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
