#!/usr/bin/env python3
"""يجمع صفحة المعاينة: الهيئة + الواجهة + المادّة المضغوطة في ملفٍ واحد."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
r = lambda n: open(os.path.join(HERE, n), encoding="utf-8").read()

def main(out="falah-preview.html", embed=True):
    head, body = r("preview_head.html"), r("preview_body.html")
    data = r("preview-data.b64") if embed else ""
    page = head + "\n" + body.replace("__DATA__", data)
    p = os.path.join(HERE, out)
    open(p, "w", encoding="utf-8").write(page)
    print(f"{out}: {len(page)/1e6:.2f} م.ب")
    return p

if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
