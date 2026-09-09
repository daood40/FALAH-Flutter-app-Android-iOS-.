---
name: web-css-modern
description: CSS الحديث عملياً — Grid وFlex ومتى كل منهما، الوحدات وclamp، الخصائص المخصصة، container queries، ‏:has وis وwhere، الخصائص المنطقية للعربية، ‎@layer، التموضع وسياقات التكديس، والأداء. تُفتح عند ذكر "CSS", "تنسيق", "تخطيط", "grid", "flex", "container query", "has", "layers", "z-index", "logical properties", "rtl css".
---

# CSS الحديث

مسار الويب — ليس Flutter. تركيز على ما صار مدعوماً في كل المتصفحات الحديثة ويلغي حيلاً قديمة.

## Grid مقابل Flex

| السؤال | الجواب |
|---|---|
| أرتّب عناصر في **بُعد واحد** (صف أو عمود) بأحجام يحددها المحتوى | Flex |
| أرتّب في **بُعدين** (صفوف وأعمدة متقاطعة) أو أريد تحكماً في الشبكة | Grid |
| توزيع مسافات بين عناصر شريط أدوات | Flex + `justify-content` |
| بطاقات تملأ العرض وتنزل تلقائياً | Grid + `auto-fit` |
| عنصران فوق بعض في نفس الخلية | Grid (`grid-area: 1/1`) |

```css
/* شبكة بطاقات متجاوبة بلا أي media query */
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(260px, 100%), 1fr));
  gap: 16px;
}
```

`min(260px, 100%)` ضرورية: بدونها يفيض العنصر على شاشة 320px. و`gap` تعمل في Flex أيضاً — لا تستعمل `margin` سالبة بعد اليوم.

قاعدة: `1fr` تعني "حصة من المتبقي" وليست `auto`. العنصر داخل `1fr` لا ينكمش تحت `min-content` إلا بـ `minmax(0, 1fr)` — وهذا سبب فيضان النصوص الطويلة والصور داخل الشبكات.

## الوحدات

| الوحدة | معناها | استعمالها |
|---|---|---|
| `rem` | نسبة لجذر المستند (16px افتراضاً) | أحجام النص والمسافات — الافتراضي |
| `em` | نسبة لخط العنصر نفسه | حشو داخل زر يكبر مع نصه |
| `ch` | عرض الرقم `0` تقريباً | `max-width: 65ch` لعرض سطر مقروء |
| `%` | نسبة للأب | العروض داخل حاويات |
| `vh` / `dvh` / `svh` | ارتفاع النافذة | `dvh` للجوال (يحسب شريط المتصفح) |
| `px` | ثابت | الحدود، ونصف القطر الصغير |

- لا تضع `font-size` بـ `px` على `html` — يكسر تكبير المستخدم للخط.
- طول السطر المقروء: 45–75 حرفاً. للنص العربي استهدف `60–70ch`.
- `clamp(min, preferred, max)` تلغي أغلب media queries للطباعة:

```css
h1 { font-size: clamp(1.75rem, 1.25rem + 2.5vw, 3rem); }
.section { padding-block: clamp(2rem, 6vw, 5rem); }
```

الشرط: الجزء الأوسط يجب أن يحتوي وحدة نسبية (`vw`) وإلا لن يتغيّر، ويُفضّل إضافة `rem` معها ليبقى التكبير يعمل.

## الخصائص المخصصة (custom properties)

```css
:root {
  --space: 8px;
  --radius: 12px;
  --fg: #101418;
  --bg: #ffffff;
}
[data-theme="dark"] {
  --fg: #e8ecf1;
  --bg: #101418;
}
.card { background: var(--bg); color: var(--fg); border-radius: var(--radius); }
```

- تُورَّث ويمكن تجاوزها لكل مكوّن: عرّف `--btn-bg` على `.btn` وغيّرها في `.btn--danger`.
- `var(--x, fallback)` للقيمة الاحتياطية.
- التبديل بين الوضعين يتم بتغيير متغيرات على الجذر فقط، لا بإعادة كتابة القواعد.
- الأداء: تغيير متغيّر يعيد الرسم لكل شجرة تحته؛ لا تحدّثها داخل `scroll` بلا حاجة.

