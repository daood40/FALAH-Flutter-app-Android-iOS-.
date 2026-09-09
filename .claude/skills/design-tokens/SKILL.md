---
name: design-tokens
description: رموز التصميم — الطبقات الثلاث (أولية، دلالية، مكوّنات)، التسمية المنضبطة، الترجمة إلى CSS custom properties وثوابت Dart وJSON مشترك، الرموز المتبدّلة مع الوضع الليلي، وفرض منع القيم الخام. تُفتح عند ذكر "رموز تصميم", "متغيّرات الثيم", "توكن", "design tokens", "css variables", "theme tokens", "semantic colors".
---

# رموز التصميم (Design Tokens)

الرمز = اسم ثابت لقيمة تصميم، يُستهلك في كل مكان بدل كتابة القيمة. الفائدة ليست الاختصار، بل **أن التغيير يحدث في مكان واحد** وأن الوضع الليلي والعلامة الثانية يصبحان تبديل قيم لا إعادة كتابة.

> التنفيذ في Flutter: افتح مهارة flutter-ui-design.

## لماذا الرموز تمنع الفوضى

بدون رموز تتكرر القيمة في 40 موضعاً، فتظهر سبعة "رماديات" متقاربة تجعل الواجهة قذرة، ويصبح الوضع الليلي مستحيلاً دون تعديل كل ملف، وتغيير لون العلامة يستغرق يوماً بدل دقيقة.

القاعدة الحاكمة: **لا قيمة خام في أي ملف مكوّن. أبداً.**

## الطبقات الثلاث

```
أولية (primitive)  →  دلالية (semantic)  →  مكوّن (component)
gray-900              text-primary           button-primary-label
blue-600              action-primary         button-primary-bg
space-4               space-inline-md        button-padding-x
```

| الطبقة | تصف | من يستهلكها | تتبدّل مع الوضع الليلي؟ |
|---|---|---|---|
| أولية | القيمة الخام المسمّاة (`blue-600 = #2563EB`) | الطبقة الدلالية فقط | ❌ ثابتة تماماً |
| دلالية | الدور في الواجهة (`surface-raised`, `text-muted`) | المكوّنات والشاشات | ✅ هنا يحدث التبديل |
| مكوّن | استثناء يخصّ مكوّناً واحداً | ذلك المكوّن فقط | تبعاً للدلالي |

الطبقة الثالثة **اختيارية**. لا تنشئها إلا حين يحتاج مكوّن قيمة لا يمثّلها أي رمز دلالي. مطوّر فردي غالباً يحتاج طبقتين فقط.

## أسماء حقيقية للطبقة الأولية

```
color:  gray-50…950 (11 درجة) | brand-50…900 | red-500/600 green-500/600 amber-500 blue-500
space:  space-1=4 space-2=8 space-3=12 space-4=16 space-6=24 space-8=32 space-12=48
font:   font-size-1=12 -2=14 -3=16 -4=20 -5=24 -6=32
        font-weight-regular=400 -medium=500 -bold=700
        line-height-tight=1.3 -normal=1.6 -relaxed=1.8
radius: radius-sm=8 radius-md=12 radius-lg=16 radius-full=9999
shadow: shadow-0 shadow-1 shadow-2 shadow-3
motion: duration-fast=100ms -base=200ms -slow=320ms
```

الأرقام تصف **الفاتح إلى الداكن** دائماً (50 أفتح، 950 أغمق) — لا تعكس السلّم في وضع دون آخر.

## أسماء حقيقية للطبقة الدلالية

