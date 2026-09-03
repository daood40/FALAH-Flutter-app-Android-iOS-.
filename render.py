#!/usr/bin/env python3
"""محرّك التصيير — من بطاقةٍ مفحوصة إلى صورة PNG بمقاس المنصّة.

    python3 render.py --kind quran  --surah 94 --ayah 5 --to 6 --skin night
    python3 render.py --kind hadith --book bukhari --no 1 --ratio vertical
    python3 render.py --kind enc    --id 5907 --skin parch --out card.png

القاعدة: لا يُصيَّر إلا ما اجتاز الفحوص الخمسة والعشرين. البطاقة تُبنى من
نفس القالب الذي يراه المستخدم في الواجهة، فما رآه هو ما يُصدَّر.
الخطوط محلّية (أميري بترخيص OFL) فلا يتغيّر الرسم باختلاف الجهاز.
"""
import argparse, base64, os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api
from falah import verify as V

HERE  = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
DB    = os.path.join(HERE, "falah.db")

SIZES = {"square":   (1080, 1080), "portrait": (1080, 1350),
         "vertical": (1080, 1920), "wide":     (1920, 1080)}

SKINS = {
 # الرقّ: ورقٌ عتيقٌ كما في النموذج — حبرٌ بنيّ داكن وخطوطٌ رفيعة
 "parch": dict(frame="#C9AE7E",
   page="radial-gradient(120% 95% at 32% 18%, #F5EAD0 0%, #EEDFBC 42%, #E3D0A6 76%, #D9C69C 100%)",
   ink="#2B2116", sub="#6E5836", rule="rgba(94,73,42,.55)", hair="rgba(94,73,42,.30)",
   edge="rgba(94,73,42,.45)", glow="rgba(120,92,48,.22)"),
 "night": dict(frame="#0A1512",
   page="radial-gradient(120% 85% at 50% 30%, #12241D 0%, #0A1512 55%, #050A08 100%)",
   ink="#F0E5CA", sub="#A08F63", rule="rgba(201,162,71,.42)", hair="rgba(201,162,71,.22)",
   edge="rgba(201,162,71,.34)", glow="rgba(201,162,71,.10)"),
 "ivory": dict(frame="#E8E3D7",
   page="linear-gradient(170deg,#FCFAF5,#F2EEE3)",
   ink="#1E2A24", sub="#6E7A72", rule="rgba(47,93,74,.45)", hair="rgba(47,93,74,.22)",
   edge="rgba(47,93,74,.30)", glow="rgba(47,93,74,.06)"),
}

# ألوان التصميم: تغيّر الورق والإطار لا النصّ. «تلقائي» يترك لون الهيئة كما هو.
TINTS = {
 "auto":  {},
 "sand":  dict(frame="#C9AE7E",
   page="radial-gradient(120% 95% at 32% 18%, #F5EAD0 0%, #EEDFBC 42%, #E3D0A6 76%, #D9C69C 100%)",
   rule="rgba(94,73,42,.55)", hair="rgba(94,73,42,.30)",
   edge="rgba(94,73,42,.45)", glow="rgba(120,92,48,.22)"),
 "green": dict(frame="#2F5D4A",
   page="radial-gradient(120% 95% at 32% 18%, #F2F7F3 0%, #E2EDE5 42%, #CEDFD4 76%, #BFD4C8 100%)",
   rule="rgba(30,66,52,.55)", hair="rgba(30,66,52,.28)",
   edge="rgba(30,66,52,.42)", glow="rgba(30,66,52,.14)"),
 "navy":  dict(frame="#22344F",
   page="radial-gradient(120% 95% at 32% 18%, #F3F5F9 0%, #E4E9F1 42%, #D2DAE7 76%, #C4CEDE 100%)",
   rule="rgba(30,48,76,.52)", hair="rgba(30,48,76,.26)",
   edge="rgba(30,48,76,.40)", glow="rgba(30,48,76,.13)"),
 "coal":  dict(frame="#2A2A2A",
   page="radial-gradient(120% 95% at 32% 18%, #F6F5F3 0%, #EAE8E4 42%, #DBD8D2 76%, #CFCBC4 100%)",
   rule="rgba(40,40,40,.50)", hair="rgba(40,40,40,.25)",
   edge="rgba(40,40,40,.38)", glow="rgba(40,40,40,.12)"),
 "gold":  dict(frame="#0A1512",
   page="radial-gradient(120% 85% at 50% 30%, #12241D 0%, #0A1512 55%, #050A08 100%)",
   rule="rgba(201,162,71,.42)", hair="rgba(201,162,71,.22)",
   edge="rgba(201,162,71,.34)", glow="rgba(201,162,71,.10)"),
}