## container queries

الاستجابة الحقيقية للمكوّنات: القياس بعرض **الحاوية** لا النافذة. مكوّن بطاقة في شريط جانبي 320px يجب أن يبدو كبطاقة ضيقة حتى لو كانت الشاشة 1440px.

```css
.card-wrap { container-type: inline-size; container-name: card; }

@container card (min-width: 400px) {
  .card { display: grid; grid-template-columns: 120px 1fr; }
}
```

- `container-type: inline-size` هو الشائع؛ `size` يتطلب ارتفاعاً محدداً ويكسر التدفق غالباً.
- الوحدات `cqi` و`cqw` نسبة لعرض الحاوية.
- لا يمكن لعنصر أن يستعلم عن **نفسه**؛ يحتاج غلافاً.

## ‏:has() و:is() و:where()

```css
/* الأب الذي يحتوي صورة يتغيّر تخطيطه */
.card:has(> img) { grid-template-rows: auto 1fr; }

/* حقل به خطأ */
.field:has(input:invalid:not(:placeholder-shown)) .msg { display: block; }

/* اختصار بلا رفع الخصوصية */
:where(h1, h2, h3) { text-wrap: balance; }
:is(.post, .page) :is(h2, h3) { margin-block-start: 1.5em; }
```

الفرق الحاسم: `:where()` خصوصيتها **صفر** — مثالية لأنماط الأساس (reset/base) لأنها تُتجاوز بسهولة. `:is()` تأخذ خصوصية أقوى وسيط داخلها. `:has()` تأخذ خصوصية أقوى وسيط أيضاً وتعمل صعوداً.

## الخصائص المنطقية — أهم بند للعربية

استخدام `margin-left` في واجهة RTL يعني كتابة كل قاعدة مرتين. الخصائص المنطقية تتبع اتجاه الكتابة تلقائياً.

| فيزيائي | منطقي |
|---|---|
| `margin-left` / `margin-right` | `margin-inline-start` / `margin-inline-end` |
| `padding-top` / `padding-bottom` | `padding-block-start` / `padding-block-end` |
| `left` / `right` | `inset-inline-start` / `inset-inline-end` |
| `text-align: left` | `text-align: start` |
| `border-left` | `border-inline-start` |
| `width` / `height` | `inline-size` / `block-size` |

اختصارات مفيدة: `margin-inline: auto` للتوسيط، `padding-block: 16px` للحشو الرأسي، `inset: 0` بدل الأربعة.

الاستثناءات التي تبقى فيزيائية عمداً: الظل `box-shadow` واتجاه أيقونة السهم — السهم يجب أن **ينقلب** في RTL (`transform: scaleX(-1)`)، لكن أيقونات مثل التشغيل ▶ في الوسائط لا تنقلب.

## ‎@layer

ترتيب الطبقات يحسم التعارض قبل الخصوصية: أي قاعدة في طبقة لاحقة تفوز على أي قاعدة في طبقة سابقة حتى لو كانت خصوصيتها أقل.

```css
@layer reset, base, components, utilities;

@layer components { .btn { background: var(--brand); } }
@layer utilities  { .bg-transparent { background: transparent; } }
```

هذا يلغي الحاجة لـ `!important` في 90% من الحالات. القاعدة غير المُطبَّقة داخل أي طبقة تفوز على كل الطبقات.

## التموضع وسياقات التكديس

`position: sticky` يحتاج ثلاثة شروط معاً وإلا لا يعمل: قيمة `top`/`inset-block-start` محددة، أب لا يملك `overflow: hidden` أو `auto`، وارتفاع الأب أكبر من العنصر.

سياق تكديس جديد يُنشأ عند: `position` غير `static` مع `z-index` رقمي، أو `transform`، `filter`، `opacity < 1`، `will-change`، `contain: paint`، `isolation: isolate`.

