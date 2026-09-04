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

SECURE = ORIGIN = INVITE = ADMIN_KEY = None
TRUST_PROXY = False
MAX_BODY = 1_000_000

def refresh():
    """يعيد قراءةَ البيئة. يُنادى عند الاستيراد وعند إعادة التحميل."""
    global SECURE, ORIGIN, INVITE, ADMIN_KEY, TRUST_PROXY, MAX_BODY
    SECURE = os.environ.get("FALAH_SECURE") == "1"     # خلف HTTPS: كعكةٌ لا تسافر إلا مشفّرة
    ORIGIN = os.environ.get("FALAH_ORIGIN", "").rstrip("/")    # نطاق الإنتاج، إن حُدِّد
    INVITE = os.environ.get("FALAH_INVITE", "").strip()        # إطلاقٌ مغلق: لا حساب إلا برمز دعوة
    ADMIN_KEY = os.environ.get("FALAH_ADMIN_KEY", "").strip()  # منح الاشتراك وإيصالات المتجر
    # لا تُقرأ X-Forwarded-For إلا بإعلانٍ صريح — انظر `App.client_ip`
    TRUST_PROXY = os.environ.get("FALAH_TRUST_PROXY") == "1"
    MAX_BODY = int(os.environ.get("FALAH_MAX_BODY", 1_000_000))

refresh()
