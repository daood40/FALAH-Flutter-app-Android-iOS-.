---
name: web-typescript
description: TypeScript عملي للويب — الإعداد الصارم وما يمنعه، type مقابل interface، الاتحادات المميّزة وحراس الأنواع، unknown بدل any، الأنواع المشتقّة والمساعدة، وأنواع استجابات الخادم مع التحقق وقت التشغيل بـ Zod. تُفتح عند ذكر "TypeScript", "تايب سكربت", "أنواع", "strict", "type", "interface", "generics", "zod", "type guard", "any", "unknown".
---

# TypeScript عملي

مسار الويب — ليس Flutter. الهدف ليس إرضاء المدقّق، بل **جعل الحالات المستحيلة غير قابلة للتمثيل** وتحويل أخطاء وقت التشغيل إلى أخطاء بناء.

## الإعداد الصارم وما يمنعه فعلاً

```jsonc
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "verbatimModuleSyntax": true,
    "target": "ES2022",
    "moduleResolution": "bundler",
    "skipLibCheck": true
  }
}
```

| الخيار | يمنع فعلياً |
|---|---|
| `strictNullChecks` (ضمن strict) | `Cannot read properties of undefined` — أكثر خطأ في JS |
| `noImplicitAny` (ضمن strict) | معاملات بلا نوع تتسرّب كـ `any` عبر المشروع |
| `noUncheckedIndexedAccess` | `arr[10]` يُعامَل كـ `T` وهو `undefined` فعلاً |
| `exactOptionalPropertyTypes` | الخلط بين "غائب" و"موجود بقيمة undefined" |
| `noFallthroughCasesInSwitch` | نسيان `break` |

فعّل `strict` من اليوم الأول. تفعيله على مشروع قائم بـ 400 خطأ يعني أنه لن يُفعّل أبداً. `skipLibCheck: true` مقبول ومفيد — لا تدقّق أنواع مكتبات الطرف الثالث.

## type مقابل interface

| استعمل `interface` | استعمل `type` |
|---|---|
| شكل كائن سيُوسَّع (`extends`) | اتحادات (`A | B`) |
| واجهة عامة لمكتبة (رسائل خطأ أوضح) | أنواع مشتقّة وشرطية ومعيّنة |
| دمج تصريحي مطلوب (نادر) | الاسم المستعار لأي نوع بدائي أو صف |

القاعدة العملية: `interface` للكائنات، `type` لكل شيء آخر. لا تخلط الأسلوبين في نفس الملف بلا سبب، والاتساق أهم من الاختيار نفسه.

## الاتحادات المميّزة وحراس الأنواع

أقوى نمط في TypeScript. حقل حرفي واحد يميّز الأشكال، فيضيّق المترجم النوع تلقائياً.

```ts
type Result<T> =
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; message: string };

function render(r: Result<Order[]>) {
  switch (r.status) {
    case "loading": return spinner();
    case "success": return list(r.data);        // data متاحة هنا فقط
    case "error":   return alert(r.message);
    default: {
      const _never: never = r;                   // فحص الشمولية
      return _never;
    }
  }
}
```

`const _never: never = r` هو **فحص الشمولية**: إضافة حالة رابعة لاحقاً تكسر البناء هنا وتجبرك على معالجتها. هذا الخط وحده يمنع فئة كاملة من الأخطاء.

هذا يلغي النمط الخاطئ `{ loading: boolean; data?: T; error?: string }` الذي يسمح بـ `loading && error` معاً.

حارس النوع المخصّص (`function isOrder(v: unknown): v is Order`) يعِد ولا يتحقق: المترجم يصدّقك. إن كان الفحص داخله ناقصاً فقد كذبت على المترجم — لذلك التحقق الحقيقي للبيانات الخارجية يكون بمكتبة مخطط لا بحارس يدوي.

## unknown بدل any

`any` تُطفئ فحص الأنواع وتنتشر: كل قيمة مشتقّة منها تصير `any` أيضاً. `unknown` تقول "لا أعرف بعد" وتُجبرك على التضييق قبل الاستعمال.

```ts
function handle(e: unknown) {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  return "حدث خطأ غير متوقع";
}
```

المعامل `catch (e)` نوعه `unknown` تحت `strict`، وهذا صحيح: الخطأ الملقى قد يكون أي شيء. استعمل `any` فقط داخل ملفات تعريف مؤقتة مع تعليق يشرح السبب، وفعّل قاعدة ESLint `no-explicit-any`.

## الأنواع المشتقّة

لا تكرّر النوع — اشتقّه. التكرار يعني أن تعديلاً واحداً يترك نسخة قديمة صامتة.

```ts
const ROLES = ["admin", "editor", "viewer"] as const;
type Role = typeof ROLES[number];              // "admin" | "editor" | "viewer"

type User = { id: string; name: string; role: Role; createdAt: string };
type PublicUser = Omit<User, "createdAt">;
type UserDraft  = Pick<User, "name" | "role">;
type Props = React.ComponentProps<typeof Button>;
type Row = Awaited<ReturnType<typeof fetchRows>>[number];
```