النتيجة العملية: `z-index: 9999` داخل بطاقة عليها `transform` **لن** يتجاوز عنصراً بـ `z-index: 1` خارجها. الحل ليس رفع الرقم بل نقل العنصر خارج السياق، أو استخدام `<dialog>` / `popover` التي تُرسم في الطبقة العليا (top layer) وتتجاهل z-index كلياً.

سلّم z-index مقترح ومحدود: `1` محتوى مرفوع، `10` رأس لاصق، `100` قوائم منسدلة، `1000` حوارات، `1100` تنبيهات. أي رقم خارجه علامة مشكلة.

## الظلال ونصف الأقطار

- 3 مستويات ظل كحد أقصى. ظل واقعي = طبقتان: واحدة قريبة ضيقة وأخرى بعيدة ناعمة.
- في الوضع الداكن الظل شبه عديم الأثر؛ افصل الأسطح بـ **إضاءة خلفية** أو حد `1px` بدلاً منه.
- نصف القطر الداخلي = الخارجي − الحشو. بطاقة `radius: 16px` وحشو `8px` تحتاج صورة داخلية `radius: 8px` وإلا ظهرت زوايا مكسورة.

```css
--shadow-1: 0 1px 2px rgb(0 0 0 / .06), 0 1px 3px rgb(0 0 0 / .10);
--shadow-2: 0 4px 8px rgb(0 0 0 / .06), 0 8px 24px rgb(0 0 0 / .10);
```

## الأداء

- حرّك `transform` و`opacity` فقط. `left`, `top`, `width`, `height`, `margin` تسبب إعادة تخطيط (layout) في كل إطار.
- `will-change` تُضاف قبل الحركة وتُزال بعدها؛ تركها دائمة يحجز ذاكرة GPU ويبطئ الصفحة.
- `content-visibility: auto` مع `contain-intrinsic-size` لقوائم طويلة خارج الشاشة يقلّل زمن الرسم الأول بشكل ملموس.
- تجنّب المحدّدات العميقة جداً و`*` مع خصائص مكلفة، لكن الاختناق الحقيقي غالباً الصور والخطوط لا المحددات.
- `@media (prefers-reduced-motion: reduce)` تعطّل الحركات لمن يطلب ذلك — إلزامي.

## أخطاء شائعة

- استعمال `left/right` في مشروع عربي ثم كتابة ملف `rtl.css` مكرر.
- `height: 100vh` على الجوال فتُقص الشاشة بمقدار شريط المتصفح؛ استخدم `dvh`.
- `!important` لحل تعارض كان يُحل بـ `@layer` أو بترتيب المحددات.
- شبكة `1fr` بلا `minmax(0, 1fr)` فتفيض بمحتوى طويل.
- `overflow: hidden` على أب ثم استغراب توقّف `position: sticky`.
- تعريف عشرات المتغيرات بلا نظام، فتصير `--blue-2` بلا معنى.

> قيم اللون والمسافة والتباين: افتح مهارات design-*. التنفيذ في Flutter: flutter-ui-design.

## قائمة تحقق

- [ ] كل الاتجاهات بخصائص منطقية (`inline-start`/`block`)، ولا ملف RTL منفصل
- [ ] Grid للبُعدين وFlex للبُعد الواحد، و`gap` بدل الهوامش اليدوية
- [ ] الشبكات تستخدم `minmax(min(Xpx, 100%), 1fr)` ولا تفيض عند 320px
- [ ] الطباعة بـ `clamp()` مع `rem` داخلها، وطول السطر ≤ 70ch
- [ ] رموز التصميم كلها متغيرات على `:root`، والوضع الداكن تبديل متغيرات فقط
- [ ] استخدمت `@layer` وليس `!important`
- [ ] `:where()` لأنماط الأساس حتى لا ترتفع الخصوصية
- [ ] سلّم z-index محدود ومكتوب، ولا رقم عشوائي مثل 9999
- [ ] الحركات على `transform`/`opacity` فقط، و`prefers-reduced-motion` محترمة
- [ ] `dvh` بدل `vh` في أي ارتفاع ملء الشاشة
- [ ] `will-change` مؤقتة لا دائمة
