#!/usr/bin/env python3
"""ملءُ حقول `[يُملأ]` في السياسة والشروط — بقيمٍ يعطيها المالك.

    python3 launch/apply_owner_fields.py --entity "..." --privacy-email "..." \
        --support-email "..." --domain "..." --hosting-country "..." \
        --jurisdiction "..."

المالكُ يعمل من هاتفٍ بلا طرفيّة، فالمدخلُ الحقيقيُّ لهذا الملفّ هو
`.github/workflows/fill-legal-fields.yml` — نموذجٌ في المتصفّح يملؤه
ويضغط زرًّا. والمنطقُ هنا لا هناك ليُقرأ ويُختبر.

ولماذا لا تُخترع القيمُ ولو تخمينًا: وثيقةٌ قانونيّةٌ فيها اسمُ كيانٍ
أو بريدٌ لم يقلهما صاحبُها **أسوأُ من فراغٍ ظاهر** — الفراغُ يُرى فيُملأ،
والخطأُ يُوقَّع عليه فيَلزم. ولذلك:

  · قيمةٌ فارغة  →  يتوقّف قبل أن يمسّ ملفًّا
  · بريدٌ بلا `@` أو نطاقٌ بلا نقطة  →  يتوقّف
  · بقاءُ `[يُملأ` بعد الاستبدال  →  يتوقّف ويُرجع الملفّات كما كانت

فإمّا أن تكتمل الوثيقتان، وإمّا ألّا يتغيّر شيء. ولا حالةَ بينهما.
"""
import argparse, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# الوثيقتان وحدهما. وملفّاتُ التوثيق التي تذكر `[يُملأ]` وصفًا لا تُمَسّ —
# ذكرُ القاعدة ليس تطبيقًا لها.
TARGETS = ("docs/PRIVACY_POLICY.md", "docs/TERMS_OF_SERVICE.md")

# النصُّ الحرفيُّ في الملفّات ← اسمُ الحقل في سطر الأوامر
FIELDS = {
    "[يُملأ: الاسمُ الكامل أو اسمُ الكيان]": "entity",
    "[يُملأ: بريدُ الخصوصيّة]":              "privacy_email",
    "[يُملأ: بريدُ الدعم]":                  "support_email",
    "[يُملأ: النطاق]":                       "domain",
    "[يُملأ: بلدُ الاستضافة]":               "hosting_country",
    "[يُملأ: الاختصاصُ القضائيّ]":           "jurisdiction",
}

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
# نطاقٌ عارٍ: لا مخطَّط ولا مسار ولا مسافة — لأنّه يُطبع في نصٍّ قانونيّ
DOMAIN = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9-]+)+$")


def fail(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


def validate(vals: dict[str, str]) -> None:
    for key, val in vals.items():
        if not val or not val.strip():
            fail(f"الحقل «{key}» فارغ. لا تُخترع قيمةٌ مكانه.")
        if len(val.strip()) > 200:
            fail(f"الحقل «{key}» أطولُ من ٢٠٠ حرفًا — أهو قيمةٌ أم فقرة؟")
        if "[يُملأ" in val:
            fail(f"الحقل «{key}» ما يزال نصَّ العنصر النائب نفسَه.")
    for key in ("privacy_email", "support_email"):
        if not EMAIL.match(vals[key].strip()):
            fail(f"«{key}» = {vals[key]!r} ليس بريدًا صالحًا.")
    dom = vals["domain"].strip()
    if not DOMAIN.match(dom):
        fail(f"«domain» = {dom!r} — اكتب النطاق عاريًا: falah.app، "
             "بلا https:// وبلا مسارٍ وبلا مسافة.")


def main() -> int:
    p = argparse.ArgumentParser(description="ملءُ حقول السياسة والشروط")
    for name in sorted(set(FIELDS.values())):
        p.add_argument(f"--{name.replace('_', '-')}", required=True)
    p.add_argument("--check", action="store_true",
                   help="لا يكتب شيئًا — يقول كم عنصرًا نائبًا بقي")
    a = p.parse_args()

    if a.check:
        left = 0
        for rel in TARGETS:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                left += fh.read().count("[يُملأ")
        print(f"عناصرُ نائبةٌ باقية: {left}")
        return 0 if left == 0 else 1

    vals = {name: getattr(a, name).strip() for name in set(FIELDS.values())}
    validate(vals)

    # تُقرأ كلُّها أوّلًا وتُكتب كلُّها أخيرًا: فشلُ ملفٍّ لا يترك الآخر نصفَ مملوء
    written: dict[str, str] = {}
    total = 0
    for rel in TARGETS:
        path = os.path.join(ROOT, rel)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for token, name in FIELDS.items():
            n = text.count(token)
            if n:
                text = text.replace(token, vals[name])
                total += n
        if "[يُملأ" in text:
            fail(f"بقي عنصرٌ نائبٌ في {rel} لا يعرفه هذا الملفّ. "
                 "أُضيف حقلٌ جديدٌ ولم يُسجَّل هنا — لم يُكتب شيء.")
        written[path] = text

    if total == 0:
        print("· لا شيء ليُبدَّل — الوثيقتان مملوءتان أصلًا.")
        return 0

    for path, text in written.items():
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    print(f"✓ بُدِّل {total} موضعًا في {len(TARGETS)} وثيقتين")
    for name in sorted(vals):
        print(f"    {name:16} = {vals[name]}")
    print("\nراجعِ الوثيقتين بعينك قبل النشر. هذا يملأ فراغًا، ولا يُغني عن مراجعة.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
