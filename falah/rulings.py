"""أحكام المراجعين — قرارُ عالِمٍ مسمًّى في نصٍّ محجوب.

المحجوب لتعارض الأحكام أو لانعدامها لا يُفكّ حجبه بخوارزمية. يُفكّ بقرار
إنسانٍ يوقّع باسمه، ويُسجَّل قراره في `rulings.json` فيُطبَّق عند البناء.

وثلاثة قيود تحكم القرار:
  ١) **يُربط ببصمة النصّ** لا برقمه. فإن تغيّر حرفٌ في النصّ لاحقًا سقط
     الحكم عنه ولم يُطبَّق — كما تسقط بصمةُ المشروع عند انحراف مصدره.
  ٢) **لا إفراج بلا حكمٍ ومستند واسم مراجع** — نفس قاعدة القاعدة كلّها.
  ٣) **لا يرفع إلا الحجب الحُكمي**. أما الحجب الآليّ (متنٌ مقطوع، نصٌّ لم
     يتأكّد من مصدر ثانٍ، مدخلٌ يجمع حديثين) فلا يرفعه توقيعٌ، لأن علّته
     في سلامة النصّ لا في الحكم عليه.
"""
import json, os, re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.environ.get("FALAH_RULINGS", os.path.join(HERE, "rulings.json"))

FP_RE   = re.compile(r"^[0-9a-f]{32}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DECISIONS = ("release", "block")

# الحجب الحُكمي وحده هو ما يقبل قرار المراجع
GRADE_BLOCKS = ("تعارض", "لا حكم", "الحكم", "درجة")

def problem(r):
    """يعيد سبب رفض القرار، أو None إن كان سليمًا."""
    if not isinstance(r, dict):                 return "القرار ليس كائنًا"
    if not FP_RE.match(str(r.get("fp", ""))):   return "بصمة النصّ ناقصة أو غير صحيحة"
    if r.get("decision") not in DECISIONS:      return "القرار غير معروف"
    if not (r.get("reviewer") or "").strip():   return "لا اسم للمراجع"
    if not DATE_RE.match(str(r.get("date", ""))): return "لا تاريخ للقرار (YYYY-MM-DD)"
    if r["decision"] == "release":
        if not (r.get("grade") or "").strip():  return "إفراجٌ بلا حكم"
        if not (r.get("basis") or "").strip():  return "حكمٌ بلا مستند"
    return None

def load(path=None):
    """يعيد (القرارات السليمة مفهرسةً بالبصمة، المرفوضة ومعها أسبابها)."""
    p = path or PATH
    if not os.path.exists(p): return {}, []
    data = json.load(open(p, encoding="utf-8"))
    items = data.get("rulings", data) if isinstance(data, dict) else data
    good, bad = {}, []
    for r in items:
        why = problem(r)
        if why: bad.append((r, why)); continue
        good[r["fp"]] = r
    return good, bad

def applies_to(ruling, block_reason):
    """هل يرفع هذا القرار هذا الحجب؟ الحجب الآليّ لا يُرفع بتوقيع."""
    if ruling["decision"] != "release": return False
    return (block_reason or "").startswith(GRADE_BLOCKS)

def basis_line(r):
    return f"{r['basis']} — بمراجعة {r['reviewer']} ({r['date']})"

def template(fp, ref, matn, reason):
    """قالبُ قرارٍ فارغ يُملأ يدويًّا — يُصدَّر مع حزمة المراجعة."""
    return {"fp": fp, "ref": ref, "matn": (matn or "")[:120],
            "blocked_because": reason, "decision": "", "grade": "",
            "basis": "", "reviewer": "", "date": "", "note": ""}