FONTS_UI = {"auto": None, "amiri": "'Amiri',serif",
            "amiri-quran": "'AmiriQuran','Amiri',serif"}

def skin_of(skin="parch", tint=None, ink=None):
    """الهيئة بعد تطبيق لون التصميم ولون الخط — بلا مساسٍ بالنصّ نفسه."""
    s = dict(SKINS.get(skin) or SKINS["parch"])
    s.update(TINTS.get(tint or "auto", {}))
    if ink and ink != "auto":
        s["ink"] = ink
    return s

def font_face(name, filename, weight=400):
    p = os.path.join(FONTS, filename)
    b64 = base64.b64encode(open(p, "rb").read()).decode()
    return (f"@font-face{{font-family:'{name}';font-weight:{weight};font-display:block;"
            f"src:url(data:font/ttf;base64,{b64}) format('truetype')}}")

def esc(s):
    return (str(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))

def _foot(watermark, swap, badge=None, labels=True, falah_mark=True):
    """ذيل البطاقة: خانتان مؤطَّرتان — علامة التطبيق وعلامة المستخدم، كلٌّ في
    خانتها كما في مخطّط البطاقة. ورقم الشريحة بينهما حين تُقسَّم الآية.

    خانة فلاح وحدها هي ما يُرفع بالاشتراك. أما نسبةُ النصّ إلى مصدره — اسم
    المصدر والدرجة ومن حكم بها والمفسّر والمترجم — فثابتةٌ في كل خطّة، لا
    تُرفع بمالٍ ولا بغيره."""
    lab = lambda t: f'<i>{t}</i>' if labels else ""
    app  = (f'<div class="mark"><b class="ltr">FALAH</b>{lab("العلامة المائية للتطبيق")}</div>'
            if falah_mark else "")
    user = f'<div class="mark"><b>{esc(watermark)}</b>{lab("العلامة المائية للمستخدم")}</div>'
    first, last = (app, user) if swap else (user, app)
    mid = f'<div class="mark num">{esc(badge)}</div>' if badge else ""
    return f'<div class="marks">{first}{mid}{last}</div>'

def _tiles(text, scale, rows=4, cols=3):
    """علامةٌ مكرّرة على مساحة الورق. تُرسم **خلف** النصّ بشفافيةٍ خفيفة —
    فما يُقرأ يبقى مقروءًا، والعلامة تمنع السطو ولا تحجب حرفًا."""
    cells = []
    for r in range(rows):
        for c in range(cols):
            top  = (r + 0.5) * (100.0 / rows)
            left = (c + 0.5) * (100.0 / cols) + (5 if r % 2 else -5)
            cells.append(f'<b style="top:{top:.1f}%;left:{left:.1f}%;'
                         f'transform:translate(-50%,-50%) rotate(-24deg)">{esc(text)}</b>')
    return f'<div class="tiles">{"".join(cells)}</div>'

