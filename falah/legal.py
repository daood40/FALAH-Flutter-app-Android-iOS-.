"""الوثائقُ القانونيّةُ صفحاتٍ عامّةً — من مصدرٍ واحدٍ لا نسختين.

المتجران يشترطان **رابطًا عامًّا** لسياسة الخصوصيّة وشروط الاستخدام، يُفتح
بلا حسابٍ ولا جلسة. ولو كُتبت الصفحاتُ HTML بجانب ملفّات Markdown لصارت
نسختان تفترقان: تُحدَّث إحداهما وتبقى الأخرى، ويقرأ المراجعُ القديمةَ.

فالمصدرُ واحد: `docs/PRIVACY_POLICY.md` و`docs/TERMS_OF_SERVICE.md`، وهذه
الوحدةُ تصيّرهما صفحتين. ومن عدّل الوثيقةَ تغيّرت الصفحةُ في اللحظة نفسِها.

والتصييرُ هنا **مكتوبٌ بالمكتبة القياسيّة**، لا مكتبةَ Markdown تُضاف
لأجل صفحتين — والمشروعُ لا يُدخل اعتماديّةً إلا حين تعجز بايثون نفسُها.
"""
import html
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(HERE, "docs")

PAGES = {
    "/privacy": ("PRIVACY_POLICY.md", "سياسة الخصوصيّة — فَلاح"),
    "/terms": ("TERMS_OF_SERVICE.md", "شروط الاستخدام — فَلاح"),
}

_CSS = """
:root{--ink:#241d13;--bg:#faf7f0;--mut:#6b5f4e;--line:#e2d9c8;--acc:#7a5c2e}
@media(prefers-color-scheme:dark){:root{--ink:#ece3d4;--bg:#16130e;
  --mut:#a2947e;--line:#33291d;--acc:#d4b073}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.9 system-ui,'Segoe UI',Tahoma,sans-serif;direction:rtl}
main{max-width:46rem;margin:0 auto;padding:2.5rem 1.25rem 5rem}
h1{font-size:1.9rem;line-height:1.4;margin:0 0 .3em;letter-spacing:-.01em}
h2{font-size:1.3rem;margin:2.4em 0 .6em;padding-bottom:.3em;
  border-bottom:1px solid var(--line)}
h3{font-size:1.05rem;margin:1.8em 0 .4em;color:var(--acc)}
p,li{margin:.7em 0}
ul{padding-inline-start:1.4em}
code{background:color-mix(in srgb,var(--acc) 12%,transparent);
  padding:.12em .4em;border-radius:4px;font-size:.88em;direction:ltr;
  display:inline-block}
blockquote{margin:1.4em 0;padding:.8em 1.1em;border-inline-start:3px solid var(--acc);
  background:color-mix(in srgb,var(--acc) 7%,transparent);color:var(--mut)}
blockquote p{margin:.3em 0}
table{width:100%;border-collapse:collapse;margin:1.2em 0;font-size:.93rem;
  display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:.5em .7em;text-align:start}
th{background:color-mix(in srgb,var(--acc) 10%,transparent);font-weight:600}
hr{border:0;border-top:1px solid var(--line);margin:2.5em 0}
strong{font-weight:650}
a{color:var(--acc)}
footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--line);
  color:var(--mut);font-size:.87rem}
"""


def _inline(s):
    """تصييرُ ما داخل السطر — **والهروبُ أوّلًا دائمًا.**

    الترتيبُ مقصود: يُهرَّب النصُّ كلُّه، ثم تُدخَل الوسومُ التي نولّدها نحن.
    ولو عُكس لأمكن أن يُهرَّب وسمُنا أو يمرَّ وسمُ الكاتب. والوثيقةُ عندنا
    مكتوبةٌ بأيدينا، لكنّ المصيِّرَ الذي يأمن مصدرَه يصير ثغرةً يوم يُغذّى
    من غيره.
    """
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def render(md):
    """Markdown → HTML: العناوينُ والفقراتُ والقوائمُ والجداولُ والاقتباس."""
    out, lines, i = [], md.splitlines(), 0
    para: list = []

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i]
        st = ln.strip()

        if not st:
            flush()
            i += 1
            continue

        if st.startswith("#"):
            flush()
            n = len(st) - len(st.lstrip("#"))
            out.append(f"<h{min(n, 4)}>{_inline(st[n:].strip())}</h{min(n, 4)}>")
            i += 1
            continue

        if set(st) <= {"-", "—"} and len(st) >= 3:
            flush()
            out.append("<hr>")
            i += 1
            continue

        # جدول: سطرُ رؤوسٍ يتبعه سطرُ فواصل
        if st.startswith("|") and i + 1 < len(lines) and \
                re.fullmatch(r"\|[\s:|-]+\|", lines[i + 1].strip()):
            flush()
            head = _cells(st)
            out.append("<table><thead><tr>" +
                       "".join(f"<th>{_inline(c)}</th>" for c in head) +
                       "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>"
                                            for c in _cells(lines[i])) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue

        if st.startswith(("- ", "* ")):
            flush()
            out.append("<ul>")
            while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                out.append("<li>" + _inline(lines[i].strip()[2:]) + "</li>")
                i += 1
            out.append("</ul>")
            continue

        if st.startswith(">"):
            flush()
            out.append("<blockquote>")
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<p>" + _inline(" ".join(x for x in buf if x)) + "</p>")
            out.append("</blockquote>")
            continue

        para.append(st)
        i += 1

    flush()
    return "\n".join(out)


def page(path):
    """يعيد (html, None) أو (None, سببُ التعذّر). ولا يُرمى استثناءٌ للخادم."""
    entry = PAGES.get(path)
    if not entry:
        return None, "غير معروف"
    fname, title = entry
    # `basename` رغم أنّ الاسمَ من ثابتٍ عندنا: الحدُّ يُرسم على ما يُنفَّذ
    # لا على ما نثق أنه لن يتغيّر
    fpath = os.path.join(DOCS, os.path.basename(fname))
    if not os.path.exists(fpath):
        return None, "الوثيقة غير منشورة"
    with open(fpath, encoding="utf-8") as f:
        body = render(f.read())
    other = "/terms" if path == "/privacy" else "/privacy"
    other_ar = "شروط الاستخدام" if path == "/privacy" else "سياسة الخصوصيّة"
    return (
        "<!doctype html><html lang=ar dir=rtl><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f"<body><main>{body}"
        f"<footer><a href='{other}'>{other_ar}</a> · "
        "<a href='/'>فَلاح</a></footer></main></body></html>"
    ), None


__all__ = ["PAGES", "render", "page"]
