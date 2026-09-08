#!/usr/bin/env python3
"""حدودُ الأصل — CORS والتمهيد والكعكة وحارسُ CSRF للعملاء الأصليّين.

    python3 cors_test.py

لماذا ملفٌّ مستقلّ؟ لأن هذا العطبَ لم يُكتشف إلا بتدقيقٍ يدويّ، وسببُ
خفائه أن **القشرةَ لم تُبنَ قطّ** — فلا اختبارٌ كان يمرّ من هنا. وأشدُّ ما
فيه أنه ينكسر من أربع جهاتٍ مستقلّة، فإصلاحُ واحدةٍ لا يُظهر الثلاث.

القاعدةُ التي تحرسها هذه الاختبارات:

    أصلٌ معلَن  ⇒ CORS + تمهيدٌ مُجاب + SameSite=None (بشرط Secure)
    أصلٌ آخر    ⇒ لا ترويسةَ CORS · تمهيدٌ مرفوض · CSRF مرفوض
    بلا أصل     ⇒ يمرّ (Flutter على الهاتف ليس متصفّحًا)

ولا يُنادى الخادمُ عبر الشبكة هنا: تُعاد قراءةُ الوحدة بعد ضبط البيئة،
فتُفحص القرارات نفسُها لا آثارُها.
"""
import importlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

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

APP_ORIGIN = "https://app.falah.example"
SHELL      = "capacitor://localhost"
EVIL       = "https://evil.example"

class Headers(dict):
    """أبسطُ ما يكفي: `get` بحساسيّةٍ للحالة كما في http.client."""
    def get(self, k, d=None):
        for kk, vv in self.items():
            if kk.lower() == k.lower(): return vv
        return d

def load(**env):
    """يضبط البيئة ويعيد تحميل الإعداد والخادم، فيُقرأ الجديد."""
    for k in ("FALAH_APP_ORIGINS", "FALAH_ORIGIN", "FALAH_SECURE"):
        os.environ.pop(k, None)
    os.environ.update({k: v for k, v in env.items() if v is not None})
    import falah.settings as CFG
    importlib.reload(CFG)
    import app as APP
    importlib.reload(APP)
    return APP, CFG

class Fake:
    """مُعالِجٌ بلا شبكة: ترويساتٌ فقط، لأن القرارات كلَّها تُبنى عليها."""
    def __init__(self, APP, origin=None):
        self.__class__ = type("F", (APP.App,), {"__init__": lambda s: None})
        self.headers = Headers({"Origin": origin} if origin else {})

def fake(APP, origin=None):
    f = Fake.__new__(Fake); Fake.__init__(f, APP, origin); return f

# ═══════════ ١ · تحليلُ القائمة المعلَنة ═══════════

def parsing():
    head("تحليلُ FALAH_APP_ORIGINS")
    _, CFG = load(FALAH_APP_ORIGINS=f"{APP_ORIGIN}, {SHELL} ,")
    check("الأصلان يُقرآن ويُشذَّب الفراغ", CFG.APP_ORIGINS == {APP_ORIGIN, SHELL},
          str(sorted(CFG.APP_ORIGINS)))

    _, CFG = load(FALAH_APP_ORIGINS="*")
    check("`*` تُرفض ولا تدخل القائمة", CFG.APP_ORIGINS == frozenset(),
          str(sorted(CFG.APP_ORIGINS)))

    _, CFG = load(FALAH_APP_ORIGINS="http://insecure.example")
    check("أصلٌ غيرُ مشفّرٍ وغيرِ محلّيٍّ يُهمَل", CFG.APP_ORIGINS == frozenset(),
          str(sorted(CFG.APP_ORIGINS)))

    _, CFG = load(FALAH_APP_ORIGINS="http://localhost:3000")
    check("localhost يُقبل للتطوير", CFG.APP_ORIGINS == {"http://localhost:3000"})

    _, CFG = load(FALAH_APP_ORIGINS=f"{APP_ORIGIN}/")
    check("الشرطةُ الأخيرة تُشذَّب", CFG.APP_ORIGINS == {APP_ORIGIN})

    _, CFG = load()
    check("بلا إعلانٍ: القائمةُ فارغة (السلوكُ الأصليّ)", CFG.APP_ORIGINS == frozenset())

# ═══════════ ٢ · مطابقةُ الأصل ═══════════

def matching():
    head("مطابقةُ الأصل — حرفيّةٌ لا نمطيّة")
    APP, _ = load(FALAH_APP_ORIGINS=f"{APP_ORIGIN},{SHELL}")

    check("الأصلُ المعلَن يُقبل", fake(APP, APP_ORIGIN).app_origin() == APP_ORIGIN)
    check("مخطَّطُ القشرة يُقبل", fake(APP, SHELL).app_origin() == SHELL)
    check("أصلٌ غريبٌ يُرفض", fake(APP, EVIL).app_origin() is None)
    check("بلا أصل: None", fake(APP).app_origin() is None)

    # النطاقُ الفرعيّ ليس النطاق. ولا البادئةُ تكفي.
    check("نطاقٌ فرعيٌّ غيرُ معلَنٍ يُرفض",
          fake(APP, "https://evil.app.falah.example").app_origin() is None)
    check("أصلٌ يبدأ بالمعلَن ولا يساويه يُرفض",
          fake(APP, APP_ORIGIN + ".evil.com").app_origin() is None)

# ═══════════ ٣ · الكعكة ═══════════