def _css(s, w, h, scale, body_font="'Amiri',serif", body_wt="700", body_size=48,
         lines_ar=3, lines_en=2):
    """قواعد العرض المشتركة بين البطاقة والغلاف والخاتمة — إطارٌ واحد للسلسلة كلّها."""
    return f"""
{font_face('Amiri','Amiri-Regular.ttf',400)}
{font_face('Amiri','Amiri-Bold.ttf',700)}
{font_face('AmiriQuran','AmiriQuran.ttf',400)}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{w}px;height:{h}px;overflow:hidden}}
.slide{{width:{w}px;height:{h}px;padding:{18*scale:.0f}px;background:{s['frame']};display:flex}}
.paper{{flex:1;display:flex;flex-direction:column;color:{s['ink']};overflow:hidden;
  padding:{26*scale:.0f}px {28*scale:.0f}px {22*scale:.0f}px;background:{s['page']};
  border:1px solid {s['edge']};box-shadow:0 0 {80*scale:.0f}px {s['glow']} inset;
  position:relative}}
/* بقعُ الورق العتيق: طبقاتٌ شفيفة تكسر استواء اللون */
.paper::before{{content:"";position:absolute;inset:0;pointer-events:none;opacity:.55;
  background-image:
    radial-gradient(38% 26% at 12% 18%,{s['glow']} 0%,transparent 70%),
    radial-gradient(30% 22% at 88% 12%,{s['glow']} 0%,transparent 70%),
    radial-gradient(42% 30% at 78% 86%,{s['glow']} 0%,transparent 72%),
    radial-gradient(26% 20% at 22% 78%,{s['glow']} 0%,transparent 70%)}}
.top{{display:flex;text-align:center;position:relative;
  padding-bottom:{14*scale:.0f}px}}
.cell{{flex:1;padding:0 {10*scale:.0f}px;line-height:1.35;min-width:0}}
.cell:not(:last-child){{border-inline-end:1px solid {s['hair']}}}
.cell b{{display:block;font-family:'Amiri',serif;font-weight:700;
  font-size:{24*scale:.0f}px;color:{s['ink']};text-wrap:balance}}
.cell i{{display:block;font-family:'Amiri',serif;font-style:normal;
  font-size:{17*scale:.0f}px;color:{s['sub']};direction:ltr;
  margin-top:{3*scale:.0f}px;letter-spacing:.03em}}
.hr{{height:1px;margin:{16*scale:.0f}px 0;flex:none;position:relative;
  background:{s['rule']};opacity:.75}}
.hr.key{{opacity:1}}
/* تناسق المساحات: النصّ يأخذ الحصّة الكبرى، وكل صندوقٍ تحته حصّةً ثابتة،
   فلا تتفاوت البطاقات حين يطول شرحٌ أو يقصر */
.main{{flex:5 1 0;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:{18*scale:.0f}px;padding:{12*scale:.0f}px;text-align:center;min-height:0;
  overflow:hidden;position:relative}}
.text{{font-family:{body_font};font-weight:{body_wt};
  font-size:{body_size*scale:.0f}px;line-height:{2.15 if body_wt=="400" else 1.95};color:{s['ink']}}}
.attr{{font-family:'Amiri',serif;font-size:{24*scale:.0f}px;color:{s['sub']}}}
/* السند: أصغر من المتن وأخفت، فالمتن هو المقصود والسندُ سياقُه */
.isnad{{font-family:'Amiri',serif;font-size:{26*scale:.0f}px;line-height:1.75;
  color:{s['sub']};opacity:.95;padding:0 {6*scale:.0f}px;flex:none}}
.hr.hair{{margin:{10*scale:.0f}px auto;width:38%;opacity:.4}}
/* العلامة المكرّرة: تحت النصّ لا فوقه، فلا تُشوّش على قراءة نصٍّ شرعي */
.tiles{{position:absolute;inset:0;z-index:0;pointer-events:none;overflow:hidden}}
.tiles b{{position:absolute;font-family:'Amiri',serif;font-weight:700;white-space:nowrap;
  color:{s['sub']};opacity:.11;transform:rotate(-24deg);
  font-size:{22*scale:.0f}px;letter-spacing:.12em}}
.paper > *:not(.tiles){{position:relative;z-index:1}}
.row{{flex:2 1 0;display:flex;flex-direction:column;justify-content:flex-start;
  text-align:center;padding:0 {14*scale:.0f}px;min-height:0;overflow:hidden;position:relative}}
.cap{{font-family:'Amiri',serif;font-size:{20*scale:.0f}px;color:{s['sub']};flex:none;
  margin-bottom:{8*scale:.0f}px;letter-spacing:.03em}}
/* السطر الأخير ينتهي عند حدّ السطر لا في وسطه، فلا يُبتر الشرح بترًا */
.ar{{font-family:'Amiri',serif;font-size:{27*scale:.0f}px;line-height:1.85;color:{s['ink']};opacity:.92;
  display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:{lines_ar};overflow:hidden}}
.en{{font-family:'Amiri',serif;font-size:{25*scale:.0f}px;line-height:1.6;color:{s['ink']};
  direction:ltr;opacity:.92;display:-webkit-box;-webkit-box-orient:vertical;
  -webkit-line-clamp:{lines_en};overflow:hidden}}
.marks{{display:flex;flex:none;border:1px solid {s['rule']};font-family:'Amiri',serif}}
.mark{{flex:1;text-align:center;padding:{10*scale:.0f}px {8*scale:.0f}px;min-width:0}}
.mark:not(:last-child){{border-inline-end:1px solid {s['rule']}}}
.mark b{{display:block;font-weight:700;font-size:{24*scale:.0f}px;color:{s['ink']};
  letter-spacing:.04em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.mark b.ltr{{direction:ltr}}
.mark i{{display:block;font-style:normal;font-size:{15*scale:.0f}px;color:{s['sub']};
  margin-top:{3*scale:.0f}px;letter-spacing:.02em}}
.mark.num{{flex:0 0 {130*scale:.0f}px;display:flex;align-items:center;justify-content:center;
  font-size:{22*scale:.0f}px;color:{s['sub']};font-variant-numeric:tabular-nums}}
.ttl{{font-family:'Amiri',serif;font-weight:700;font-size:{78*scale:.0f}px;
  line-height:1.4;color:{s['ink']}}}
.ttl-en{{font-family:'Amiri',serif;font-size:{30*scale:.0f}px;color:{s['sub']};
  direction:ltr;letter-spacing:.08em;margin-top:{10*scale:.0f}px}}
.kicker{{font-family:'Amiri',serif;font-size:{26*scale:.0f}px;color:{s['sub']};letter-spacing:.14em}}
.list{{font-family:'Amiri',serif;font-size:{27*scale:.0f}px;line-height:2.05;color:{s['ink']};
  opacity:.94;text-align:center}}
.note{{font-family:'Amiri',serif;font-size:{22*scale:.0f}px;color:{s['sub']};line-height:1.8;
  margin-top:{22*scale:.0f}px}}
"""