| المجموعة | الرموز | الدور |
|---|---|---|
| الأسطح | `bg-canvas`, `bg-surface`, `bg-surface-raised`, `bg-surface-sunken`, `bg-overlay` | خلفية الشاشة، البطاقة، سطح فوق سطح، منطقة غائرة، طبقة خلف الحوار |
| النص | `text-primary`, `text-secondary`, `text-muted`, `text-on-action`, `text-inverse` | أساسي، مساعد، تلميح/نائب، فوق الزر، فوق خلفية معكوسة |
| الأفعال | `action-primary` (+ `-hover`, `-pressed`), `action-secondary`, `action-disabled` | خلفيات الأزرار وحالاتها |
| الحدود | `border-subtle`, `border-default`, `border-strong`, `border-focus` | فاصل خفيف، حدّ حقل، حدّ بارز، حلقة التركيز |
| الحالات | `status-success/danger/warning/info` + نسخة `-bg` لكل واحد | لون النص/الأيقونة ولون الخلفية |

القاعدة: الاسم الدلالي يجيب على "**أين يُستعمل**"، لا "**ما لونه**". `text-danger` صحيح، `text-red` خطأ.

## الخطأ الشائع الأول: استعمال الأولي مباشرة

```css
/* خطأ — المكوّن يعرف اللون الخام */
.btn-primary { background: var(--blue-500); }

/* صحيح — المكوّن يعرف الدور فقط */
.btn-primary { background: var(--action-primary); }
```

الفرق ليس شكلياً. في الحالة الأولى، الوضع الليلي يجبرك على تعديل المكوّن. في الثانية تعدّل تعريف `action-primary` وحده. أي `blue-500` يظهر داخل ملف مكوّن هو دَين يجب إغلاقه فوراً.

## CSS custom properties

الأولية في `:root` ولا تتكرر. الدلالية فقط هي التي تُعاد في الوضع الداكن.

```css
:root {
  /* أولية — ثابتة، تُعرَّف مرة واحدة */
  --gray-50:#F8FAFC; --gray-200:#E2E8F0; --gray-500:#64748B;
  --gray-900:#0F172A; --gray-950:#020617;
  --brand-500:#2563EB; --brand-400:#60A5FA;
  --space-4:16px; --radius-md:12px;

  /* دلالية — الوضع الفاتح */
  --bg-canvas: var(--gray-50);   --bg-surface: #FFFFFF;
  --text-primary: var(--gray-900); --text-secondary: var(--gray-500);
  --action-primary: var(--brand-500); --text-on-action: #FFFFFF;
  --border-default: var(--gray-200);
}

:root[data-theme="dark"] {
  --bg-canvas: var(--gray-950); --bg-surface: #12161F;
  --text-primary: #E8EAED;      --text-secondary: #9AA0A6;
  --action-primary: var(--brand-400); --text-on-action: var(--gray-950);
  --border-default: #2A2F3A;
}
```

لاحظ: `--space-*` و`--radius-*` و`--font-size-*` **لا تُعاد** في الكتلة الداكنة. أي رمز غير لوني يتبدّل مع الوضع هو غالباً خطأ.

## ثوابت Dart

نفس التقسيم، دون أي بناء واجهة — قيم فقط، تُغذّي الثيم لاحقاً.

```dart
// primitives.dart — ثابتة، لا تُقرأ من الشاشات
abstract class P {
  static const gray50 = Color(0xFFF8FAFC);
  static const gray900 = Color(0xFF0F172A);
  static const gray950 = Color(0xFF020617);
  static const brand500 = Color(0xFF2563EB);
  static const brand400 = Color(0xFF60A5FA);
  static const space4 = 16.0;
  static const radiusMd = 12.0;
  static const durationBase = Duration(milliseconds: 200);
}

// semantic.dart — نسختان بنفس الحقول تماماً
class Sem {
  const Sem({required this.bgCanvas, required this.textPrimary, required this.actionPrimary});
  final Color bgCanvas, textPrimary, actionPrimary;

  static const light = Sem(
    bgCanvas: P.gray50, textPrimary: P.gray900, actionPrimary: P.brand500);
  static const dark = Sem(
    bgCanvas: P.gray950, textPrimary: Color(0xFFE8EAED), actionPrimary: P.brand400);
}
```

المهم أن `light` و`dark` لهما **نفس الحقول بالضبط**. أي حقل موجود في أحدهما فقط سيسبب انهياراً بصرياً في الوضع الآخر.

## JSON مشترك بين المنصّات