def cookie():
    head("SameSite — None للمعلَن بشرط Secure، وStrict لما عداه")
    APP, _ = load(FALAH_APP_ORIGINS=APP_ORIGIN, FALAH_SECURE="1")

    ck = APP.App.set_cookie(fake(APP, APP_ORIGIN), "TOK")[0][1]
    check("أصلٌ معلَن + Secure ⇒ SameSite=None", "SameSite=None" in ck, ck)
    check("ومعها Secure دائمًا", "; Secure" in ck, ck)
    check("وتبقى HttpOnly", "HttpOnly" in ck, ck)

    ck = APP.App.set_cookie(fake(APP, EVIL), "TOK")[0][1]
    check("أصلٌ غريب ⇒ يبقى Strict", "SameSite=Strict" in ck, ck)

    ck = APP.App.set_cookie(fake(APP), "TOK")[0][1]
    check("بلا أصل (عميلٌ أصليّ) ⇒ Strict", "SameSite=Strict" in ck, ck)

    # القاعدةُ التي تمنع كعكةً لا تُحفظ: None بلا Secure ترفضها المتصفّحات
    APP, _ = load(FALAH_APP_ORIGINS=APP_ORIGIN)          # لا FALAH_SECURE
    ck = APP.App.set_cookie(fake(APP, APP_ORIGIN), "TOK")[0][1]
    check("بلا Secure ⇒ لا None بحالٍ (فشلٌ مغلق)", "SameSite=Strict" in ck, ck)
    check("ولا تخرج Secure كذبًا", "; Secure" not in ck, ck)

    ck = APP.App.clear_cookie(fake(APP, APP_ORIGIN))[0][1]
    check("المحوُ يتبع القاعدةَ نفسها", "SameSite=Strict" in ck and "Max-Age=0" in ck, ck)

    # النداءُ بلا مُعالِجٍ حقيقيّ يبقى ممكنًا — اختبارٌ قائمٌ يعتمد عليه
    ck = APP.App.set_cookie(None, "TOK")[0][1]
    check("النداءُ بلا self لا ينكسر", "SameSite=Strict" in ck, ck)

# ═══════════ ٤ · حارسُ CSRF ═══════════

def csrf():
    head("حارسُ CSRF — يقبل النطاقَ والأصولَ المعلَنة وحدها")
    APP, _ = load(FALAH_ORIGIN=APP_ORIGIN, FALAH_APP_ORIGINS=SHELL)

    def guard(origin=None, hdr="1"):
        f = fake(APP, origin)
        if hdr is not None: f.headers["X-FALAH"] = hdr
        return APP.App.guard_csrf(f)

    check("نطاقُ الإنتاج يمرّ", guard(APP_ORIGIN) is True)
    check("الأصلُ المعلَن يمرّ", guard(SHELL) is True)
    check("أصلٌ غريبٌ يُرفض", guard(EVIL) is False)
    check("بلا أصل يمرّ — Flutter على الهاتف", guard(None) is True)
    check("بلا ترويسة X-FALAH يُرفض ولو من النطاق", guard(APP_ORIGIN, hdr=None) is False)
    check("بترويسةٍ خاطئة يُرفض", guard(APP_ORIGIN, hdr="0") is False)

    # أصلٌ معلَنٌ بلا الترويسة: المنعُ يبقى — الطبقتان معًا لا إحداهما
    check("أصلٌ معلَنٌ بلا الترويسة يُرفض", guard(SHELL, hdr=None) is False)

# ═══════════ ٥ · لا CORS بلا إعلان ═══════════

def default_off():
    head("السلوكُ الافتراضيّ — لا CORS لمن لم يُعلن شيئًا")
    APP, CFG = load(FALAH_ORIGIN=APP_ORIGIN)
    check("القائمةُ فارغة", CFG.APP_ORIGINS == frozenset())
    check("أيُّ أصلٍ يُرفض", fake(APP, APP_ORIGIN).app_origin() is None)
    ck = APP.App.set_cookie(fake(APP, APP_ORIGIN), "TOK")[0][1]
    check("والكعكةُ تبقى Strict كما كانت", "SameSite=Strict" in ck, ck)

# ═══════════ ٦ · ترويساتُ CORS ═══════════

def headers():
    head("ترويساتُ CORS — الأصلُ حرفيًّا، ولا `*` أبدًا")
    APP, _ = load(FALAH_APP_ORIGINS=APP_ORIGIN)
    h = dict(APP.App._cors(fake(APP, APP_ORIGIN), APP_ORIGIN))

    check("Allow-Origin بالأصل حرفيًّا", h.get("Access-Control-Allow-Origin") == APP_ORIGIN)
    check("ولا يساوي `*` بحال", h.get("Access-Control-Allow-Origin") != "*")
    check("Allow-Credentials: true", h.get("Access-Control-Allow-Credentials") == "true")
    check("Vary: Origin — فلا يُخزَّن ردٌّ لأصلٍ ويُقدَّم لآخر",
          h.get("Vary") == "Origin")

# ═══════════ التشغيل ═══════════

def run():
    print("═" * 46)
    print("  حدودُ الأصل — CORS · التمهيد · الكعكة · CSRF")
    print("═" * 46)
    parsing(); matching(); cookie(); csrf(); default_off(); headers()

    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: سقط {FAIL} من {OK + FAIL}")
        for n, d in FAILURES: print(f"  ✗ {n}" + (f"  ← {d}" if d else ""))
        return 1
    print(f"النتيجة: {OK} فحصًا · كلّها نجحت ✓")
    return 0

if __name__ == "__main__":
    sys.exit(run())
