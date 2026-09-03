#!/usr/bin/env python3
"""أيقونات فلاح — تُصنع من نفس هيئة البطاقة، فما يراه المستخدم في المتجر
هو ما يراه في التطبيق. لا صور خارجية ولا خطوط من الشبكة.

    python3 icons.py            → icons/*.png  و icons/maskable-*.png
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as RD

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "icons")

# المقاسات التي يطلبها المتجران والويب
SIZES = [16, 32, 48, 72, 96, 128, 144, 152, 167, 180, 192, 256, 384, 512, 1024]

def html(px, maskable=False):
    """رقٌّ عتيقٌ وحرفٌ واحد. القناعية تترك هامشًا آمنًا ٢٠٪ كما تشترط أندرويد."""
    s = RD.SKINS["parch"]
    pad = 0.20 if maskable else 0.10
    fonts = RD.font_face("Amiri", "Amiri-Bold.ttf", 700)
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>
{fonts}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{px}px;height:{px}px;overflow:hidden}}
.ic{{width:{px}px;height:{px}px;background:{s['page']};display:flex;
  align-items:center;justify-content:center;position:relative}}
.ring{{position:absolute;inset:{px*pad*0.55:.0f}px;border:{max(1,px//64)}px solid {s['rule']};
  border-radius:{px*0.14:.0f}px}}
.g{{font-family:'Amiri',serif;font-weight:700;color:{s['ink']};
  font-size:{px*(0.52 if not maskable else 0.44):.0f}px;line-height:1;
  margin-top:{-px*0.03:.0f}px}}
</style></head><body><div class="ic"><div class="ring"></div><div class="g">ف</div></div></body></html>"""

def render_icon(px, path, maskable=False):
    from playwright.sync_api import sync_playwright
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html(px, maskable)); src = f.name
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        pg = b.new_page(viewport={"width": px, "height": px}, device_scale_factor=1)
        pg.goto("file://" + src); pg.wait_for_timeout(220)
        pg.screenshot(path=path); b.close()
    os.remove(src)

def main():
    os.makedirs(OUT, exist_ok=True)
    for px in SIZES:
        render_icon(px, os.path.join(OUT, f"icon-{px}.png"))
        print(f"  icon-{px}.png")
    for px in (192, 512):
        render_icon(px, os.path.join(OUT, f"maskable-{px}.png"), maskable=True)
        print(f"  maskable-{px}.png")
    # شاشة البدء لأندرويد وiOS: نفس الورق بالمقاس الأكبر
    render_icon(1024, os.path.join(OUT, "splash-1024.png"))
    print("  splash-1024.png")
    print(f"\n{len(SIZES)+3} أيقونة في {OUT}")

if __name__ == "__main__":
    main()
