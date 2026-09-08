"""تطبيع أحكام المحدِّثين.

المبدأ: النص الأصلي للحكم يُحفظ كما ورد، ومعه اسم المحكِّم. التصنيف العربي
مجرّد ترجمة للتصنيف لا اجتهاد فيه، وما لم يُعرف تصنيفه لا يُطلق.
"""
FAMILY = {
    # صحيح
    "sahih": "صحيح", "sahih - agreed upon": "صحيح", "sahih muslim": "صحيح",
    "sahih - bukhari and muslim": "صحيح", "sahih bukhari": "صحيح",
    "sahih lighairihi": "صحيح لغيره", "isnaad sahih": "إسناده صحيح",
    "sahih - muslim": "صحيح", "sahih isnaad": "إسناده صحيح",
    # حسن
    "hasan": "حسن", "hasan sahih": "حسن صحيح", "hasan lighairihi": "حسن لغيره",
    "isnaad hasan": "إسناده حسن", "hasan isnaad": "إسناده حسن",
    # ضعيف وما دونه
    "daif": "ضعيف", "da'if": "ضعيف", "daif jiddan": "ضعيف جدًا",
    "isnaad daif": "إسناده ضعيف", "munkar": "منكر", "mawdu": "موضوع",
    "batil": "باطل", "shadh": "شاذ", "maqtu": "مقطوع", "mursal": "مرسل",
    "munqati": "منقطع", "matruk": "متروك",
}
RELEASABLE = {"صحيح", "حسن", "حسن صحيح", "صحيح لغيره", "حسن لغيره",
              "إسناده صحيح", "إسناده حسن"}

# ترتيب الترجيح عند تعدد المحكِّمين: الأشهر تداولًا أولًا
PREFERRED = ["Al-Albani", "Ahmad Muhammad Shakir", "Zubair Ali Zai",
             "Bashar Awad Maarouf", "Salim al-Hilali"]

def normalize(raw: str | None) -> str | None:   # يقبل الغائب ويردّ None
    return FAMILY.get((raw or "").strip().lower())

def pick(grades: list[dict]):
    """يختار حكمًا واحدًا للعرض مع اسم قائله، ويعيد كل الأحكام للسجل.
    يعيد None إذا لم يُفهم أي حكم — ولا يُخمَّن."""
    if not grades: return None
    known = [(g.get("name",""), g.get("grade",""), normalize(g.get("grade"))) for g in grades]
    known = [k for k in known if k[2]]
    if not known: return None
    for want in PREFERRED:
        for name, raw, ar in known:
            if name == want:
                return {"grade": ar, "raw": raw, "by": name,
                        "all": [{"by": n, "grade": r} for n, r, _ in known]}
    name, raw, ar = known[0]
    return {"grade": ar, "raw": raw, "by": name,
            "all": [{"by": n, "grade": r} for n, r, _ in known]}

def releasable(grade_ar: str | None) -> bool:
    return grade_ar in RELEASABLE
