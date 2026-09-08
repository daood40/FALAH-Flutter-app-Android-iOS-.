"""إعدادُ الخادم المقروء من البيئة — موضعٌ واحدٌ يُقرأ منه.

`refresh()` يُنادى عند تحميل `app.py`، فإعادةُ تحميل الوحدة في الاختبار
تعيد قراءةَ البيئة كما كانت تفعل حين كانت هذه الأسماء في `app.py` نفسه.
لا شيءَ هنا يُخمَّن: كلُّ قيمةٍ لها متغيّرٌ ومعناه مكتوبٌ في `.env.example`.
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB   = os.path.join(HERE, "falah.db")                # قاعدة المحتوى
UI   = os.path.join(HERE, "falah-app.html")          # مساحة العمل
DEMO = os.path.join(HERE, "falah-agent.html")        # النموذج التفاعلي (بلا حساب)
COOKIE = "falah_sid"

SECURE = ORIGIN = INVITE = None
TRUST_PROXY = False
MAX_BODY = 1_000_000
APP_ORIGINS: frozenset = frozenset()

# أصولُ العملاء الأصليّين المسموح بها. القاعدة: **قائمةٌ معلَنة، لا `*`
# أبدًا** — لأن `Access-Control-Allow-Origin: *` مع `credentials` مرفوضٌ
# في المتصفّحات أصلًا، ومن يحاول الالتفاف عليه بعكس الأصل الوارد كما جاء
# يكون قد فتح الباب لكل موقع. هنا يُطابَق الأصلُ حرفيًّا أو يُرفض.
#
# ومن لا يعلن شيئًا لا يحصل على CORS إطلاقًا: السلوك الافتراضيّ هو ما
# كان — أصلٌ واحدٌ يخدم الواجهة والـAPI معًا.
#
# ملاحظةٌ تُغني عن عملٍ كثير: **Flutter على الهاتف ليس متصفّحًا.** لا
# CORS فيه ولا SameSite — فلا يحتاج شيئًا ممّا هنا. هذا للويب وللقشرة
# داخل WebView وحدهما.
_LOCAL = ("http://localhost", "http://127.0.0.1")

def _origins(raw):
    out = set()
    for o in (raw or "").split(","):
        o = o.strip().rstrip("/")
        if not o or o == "*":                       # `*` ليست قيمةً مقبولة
            continue
        # مشفَّرٌ أو مخطَّطُ قشرةٍ أصليّة أو محلّيٌّ للتطوير — وما عداه يُهمَل
        if o.startswith(("https://", "capacitor://", "ionic://")) or o.startswith(_LOCAL):
            out.add(o)
    return frozenset(out)

def refresh():
    """يعيد قراءةَ البيئة. يُنادى عند الاستيراد وعند إعادة التحميل."""
    global SECURE, ORIGIN, INVITE, TRUST_PROXY, MAX_BODY, APP_ORIGINS
    SECURE = os.environ.get("FALAH_SECURE") == "1"     # خلف HTTPS: كعكةٌ لا تسافر إلا مشفّرة
    ORIGIN = os.environ.get("FALAH_ORIGIN", "").rstrip("/")    # نطاق الإنتاج، إن حُدِّد
    INVITE = os.environ.get("FALAH_INVITE", "").strip()        # إطلاقٌ مغلق: لا حساب إلا برمز دعوة
    # لا `FALAH_ADMIN_KEY`: أُلغي في P1.2. الإدارةُ بدورٍ على حسابٍ حقيقيّ.
    # لا تُقرأ X-Forwarded-For إلا بإعلانٍ صريح — انظر `App.client_ip`
    TRUST_PROXY = os.environ.get("FALAH_TRUST_PROXY") == "1"
    MAX_BODY = int(os.environ.get("FALAH_MAX_BODY", 1_000_000))
    APP_ORIGINS = _origins(os.environ.get("FALAH_APP_ORIGINS"))

refresh()