`as const` هي الأداة الأهم هنا: تحوّل المصفوفة إلى ثوابت حرفية بدل `string[]`.

## الأنواع المساعدة الشائعة

| النوع | الاستعمال |
|---|---|
| `Partial<T>` / `Required<T>` | تحديث جزئي / فرض الاكتمال |
| `Pick<T, K>` / `Omit<T, K>` | اقتطاع حقول |
| `Record<K, V>` | خرائط: `Record<Role, string[]>` |
| `Readonly<T>` | منع التعديل |
| `NonNullable<T>` | إزالة `null | undefined` |
| `ReturnType<F>` / `Parameters<F>` | اشتقاق من الدوال |
| `Awaited<T>` | فك `Promise` |

`Record` مع اتحاد حرفي مفيدة جداً: `Record<Role, Permission[]>` تجبرك على تغطية كل دور، فإضافة دور جديد تكسر البناء حتى تعرّف صلاحياته.

## أنواع استجابات الخادم — ولماذا النوع وحده لا يكفي

هذا أخطر سوء فهم في TypeScript:

```ts
const data = await res.json() as Order[];   // كذبة
```

الأنواع تُمحى بالكامل عند البناء. `as` **لا تفحص شيئاً** وقت التشغيل. إن غيّر الخادم حقلاً أو أعاد `null`، سينفجر الكود في مكان بعيد عن السبب، والنوع سيقول إن كل شيء سليم.

الحد الفاصل: كل بيانات تعبر حدود التطبيق (استجابة API، `localStorage`، معاملات العنوان، متغيّرات البيئة، رسائل webhook) **غير موثوقة** ويجب التحقق منها وقت التشغيل.

```ts
import { z } from "zod";

const OrderSchema = z.object({
  id: z.string().uuid(),
  total: z.number().nonnegative(),
  status: z.enum(["pending", "paid", "shipped"]),
  createdAt: z.string().datetime(),
  note: z.string().optional(),
});
type Order = z.infer<typeof OrderSchema>;      // النوع مشتق من المخطط

const parsed = OrderSchema.array().safeParse(await res.json());
if (!parsed.success) {
  report(parsed.error);
  throw new Error("استجابة غير متوقعة من الخادم");
}
const orders = parsed.data;                    // مضمون شكلاً ونوعاً
```

قواعد:

- **مصدر واحد**: عرّف المخطط ثم اشتقّ النوع بـ `z.infer`. لا تكتب `interface` موازياً يدوياً.
- استعمل `safeParse` في مسارات الواجهة (تريد رسالة لا انهياراً)، و`parse` في الحدود الداخلية.
- تحقّق من متغيّرات البيئة عند الإقلاع بمخطط واحد؛ الفشل المبكر أرخص من `undefined` في الإنتاج.
- نفس المخطط يخدم تحقق النموذج على العميل والتحقق على الخادم — لا تكرّر القواعد.
- إن كان مصدر البيانات Supabase، ولّد الأنواع من المخطط بأداتها بدل كتابتها يدوياً، وتحقّق وقت التشغيل فقط عند الحدود غير المضمونة.

## أخطاء شائعة

- `as` بدل التحقق: تأكيد النوع يُسكِت المترجم ولا يمنع شيئاً.
- `any` واحدة تنتشر عبر عشرات الملفات.
- `@ts-ignore` بدل `@ts-expect-error` — الثانية تكسر البناء عندما يُصلَح الخطأ فلا تُنسى.
- `!` (non-null assertion) في كل مكان بدل فحص فعلي.
- كتابة `interface` يدوياً بجانب مخطط Zod ثم انحرافهما.
- `strict: false` لتسريع البداية، ثم استحالة تفعيله لاحقاً.
- أنواع عامة (generics) معقّدة لحل مشكلة تُحل باتحاد بسيط.
- الاعتماد على `Object.keys` الذي يعيد `string[]` لا مفاتيح النوع.

> أنواع Dart وFlutter موضوع مختلف؛ افتح flutter-code-quality.

## قائمة تحقق

- [ ] `strict: true` مفعّل مع `noUncheckedIndexedAccess`
- [ ] لا `any` صريحة خارج ملفات تعريف مبرَّرة بتعليق
- [ ] كل بيانات خارجية (API، تخزين، عنوان، بيئة) تمر بمخطط Zod
- [ ] الأنواع مشتقّة من المخططات بـ `z.infer` لا مكتوبة مرتين
- [ ] حالات الواجهة اتحاد مميّز لا أعلام منطقية متعددة
- [ ] كل `switch` على اتحاد فيه فحص شمولية بـ `never`
- [ ] الثوابت بـ `as const` والأنواع مشتقّة منها
- [ ] `unknown` في معالجات الأخطاء لا `any`
- [ ] `@ts-expect-error` بدل `@ts-ignore` عند الضرورة
- [ ] لا `!` لتجاوز فحص null بلا مبرر
- [ ] `tsc --noEmit` جزء من التحقق في CI ويمنع الدمج عند الفشل