def _cover_scale(w, h):
    """الغلاف والخاتمة صفحتان خفيفتان: تُقاسان بالضلع الأقصر، وتكبُر في الطولي
    كي لا يبتلع الفراغُ النصّ."""
    return min(w, h) / 1080.0 * (1.3 if h > w else 1.0)

def build_cover_html(title_ar, title_en, kicker, lines, skin="parch", ratio="square",
                     watermark="قناتك", swap=False, badge=None):
    """غلاف السلسلة — نفس الإطار، بلا نصٍّ شرعيّ حتى لا يُنسب للغلاف ما ليس منه."""
    w, h = SIZES[ratio]; s = SKINS[skin]; scale = _cover_scale(w, h)
    body = "".join(f'<div class="list">{esc(x)}</div>' for x in lines)
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<style>{_css(s, w, h, scale)}</style></head><body><div class="slide"><div class="paper">
<div class="main">
  <div class="kicker">{esc(kicker)}</div>
  <div class="hr key" style="width:60%"></div>
  <div><p class="ttl">{esc(title_ar)}</p><p class="ttl-en">{esc(title_en)}</p></div>
  {body}
</div>
<div class="hr"></div>{_foot(watermark, swap, badge)}
</div></div></body></html>"""

def build_end_html(heading, entries, note, skin="parch", ratio="square",
                   watermark="قناتك", swap=False, badge=None):
    """خاتمة السلسلة — سندُ ما عُرض: المصدر والطبعة والحكم، لا دعوةٌ للمتابعة فحسب."""
    w, h = SIZES[ratio]; s = SKINS[skin]; scale = _cover_scale(w, h)
    body = "".join(f'<div class="list">{esc(x)}</div>' for x in entries)
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<style>{_css(s, w, h, scale)}</style></head><body><div class="slide"><div class="paper">
<div class="main">
  <div class="kicker">{esc(heading)}</div>
  <div class="hr key" style="width:60%"></div>
  {body}
  <div class="note">{esc(note)}</div>
</div>
<div class="hr"></div>{_foot(watermark, swap, badge)}
</div></div></body></html>"""

