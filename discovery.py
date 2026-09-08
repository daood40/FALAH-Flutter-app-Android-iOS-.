#!/usr/bin/env python3
"""جردٌ مقيسٌ للمشروع — يُقرأ من الشفرة والقاعدة، لا من الذاكرة ولا من الوصف.

    python3 discovery.py            # جرد كامل
    python3 discovery.py --json     # للاستهلاك الآلي

كل رقمٍ هنا محسوبٌ الآن. وما لا يُقاس يُكتب «غير مقيس» ولا يُدَّعى.
"""
import ast, json, os, re, subprocess, sys, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = {"__pycache__", "raw", "node_modules", ".git", "exports", "out",
        "templates", "review", "review_sample", "backups", "icons", "fonts"}

def walk(exts=(".py", ".html", ".js", ".yml", ".yaml", ".md", ".json")):
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if f.endswith(exts):
                yield os.path.join(root, f)

def rel(p): return os.path.relpath(p, HERE)

# ═════════════ ١ · الشفرة ═════════════
def code_inventory():
    rows, tot = [], {"files": 0, "lines": 0, "py": 0, "html": 0}
    for p in walk():
        try: n = sum(1 for _ in open(p, encoding="utf-8", errors="ignore"))
        except Exception: continue
        r = rel(p)
        if r.startswith(("mobile/www", "falah-preview.html")): continue
        rows.append((r, n))
        tot["files"] += 1; tot["lines"] += n
        if p.endswith(".py"):   tot["py"] += n
        if p.endswith(".html"): tot["html"] += n
    rows.sort(key=lambda x: -x[1])
    return rows, tot

