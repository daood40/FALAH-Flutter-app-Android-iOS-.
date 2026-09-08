#!/usr/bin/env python3
"""حارسُ الخضرة الكاذبة — يفرّق بين تخطٍّ معلَنٍ وتخطٍّ صامت.

    flutter test --file-reporter json:ft.json
    python3 check_skips.py ft.json

**المشكلةُ التي يحلّها:** اختبارٌ يتخطّى نفسه يُحسب «ناجحًا» في السطر
الأخير، و«All tests passed» تُطبع على مجموعةٍ لم يجرِ منها شيء. وهذا أسوأُ
من الفشل: الفشلُ يُرى، والتخطّي يُظنّ نجاحًا.

**والتفريق:** قاعدةُ المحتوى (١٦٥ م.ب من الخام) لا تدخل git، فالاستنساخُ
النظيفُ في خطِّ التكامل لا يملكها — واختباراتُ النصِّ الشرعيِّ لا تجري.
وهذا سببٌ **نعرفه ونقوله**، لا عطبٌ نخفيه. فيُقبل ما وُسم `DECLARED_SKIP`
ويُطبع بالاسم، ويُسقط الأنبوبَ أيُّ تخطٍّ سواه.

ويُكتب ملفًّا مستقلًّا لا سطورًا داخل YAML: ما لا يُشغَّل إلا في خطِّ التكامل
لا يُختبر أبدًا، وحارسٌ معطوبٌ أسوأُ من لا حارس.
"""
import json
import os
import sys

MARK = "DECLARED_SKIP"


def read(path):
    """يعيد (المتخطّاةُ المعلَنة، المتخطّاةُ الصامتة، عددُ ما جرى فعلًا)."""
    names, reasons, skipped, ran = {}, {}, [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = e.get("type")
            if t == "testStart":
                names[e["test"]["id"]] = e["test"]["name"]
            elif t == "print" and e.get("messageType") == "skip":
                # سببُ التخطّي لا يُذكر في `testDone` — يأتي حدثَ طباعةٍ
                # موسومًا `skip` ومربوطًا بالاختبار بمعرِّفه
                reasons[e.get("testID")] = e.get("message", "")
            elif t == "testDone":
                tid = e.get("testID")
                nm = names.get(tid, str(tid))
                # مجموعاتُ `setUpAll`/`tearDownAll` تظهر كاختباراتٍ خفيّة
                if e.get("hidden"):
                    continue
                if e.get("skipped"):
                    skipped.append((nm, reasons.get(tid, "")))
                else:
                    ran += 1
    declared = [(n, r) for n, r in skipped if MARK in r]
    silent = [(n, r) for n, r in skipped if MARK not in r]
    return declared, silent, ran


def main(argv):
    path = argv[1] if len(argv) > 1 else "ft.json"
    if not os.path.exists(path):
        print(f"::error::لم يُنتج تقريرُ الاختبارات ({path}) — لم تجرِ أصلًا")
        return 1

    declared, silent, ran = read(path)
    print(f"جرى فعلًا: {ran} · معلَنُ التخطّي: {len(declared)} · "
          f"صامتُ التخطّي: {len(silent)}")

    if declared:
        print(f"::warning::{len(declared)} اختبارًا لم يجرِ بسببٍ معلَن — "
              "**غيرُ محقَّقةٍ لا ناجحة**:")
        for n, r in declared:
            print(f"  ~ {n}\n      ← {r}")

    if silent:
        print("::error::تخطٍّ صامتٌ لا يُمرَّر على أنه نجاح:")
        for n, r in silent:
            print(f"  ~ {n}" + (f"\n      ← {r}" if r else ""))
        return 1

    # مجموعةٌ لم يجرِ منها شيءٌ ليست ناجحة، ولو خلت من الصامت
    if ran == 0:
        print("::error::لم يجرِ اختبارٌ واحد — لا يُعدُّ هذا نجاحًا")
        return 1

    print(f"✓ لا تخطٍّ صامت (جرى {ran})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