def build_html(card, kind, skin="parch", ratio="square", watermark="قناتك",
               swap=False, show_tafsir=True, show_translation=True, badge=None, part=None,
               tint=None, ink=None, font=None, falah_mark=True,
               isnad=False, tile_mark=None):
    w, h = SIZES[ratio]
    s = skin_of(skin, tint, ink)
    c = card["cells"]
    isQ = kind == "quran"
    scale = w / 1080.0                       # كل المقاسات مبنية على ١٠٨٠ ثم تُقاس

    # كم سطرًا يسع الصندوق فعلًا في هذا المقاس — فالحدّ من المساحة لا من الرأي
    LN = {"square": (2, 2), "portrait": (3, 3), "vertical": (5, 4), "wide": (2, 2)}[ratio]
    CLIP = {"square": (115, 145), "portrait": (185, 225),
            "vertical": (275, 290), "wide": (220, 290)}[ratio]

    def clip(t, n):
        """قصٌّ عند حدّ الكلمة لا في وسطها — التفسير يُختصر ولا يُبتر لفظه."""
        t = (t or "").strip()
        if len(t) <= n: return t
        cut = t[:n]
        sp  = cut.rfind(" ")
        return (cut[:sp] if sp > n * 0.6 else cut).rstrip("،.,؛ ") + "…"

    rows = ""
    tf = card.get("tafsir") or card.get("sharh")
    if show_tafsir and tf:
        rows += (f'<div class="hr"></div><div class="row">'
                 f'<div class="cap">{esc(tf["source"])}</div>'
                 f'<div class="ar">{esc(clip(tf["text"], CLIP[0]))}</div></div>')
    tr = card.get("translation")
    if show_translation and tr:
        rows += (f'<div class="hr"></div><div class="row">'
                 f'<div class="cap">{esc(tr["source"])}</div>'
                 f'<div class="en">{esc(clip(tr["text"], CLIP[1]))}</div></div>')

    # السند: يُعرض فوق المتن بخطٍّ أصغر، فيبقى المتن هو الأبرز ولا يغيب
    # الإسناد. وهو منقولٌ بنصّه من المصدر، فإن طال قُصّ عند حدّ الكلمة.
    isnad_block = ""
    if isnad and not isQ:
        full = (card.get("isnad_full") or "").split("\n")[0].strip()
        if full:
            isnad_block = (f'<div class="isnad">{esc(clip(full, CLIP[0] + 160))}</div>'
                           f'<div class="hr hair"></div>')

    attr = ""
    if not isQ:
        bits = [card.get("narrator") or card.get("intro") or ""]
        if card.get("takhrij"): bits.append(" — ".join(card["takhrij"][:2]))
        attr = f'<div class="attr">{esc(" · ".join(x for x in bits if x))}</div>'

    cells = "".join(f'<div class="cell"><b>{esc(c[k][0])}</b><i>{esc(c[k][1])}</i></div>'
                    for k in ("c1","c2","c3","c4"))
    body_font = FONTS_UI.get(font or "auto") or \
                ("'AmiriQuran','Amiri',serif" if isQ else "'Amiri',serif")
    body_wt   = "400" if (isQ or "AmiriQuran" in body_font) else "700"
    # علامتا التنصيص تُفتحان في الشريحة الأولى وتُغلقان في الأخيرة، وما بينهما
    # يحمل علامة الاتصال — فلا تُوهم الشريحةُ أنها نصٌّ مكتمل.
    body_txt = esc(card["text"])
    if part:
        i, n = part
        head_m = ("﴿ " if isQ else "«") if i == 1 else "… "
        tail_m = (" ﴾" if isQ else "»") if i == n else " …"
        text = head_m + body_txt + tail_m
    else:
        text = ("﴿ " + body_txt + " ﴾") if isQ else ("«" + body_txt + "»")

    tiles = _tiles(tile_mark, scale) if tile_mark else ""
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<style>{_css(s, w, h, scale, body_font, body_wt, 54 if isQ else 48, LN[0], LN[1])}</style>
</head><body><div class="slide"><div class="paper">{tiles}
<div class="top">{cells}</div><div class="hr key"></div>
<div class="main">{isnad_block}<p class="text">{text}</p>{attr}</div>
{rows}<div style="height:{14*scale:.0f}px"></div>{_foot(watermark, swap, badge, falah_mark=falah_mark)}
</div></div></body></html>"""

def split_text(text, max_chars=260):
    """يقسّم النصّ الطويل على شرائح بحدود الكلمات — لا يُقصّ منه حرف.
    الآيةُ الطويلة تُقرأ على شريحتين أو ثلاث، ولا تُحجب ولا تُبتر."""
    words, parts, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            parts.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur: parts.append(cur)
    return parts or [text]

def render_split(card, kind, skin="parch", ratio="square", watermark="قناتك",
                 out_prefix="card", max_chars=260, swap=False,
                 tint=None, ink=None, font=None):
    """يصيّر النصّ الطويل شرائحَ مرقّمة، ويُظهر التفسير والترجمة في الأخيرة."""
    parts = split_text(card["text"], max_chars)
    files = []
    for i, part in enumerate(parts, 1):
        piece = dict(card, text=part)
        last  = i == len(parts)
        html = build_html(piece, kind, skin, ratio, watermark, swap,
                          show_tafsir=last, show_translation=last,
                          badge=f"{api.arabic_num(i)} / {api.arabic_num(len(parts))}",
                          part=(i, len(parts)), tint=tint, ink=ink, font=font)
        out = f"{out_prefix}_{i:02d}.png"
        render(html, out, ratio); files.append(out)
    return files

def fetch_card(kind, **kw):
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    if kind == "quran":
        it, ctx = api.quran_card(c, kw["surah"], kw["ayah"], kw.get("to"), True, True)
    elif kind == "enc":
        it, ctx = api.enc_card(c, kw["id"])
    else:
        it, ctx = api.hadith_card(c, kw["book"], kw["no"])
    c.close()
    if not it: raise SystemExit("البطاقة غير موجودة")
    rep = V.run(it, ctx)
    if not rep["ok"]:
        raise SystemExit("محجوبة — لم تجتز الفحص: " + "، ".join(rep["failed"]))
    return it, rep

def render(html, out, ratio):
    from playwright.sync_api import sync_playwright
    w, h = SIZES[ratio]
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html); path = f.name
    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg.goto("file://" + path)
        pg.wait_for_timeout(350)              # مهلة لتحميل الخطوط المدمجة
        pg.screenshot(path=out)
        b.close()
    os.unlink(path)
    return out

if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--kind", default="quran", choices=["quran","hadith","enc"])
    a.add_argument("--surah", type=int); a.add_argument("--ayah", type=int)
    a.add_argument("--to", type=int); a.add_argument("--book"); a.add_argument("--no", type=int)
    a.add_argument("--id", type=int)
    a.add_argument("--skin", default="parch", choices=list(SKINS))
    a.add_argument("--ratio", default="square", choices=list(SIZES))
    a.add_argument("--wm", default="قناتك"); a.add_argument("--swap", action="store_true")
    a.add_argument("--out", default="card.png")
    n = a.parse_args()
    card, rep = fetch_card(n.kind, surah=n.surah, ayah=n.ayah, to=n.to,
                           book=n.book, no=n.no, id=n.id)
    html = build_html(card, "quran" if n.kind=="quran" else "hadith",
                      n.skin, n.ratio, n.wm, n.swap)
    render(html, n.out, n.ratio)
    w, h = SIZES[n.ratio]
    print(f"✓ {n.out}  {w}×{h}  · اجتاز {rep['passed']}/{rep['total']} فحصًا")
