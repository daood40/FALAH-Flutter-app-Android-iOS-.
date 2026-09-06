#!/usr/bin/env python3
"""تحقُّقُ الصورة من نفسها — يجري داخل الحاوية وقتَ البناء.

    python3 verify_image.py

**وهو غيرُ `tests.py`، والفرقُ في الموضوع لا في الحجم:** `tests.py` يفحص
**المستودع** — يقرأ `Dockerfile` و`ci.yml` و`.gitignore` و`deploy/` —
فمكانُه خطُّ التكامل. وهذا يفحص **ما بُني في هذه الصورة**: هل خرجت قاعدةُ
محتوًى سليمةٌ غيرُ فارغة، وهل يقلع الخادمُ عليها ويُعلن جاهزيّته.

وسببُ وجوده أنّ `RUN python3 tests.py` كان في الـDockerfile، فألزم صورةَ
الإنتاج أن تحمل سقالةَ المستودع كلَّها لتفحص نفسها بها — ثم أسقط البناءَ
لأنّ الصورة، بحقٍّ، لا تحمل `Dockerfile`.

والقاعدةُ التي يحرسها: **لا تخرج صورةٌ بقاعدةٍ فارغةٍ أو لا تقلع.** فالعطبُ
هنا لا يظهر إلا حين يفتح مستخدمٌ التطبيقَ ولا يجد آية.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

# أدنى ما لا يُقبل دونه. ليست أرقامًا تقريبيّة: المصحف ٦٢٣٦ آيةً و١١٤
# سورة. وقاعدةٌ بأقلَّ من ذلك ناقصةٌ لا مضغوطة.
MIN_AYAT = 6236
MIN_SURAHS = 114
MIN_HADITHS = 1

OK = FAIL = 0


def check(name, cond, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f"  ← {detail}" if detail else ""))


def content_db():
    print("▸ قاعدة المحتوى")
    if not os.path.exists("falah.db"):
        check("القاعدة موجودة", False, "falah.db مفقودة — لم يُنتج build.py شيئًا")
        return
    c = sqlite3.connect("falah.db")
    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    check("سليمةٌ بنيويًّا", integrity == "ok", integrity)

    for table, floor in (("ayat", MIN_AYAT), ("surahs", MIN_SURAHS),
                         ("hadiths", MIN_HADITHS)):
        try:
            n = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
        except sqlite3.Error as e:
            check(f"جدول {table}", False, str(e))
            continue
        check(f"{table}: {n} صفًّا (الحدُّ الأدنى {floor})", n >= floor, str(n))

    # البحثُ ميزةٌ أساسية، وفهرسُه يُبنى منفصلًا عن الجداول: قد تمتلئ
    # الجداولُ ويبقى الفهرسُ فارغًا فلا يجد المستخدمُ شيئًا.
    try:
        n = c.execute("SELECT COUNT(*) FROM ayat_fts").fetchone()[0]
        check(f"فهرسُ البحث مبنيّ ({n})", n >= MIN_AYAT, str(n))
    except sqlite3.Error as e:
        check("فهرسُ البحث مبنيّ", False, str(e))

    # ولا مصدرَ بلا إسناد — وهو شرطُ المشروع الأوّل
    try:
        n = c.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        check(f"المصادرُ موثَّقة ({n})", n >= 1, str(n))
    except sqlite3.Error as e:
        check("المصادرُ موثَّقة", False, str(e))
    c.close()


def boots():
    print("\n▸ الخادم يقلع على ما بُني")
    # مجلّدٌ مؤقّتٌ بصلاحيّاتٍ ضيّقةٍ واسمٍ غيرِ متوقَّع — لا مسارٌ ثابتٌ في
    # `/tmp`: ذاك يُسبَق إليه برابطٍ رمزيٍّ فيُكتب حيث لم نقصد.
    tmp = tempfile.mkdtemp(prefix="falah_verify_")
    env = {**os.environ, "FALAH_APP_DB": os.path.join(tmp, "boot.db"),
           "FALAH_INLINE_WORKER": "0", "PORT": "8081"}
    p = subprocess.Popen([sys.executable, "app.py"], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        body = None
        for _ in range(60):
            if p.poll() is not None:
                out = (p.stdout.read() or b"").decode(errors="replace")[-800:]
                check("العملية باقية", False, out)
                return
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:8081/healthz", timeout=2) as r:
                    body = r.read().decode()
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(1)
        check("يستجيب /healthz", body is not None and '"live": true' in body,
              str(body)[:200])

        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:8081/readyz", timeout=5) as r:
                ready = r.read().decode()
        except urllib.error.HTTPError as e:
            ready = e.read().decode()
        # الجاهزيّةُ تشمل قاعدةَ المحتوى: فحصٌ من الخادم نفسِه لا منّا
        check("ويُعلن جاهزيّته", '"ready": true' in ready, ready[:300])
        check("وقاعدةُ المحتوى مرئيّةٌ له", '"content_db": true' in ready,
              ready[:300])
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("═" * 46)
    print("  تحقُّقُ الصورة من نفسها")
    print("═" * 46)
    content_db()
    boots()
    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: سقط {FAIL} من {OK + FAIL} — **لا تُختم هذه الصورة**")
        return 1
    print(f"النتيجة: {OK} فحصًا · كلّها نجحت ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
