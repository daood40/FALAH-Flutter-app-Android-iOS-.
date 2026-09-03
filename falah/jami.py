"""«الجامع الكامل في الحديث الصحيح الشامل» — ضياء الرحمن الأعظمي.

النسخة المتاحة منه صورٌ ممسوحة نصُّها مستخرج آليًا (OCR)، وفيه تصحيف
لا يُؤمَن. فلا يصحّ أن يكون **مصدرًا للنص** — ويصحّ تمامًا أن يكون
**شاهدًا**: أن نسأله «هل أورد الأعظمي هذا الحديث؟» ونعرض جوابه بإسناده.

الطريقة: يُفهرس الكتاب كرباعيات كلمات مجرّدة من التشكيل. ثم يُؤخذ من كل
متنٍ مُحقَّقٍ عندنا ستُّ رباعيات، فإن وُجد اثنتان منها فأكثر عُدَّ الحديث
موجودًا في الكتاب. التصحيف يُتلف كلمةً أو كلمتين لا ستّ رباعيات، فالعتبة
تحتمل ضجيج المسح ولا تحتمل التشابه العابر.
"""
import glob, os, re
from .text import searchable

N, K, MIN_HITS = 4, 6, 2           # طول الرباعية · عدد العيّنات · عتبة القبول
WIN_AFTER, WIN_BEFORE = 70, 400    # نافذة قراءة الملحقات بعد المتن وقبله

GRADE_POS = {"صحيح", "حسن", "صح"}
GRADE_NEG = {"ضعيف", "منكر", "موضوع", "شاذ", "باطل", "متروك"}
TAKHRIJ_VERBS = {"اخرجه", "رواه", "واخرجه", "ورواه", "اخرجاه"}

class Jami:
    def __init__(self, folder):
        self.vols, self.disp, self.idx, self.heads, self.babs = {}, {}, {}, {}, {}
        for f in sorted(glob.glob(os.path.join(folder, "v*.txt"))):
            vol  = os.path.basename(f)[1:3]
            # نبني تيّارين متوازيين: مجرّدٌ للمطابقة، وأصليٌّ للعرض.
            # التطبيع يتمّ على كل كلمة وحدها فيبقى الترتيب واحدًا بينهما.
            ws, disp = [], []
            for tok in open(f, encoding="utf-8", errors="replace").read().split():
                n = searchable(tok)
                if not n: continue
                ws.append(n.split()[0]); disp.append(tok)
            self.vols[vol], self.disp[vol] = ws, disp
            self.idx[vol]  = {}
            for i in range(len(ws) - N + 1):
                self.idx[vol].setdefault(hash(tuple(ws[i:i+N])), i)
            # عناوين الكتب بمواضعها، لنسبة الحديث إلى كتابه عند الأعظمي
            # عناوين الكتب بمواضعها — مسحة واحدة على الكلمات، بلا إعادة تطبيع
            self.heads[vol], self.babs[vol] = [], []
            for i, w in enumerate(ws):
                if w == "كتاب" and i + 1 < len(ws) and len(ws[i+1]) >= 3:
                    name = "كتاب " + disp[i+1]
                    if not self.heads[vol] or self.heads[vol][-1][1] != name:
                        self.heads[vol].append((i, name))
                elif w == "باب" and i + 1 < len(ws):
                    name = "باب " + " ".join(disp[i+1:i+5])
                    if not self.babs[vol] or self.babs[vol][-1][1] != name:
                        self.babs[vol].append((i, name))

    @property
    def word_count(self):
        return sum(len(w) for w in self.vols.values())

    def _shingles(self, matn):
        w = searchable(matn).split()
        if len(w) < N: return []
        step = max(1, (len(w) - N) // max(K - 1, 1))
        return [hash(tuple(w[i:i+N])) for i in range(0, len(w) - N + 1, step)][:K]

    @staticmethod
    def _last_before(seq, at):
        found = None
        for p, name in seq:
            if p <= at: found = name
            else: break
        return found

    def lookup(self, matn):
        """يعيد None إن لم يجده، وإلا فملحقاته: المجلد والكتاب والباب،
        والحكم الوارد بعده في الكتاب، وسطر التخريج.

        الحكم يُقرأ من نافذةٍ بعد المتن، فقد يعود لروايةٍ أخرى في التعليق.
        لذلك يُسجَّل بدرجة ثقته، ولا يُبنى عليه إفراجٌ وحده عند التعارض."""
        sh = self._shingles(matn)
        if not sh: return None
        best = None
        for vol, table in self.idx.items():
            pos = [table[s] for s in sh if s in table]
            if len(pos) >= MIN_HITS and (best is None or len(pos) > len(best[1])):
                best = (vol, pos)
        if not best: return None
        vol, pos = best
        at, end = min(pos), max(pos) + N

        win  = self.vols[vol][end:end + WIN_AFTER]
        winD = self.disp[vol][end:end + WIN_AFTER]
        grade, i_g = None, None
        for i, w in enumerate(win):
            if w in GRADE_POS or w in GRADE_NEG:
                grade, i_g = w, i; break

        takhrij = None
        for i, w in enumerate(win):
            if w in TAKHRIJ_VERBS:
                takhrij = " ".join(winD[i:i + 12]); break

        return {"vol": int(vol), "hits": len(pos), "of": len(sh),
                "book": self._last_before(self.heads[vol], at),
                "bab":  self._last_before(self.babs[vol], at),
                "grade": grade,
                "grade_polarity": ("positive" if grade in GRADE_POS else
                                   "negative" if grade in GRADE_NEG else None),
                "grade_distance": i_g,
                "takhrij": takhrij}