def py_structure():
    """دوالُّ كل وحدة وأطولها — كاشفُ الملفات المتضخّمة والدوال المعقّدة."""
    out = []
    for p in walk((".py",)):
        try: tree = ast.parse(open(p, encoding="utf-8").read())
        except Exception: continue
        fns, cls, longest = 0, 0, (None, 0)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fns += 1
                span = (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno
                if span > longest[1]: longest = (node.name, span)
            elif isinstance(node, ast.ClassDef): cls += 1
        out.append({"file": rel(p), "functions": fns, "classes": cls,
                    "longest_fn": longest[0], "longest_len": longest[1]})
    return sorted(out, key=lambda x: -x["longest_len"])

def dependencies():
    """كل ما يُستورد من خارج المكتبة القياسية — الاعتماديات الحقيقية لا المعلنة."""
    std = set(sys.stdlib_module_names)
    local = {os.path.splitext(os.path.basename(p))[0] for p in walk((".py",))}
    local |= {"falah", "api", "render", "carousel", "video", "app", "store"}
    ext = {}
    for p in walk((".py",)):
        try: tree = ast.parse(open(p, encoding="utf-8").read())
        except Exception: continue
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):   mods = [a.name.split(".")[0] for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                mods = [n.module.split(".")[0]]
            for m in mods:
                if m and m not in std and m not in local:
                    ext.setdefault(m, set()).add(rel(p))
    return {k: sorted(v) for k, v in sorted(ext.items())}

# ═════════════ ٢ · المسارات ═════════════
def routes():
    found = {"content": [], "app_get": [], "app_post": []}
    for name, key in (("api.py", "content"), ("app.py", None)):
        try: src = open(os.path.join(HERE, name), encoding="utf-8").read()
        except FileNotFoundError: continue
        for m in re.finditer(r'p (?:==|\.startswith\()\s*"(/[^"]*)"', src):
            path = m.group(1)
            if name == "api.py": found["content"].append(path)
            else:
                seg = src[:m.start()]
                bucket = "app_post" if "def app_post" in seg.split("def app_get")[-1] \
                    and seg.rfind("def app_post") > seg.rfind("def app_get") else "app_get"
                found[bucket].append(path)
    return {k: sorted(set(v)) for k, v in found.items()}

def route_protection():
    """أيّ مسارٍ يكتب بلا حراسة؟ يُقرأ من ترتيب الشفرة لا من الادّعاء."""
    src = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    csrf = "if not self.guard_csrf():" in src and 'p.startswith("/app/")' in src
    post_body = src[src.index("def app_post"):] if "def app_post" in src else ""
    gate = post_body.find('if not u: return self.send_json({"error": "يلزم تسجيل الدخول"}')
    before, after = [], []
    for m in re.finditer(r'if p == "(/app/[^"]+)"', post_body):
        (before if m.start() < gate else after).append(m.group(1))
    return {"csrf_on_all_writes": csrf,
            "public_writes": before, "authenticated_writes": after,
            "admin_gated": sorted(set(re.findall(r'X-FALAH-ADMIN', src)))}

# ═════════════ ٣ · القاعدة ═════════════
def db_report(path, label):
    if not os.path.exists(path): return {"db": label, "exists": False}
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    tables = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    info = {}
    for t in tables:
        cols = list(c.execute(f"PRAGMA table_info({t})"))
        fks  = list(c.execute(f"PRAGMA foreign_key_list({t})"))
        idx  = [r[1] for r in c.execute(f"PRAGMA index_list({t})")]
        try: n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception: n = None
        info[t] = {"rows": n, "cols": len(cols), "pk": any(x[5] for x in cols),
                   "fks": len(fks), "indexes": len(idx),
                   "has_timestamp": any(x[1].endswith(("_at", "_time")) for x in cols),
                   "soft_delete": any(x[1] in ("deleted_at", "is_deleted") for x in cols)}
    c.close()
    return {"db": label, "exists": True, "size_mb": round(os.path.getsize(path)/1e6, 1),
            "tables": info,
            "no_pk": [t for t, v in info.items() if not v["pk"]],
            "no_index": [t for t, v in info.items() if v["indexes"] == 0],
            "no_timestamp": [t for t, v in info.items() if not v["has_timestamp"]],
            "no_soft_delete": [t for t, v in info.items() if not v["soft_delete"]]}

# ═════════════ ٤ · الأمان ═════════════
def security_scan():
    findings = []
    src_app = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    src_api = open(os.path.join(HERE, "api.py"), encoding="utf-8").read()

    # حقن SQL: أيّ استعلامٍ يُبنى بدمج نصّي
    risky = []
    for p in walk((".py",)):
        src = open(p, encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r'execute\(\s*f?"""?.{0,400}?"""?\s*%|execute\(\s*f"', src, re.S):
            line = src[:m.start()].count("\n") + 1
            risky.append(f"{rel(p)}:{line}")
    findings.append(("استعلامات مبنيّة بدمجٍ نصّي (تحتاج مراجعة)", risky))

    # أسرار في الشفرة
    secrets = []
    pat = re.compile(r"(BEGIN (EC |RSA )?PRIVATE KEY|\"private_key\"\s*:|sk_live_|AIza[0-9A-Za-z_-]{20})")
    for p in walk():
        if "CREDENTIALS" in p or "discovery" in p: continue
        t = open(p, encoding="utf-8", errors="ignore").read()
        if pat.search(t): secrets.append(rel(p))
    findings.append(("أسرارٌ مكتوبة في الشفرة", secrets))

    # حدّ المعدّل: أين يُطبَّق فعلًا؟
    throttled = re.findall(r'throttled\(c,\s*"([^"]+)', open(os.path.join(HERE, "falah", "auth.py"),
                                                            encoding="utf-8").read())
    findings.append(("مسارات عليها حدُّ معدّل", throttled))

    checks = {
        "كعكة HttpOnly": "HttpOnly" in src_app,
        "SameSite=Strict": "SameSite=Strict" in src_app,
        "Secure خلف HTTPS": "FALAH_SECURE" in src_app,
        "حماية CSRF بترويسة": "X-FALAH" in src_app,
        "التحقّق من Origin": "Origin" in src_app,
        "X-Content-Type-Options": "nosniff" in src_app,
        "X-Frame-Options": "X-Frame-Options" in src_app,
        "Referrer-Policy": "Referrer-Policy" in src_app,
        "Content-Security-Policy": "Content-Security-Policy" in src_app,
        "Strict-Transport-Security": "Strict-Transport-Security" in src_app,
        "حدُّ حجم الطلب": "1_000_000" in src_app or "Content-Length" in src_app,
        "كلمة المرور مشتقّة PBKDF2": "pbkdf2" in open(
            os.path.join(HERE, "falah", "auth.py"), encoding="utf-8").read().lower(),
        "رمز الجلسة مجزَّأ": "_hash_token" in open(
            os.path.join(HERE, "falah", "auth.py"), encoding="utf-8").read(),
        "لا يُسرَّب أثر التنفيذ": "خطأ داخلي" in src_api,
        "CORS مضبوط في طبقة التطبيق": "Access-Control-Allow-Origin" in src_app,
        "أدوار وصلاحيات (Roles)": bool(re.search(r"\brole\b", src_app)),
        "سجلّ تدقيق للعمليات الحسّاسة": "store.log" in src_app,
    }
    return {"checks": checks, "findings": dict(findings)}

# ═════════════ ٥ · الاختبارات والبناء ═════════════
def tests_and_build():
    out = {}
    for name, cmd in (("unit", [sys.executable, "tests.py"]),):
        try:
            r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=900)
            ok = "كل الاختبارات نجحت" in r.stdout
            out[name] = {"ran": True, "passed": ok,
                         "checks": r.stdout.count("✓"), "failed": r.stdout.count("✗")}
        except Exception as e:
            out[name] = {"ran": False, "error": type(e).__name__}
    out["suites_present"] = {f: os.path.exists(os.path.join(HERE, f))
                             for f in ("tests.py", "audit.py", "ui_audit.py")}
    out["ci"] = {"github_actions": os.path.isdir(os.path.join(HERE, ".github", "workflows")),
                 "gitlab_ci": os.path.exists(os.path.join(HERE, ".gitlab-ci.yml")),
                 "lint_config": any(os.path.exists(os.path.join(HERE, f))
                                    for f in ("ruff.toml", "setup.cfg", ".flake8", "pyproject.toml"))}
    return out