حين يوجد تطبيق وويب لنفس المنتج، اجعل المصدر ملف JSON واحداً وولّد منه CSS وDart بسكربت بسيط.

```json
{
  "color": { "gray": { "900": "#0F172A" }, "brand": { "500": "#2563EB" } },
  "space": { "4": 16 },
  "semantic": {
    "light": { "text-primary": "{color.gray.900}", "action-primary": "{color.brand.500}" },
    "dark":  { "text-primary": "#E8EAED",          "action-primary": "{color.brand.400}" }
  }
}
```

القاعدة: **مصدر واحد للحقيقة**. ملفان يدويان في منصّتين سينحرفان خلال أسابيع. لا تبدأ بهذا إلا عند وجود منصّتين فعلاً؛ لمنصّة واحدة الملف الأصلي بلغتها يكفي.

## ما يتبدّل وما لا يتبدّل

| الفئة | يتبدّل مع الوضع الليلي |
|---|---|
| ألوان الخلفيات والأسطح | ✅ |
| ألوان النص والحدود | ✅ |
| ألوان الأفعال والحالات (بتشبّع أخفض في الداكن) | ✅ |
| الظلال (تصبح شبه بلا أثر) | ✅ |
| المسافات، radius، أحجام الخط، الأوزان، ارتفاع السطر، مدد الحركة | ❌ |

## فرض منع القيم الخام

- **ويب**: قاعدة stylelint تمنع أي قيمة لون حرفية خارج ملف الرموز (`declaration-property-value-disallowed-list` على `color`/`background`).
- **Dart**: قاعدة lint أو بحث دوري عن `Color(0x` خارج `primitives.dart`.
- **بحث يدوي دوري** قبل كل إصدار عن `#`, `rgb(`, `0xFF`, `px` في مجلد المكوّنات؛ أي نتيجة تُصلَح أو تُسجَّل كدَين.
- إذا احتجت قيمة لا يمثّلها رمز، الحل هو **إضافة رمز**، لا كتابة القيمة.

## أخطاء شائعة

- **الأكثر شيوعاً**: تسمية دلالية بلون (`--blue-button`) بدل دور (`--action-primary`) — تنهار أول ما تتغيّر العلامة.
- إنشاء الطبقة الثالثة (رموز المكوّنات) من اليوم الأول: تضخّم بلا فائدة.
- تكرار تعريف الرموز الأولية داخل كتلة الوضع الداكن، أو جعل رموز المسافات تتبدّل مع الوضع.
- أكثر من 12 رمزاً دلالياً للنص — إن لم تستطع تسمية الفرق فهو غير موجود.
- توليد كل التدرّج آلياً من لون واحد ثم استعماله دون فحص التباين.
- استعمال `primary/secondary` لتسمية المقاسات — هذه للأدوار فقط، والمقاسات `xs…xl`.

## قائمة تحقق

- [ ] لا قيمة لون خام في أي ملف مكوّن (تم البحث فعلياً)
- [ ] كل رمز أولي مُستهلك من الطبقة الدلالية لا من المكوّن
- [ ] الأسماء الدلالية تصف الدور لا اللون
- [ ] الطبقة الأولية غير مكرَّرة داخل كتلة الوضع الداكن
- [ ] `light` و`dark` لهما نفس مجموعة الرموز الدلالية بالضبط
- [ ] المسافات وradius وأحجام الخط لا تتبدّل مع الوضع
- [ ] عدد رموز النص الدلالية ≤ 6 ورموز الأسطح ≤ 5
- [ ] كل رمز دلالي مستخدم فعلاً مرة واحدة على الأقل
- [ ] رموز الحالات (success/danger/warning/info) لها نسخة نص ونسخة خلفية
- [ ] عند وجود منصّتين: مصدر JSON واحد يولّد CSS وDart
- [ ] قاعدة lint أو خطوة فحص تمنع القيم الخام قبل الإصدار
- [ ] كل رمز جديد أُضيف للطبقة الصحيحة لا لأقرب طبقة