# ═════════════ ٦ · التشغيل ═════════════
def ops():
    dep = os.path.join(HERE, "deploy")
    return {
        "dockerfile": os.path.exists(os.path.join(HERE, "Dockerfile")),
        "compose": os.path.exists(os.path.join(dep, "docker-compose.yml")),
        "deploy_files": sorted(os.listdir(dep)) if os.path.isdir(dep) else [],
        "git_repo": os.path.isdir(os.path.join(HERE, ".git")),
        "gitignore": os.path.exists(os.path.join(HERE, ".gitignore")),
        "backup_script": any("backup" in f for f in os.listdir(HERE)),
        "background_jobs": any(os.path.exists(os.path.join(HERE, f))
                               for f in ("worker.py", "jobs.py", "queue.py")),
        "monitoring": any("monitor" in f or "metrics" in f for f in os.listdir(HERE)),
        "i18n": any(os.path.isdir(os.path.join(HERE, d)) for d in ("locales", "i18n")),
        "admin_ui": any("admin" in f for f in os.listdir(HERE)),
        "pwa": all(os.path.exists(os.path.join(HERE, f))
                   for f in ("manifest.webmanifest", "sw.js")),
        "mobile_shell": os.path.exists(os.path.join(HERE, "mobile", "capacitor.config.json")),
    }

def blocking_calls():
    """عملياتٌ ثقيلة تقع داخل دورة الطلب — أخطر ما يظهر تحت الحِمل."""
    src = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    hits = []
    for fn, why in (("VD.build", "تصيير فيديو داخل الطلب"),
                    ("CR.render_plan", "تصيير سلسلة صور داخل الطلب"),
                    ("R.render", "تصيير صورة داخل الطلب")):
        if fn in src: hits.append({"call": fn, "why": why})
    return hits

# ═════════════ التقرير ═════════════
def report():
    rows, tot = code_inventory()
    d = {
        "code": {"totals": tot, "largest": rows[:14]},
        "structure": py_structure()[:12],
        "dependencies": dependencies(),
        "routes": routes(),
        "protection": route_protection(),
        "db_content": db_report(os.path.join(HERE, "falah.db"), "falah.db (المحتوى)"),
        "db_app": db_report(os.path.join(HERE, "app.db"), "app.db (التطبيق)"),
        "security": security_scan(),
        "tests": tests_and_build(),
        "ops": ops(),
        "blocking": blocking_calls(),
    }
    return d

def human(d):
    P = print
    P("\n" + "═" * 62); P("  جرد مشروع فَلاح — مقيسٌ من الشفرة"); P("═" * 62)

    t = d["code"]["totals"]
    P(f"\n▸ الشفرة: {t['files']} ملفًا · {t['lines']:,} سطرًا "
      f"(بايثون {t['py']:,} · واجهات {t['html']:,})")
    for f, n in d["code"]["largest"][:8]: P(f"    {n:>6,}  {f}")

    P("\n▸ أطول الدوال (مؤشّر تعقيد)")
    for s in d["structure"][:6]:
        P(f"    {s['longest_len']:>4} سطرًا  {s['file']} :: {s['longest_fn']}")

    P("\n▸ الاعتماديات الخارجية")
    if not d["dependencies"]: P("    لا شيء — المكتبة القياسية وحدها ✓")
    for m, files in d["dependencies"].items():
        P(f"    {m:<14} ← {len(files)} ملفًا: {', '.join(files[:3])}")

    r = d["routes"]
    P(f"\n▸ المسارات: محتوى {len(r['content'])} · قراءة {len(r['app_get'])} · "
      f"كتابة {len(r['app_post'])}")
    pr = d["protection"]
    P(f"    CSRF على كل كتابة: {'✓' if pr['csrf_on_all_writes'] else '✗'}")
    P(f"    كتابةٌ بلا جلسة (مقصودة): {', '.join(pr['public_writes']) or 'لا شيء'}")
    P(f"    كتابةٌ بجلسة: {len(pr['authenticated_writes'])} مسارًا")

    for key in ("db_content", "db_app"):
        db = d[key]
        if not db.get("exists"): P(f"\n▸ {db['db']}: غير موجودة"); continue
        P(f"\n▸ {db['db']} — {db['size_mb']} م.ب · {len(db['tables'])} جدولًا")
        P(f"    بلا مفتاح أساسي: {', '.join(db['no_pk']) or 'لا شيء ✓'}")
        P(f"    بلا فهرس: {', '.join(db['no_index'][:6]) or 'لا شيء ✓'}")
        P(f"    بلا حذفٍ منطقي: {len(db['no_soft_delete'])} من {len(db['tables'])}")

    P("\n▸ الأمان")
    for k, v in d["security"]["checks"].items():
        P(f"    {'✓' if v else '✗'} {k}")
    for k, v in d["security"]["findings"].items():
        P(f"    · {k}: {len(v)}" + (f" — {v[:3]}" if v and len(str(v[:3])) < 110 else ""))

    tt = d["tests"]
    u = tt.get("unit", {})
    P(f"\n▸ الاختبارات: وحدة {u.get('checks','?')} بند "
      f"({'نجحت' if u.get('passed') else 'فيها سقوط'})")
    P(f"    الحزم: {', '.join(k for k,v in tt['suites_present'].items() if v)}")
    P(f"    CI/CD: {'✓' if any(tt['ci'].values()) else '✗ لا يوجد'}")

    o = d["ops"]
    P("\n▸ التشغيل")
    for k, v in o.items():
        if isinstance(v, bool): P(f"    {'✓' if v else '✗'} {k}")
    if d["blocking"]:
        P("\n▸ ⚠ عملياتٌ ثقيلة داخل دورة الطلب")
        for b in d["blocking"]: P(f"    ✗ {b['call']} — {b['why']}")
    P("")

if __name__ == "__main__":
    d = report()
    if "--json" in sys.argv:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        human(d)
        open(os.path.join(HERE, "discovery.json"), "w", encoding="utf-8").write(
            json.dumps(d, ensure_ascii=False, indent=1))
        print("الجرد الكامل في discovery.json")
