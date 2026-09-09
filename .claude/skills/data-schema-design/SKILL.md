---
name: data-schema-design
description: تصميم مخطط قاعدة البيانات — التطبيع، UUID مقابل bigint، المفاتيح الخارجية، القيود، الأنواع الصحيحة وتخزين المال، الحذف الناعم، والتدقيق. تُفتح عند ذكر "تصميم جدول", "مخطط", "علاقات", "قيود", "schema", "table design", "foreign key", "normalization", "constraints".
---

# تصميم المخطط في Postgres

القاعدة الحاكمة: المخطط هو آخر خط دفاع. التطبيق يُعاد كتابته، والبيانات الفاسدة تبقى للأبد.

## التطبيع حتى الشكل الثالث

| الشكل | الشرط | المخالفة الشائعة |
|---|---|---|
| 1NF | لا قيم مركّبة في خلية | `phones text` فيها "091..,092.." |
| 2NF | كل عمود يعتمد على المفتاح كاملاً | في جدول ربط، عمود يعتمد على نصف المفتاح |
| 3NF | لا عمود يعتمد على عمود غير مفتاح | `city` و`country` معاً في نفس الجدول |

خالف التطبيع عمداً في ثلاث حالات فقط، وكل واحدة لها شرط:

1. **لقطة تاريخية**: سعر المنتج وقت الشراء يُنسخ إلى `order_items.unit_price_cents`. هذه ليست مخالفة أصلاً — السعر وقت البيع حقيقة مختلفة عن السعر الحالي. انسخ كذلك اسم المنتج ورقم الضريبة.
2. **عدّاد مشتق** (`posts.comments_count`): فقط إن كان العدّ الحيّ ظهر فعلاً في `EXPLAIN ANALYZE` كتكلفة. حدّثه بـ trigger، لا من التطبيق، وأضف مهمة تسوية دورية.
3. **حقل JSONB لبيانات متغيّرة الشكل**: خصائص منتجات مختلفة الفئات. لا تضع فيه ما تُرشّح أو تربط عليه كثيراً.

الخطأ الأكثر شيوعاً هنا: إزالة التطبيع "من أجل الأداء" قبل قياس أي شيء. لا تفعل قبل أن ترى الرقم.

## المفاتيح الأساسية: UUID مقابل bigint

| المعيار | `bigint generated always as identity` | `uuid` |
|---|---|---|
| الحجم | 8 بايت | 16 بايت |
| توليده من العميل | لا | نعم — مهم للعمل بلا اتصال |
| تسريب المعلومات | يكشف الحجم والتسلسل | لا يكشف |
| تجزئة الفهرس | ممتازة (تسلسلي) | سيئة مع `gen_random_uuid()` v4 |
| الحجم على القرص لفهرس 10M صف | ≈ 220MB | ≈ 400MB وأكثر بسبب التجزئة |

القرار العملي لتطبيق Supabase: الجداول المرتبطة بـ `auth.users` تستعمل `uuid` إجباراً (لأن `auth.uid()` نفسه uuid)، والجداول التي يظهر معرّفها في URL تستعمل `uuid` لمنع التخمين والعدّ، وجداول السجلات الضخمة الداخلية (events، logs) تستعمل `bigint identity` لأنه أرخص وأسرع. ولا تستعمل `serial` القديم — `generated always as identity` هو المعيار ويمنع الإدراج اليدوي بالخطأ. وإن اخترت uuid وأزعجتك التجزئة فولّده بترتيب زمني (UUIDv7) من التطبيق بدل v4.

```sql
create table orders (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  created_at  timestamptz not null default now()
);
```

`gen_random_uuid()` مدمجة في Postgres 13+ ولا تحتاج امتداد `uuid-ossp`.

## المفاتيح الخارجية وسلوك الحذف

| السلوك | ماذا يحدث | استعمله لـ |
|---|---|---|
| `on delete cascade` | يُحذف الابن مع الأب | بيانات ملك للأب حصراً: عناصر الطلب، إعدادات المستخدم |
| `on delete restrict` | يمنع الحذف | الافتراضي الآمن للمراجع المهمة |
| `on delete set null` | يُفرَّغ المرجع | مرجع اختياري: `assigned_to` |
| `on delete no action` | مثل restrict لكن قابل للتأجيل | مع `deferrable initially deferred` |

**كل** عمود مفتاح خارجي يحتاج فهرساً منفصلاً: Postgres يُنشئ فهرساً للمفتاح الأساسي تلقائياً لكنه **لا** يُنشئه للمفتاح الخارجي، وبدونه يصبح كل `DELETE` على الأب مسحاً كاملاً للابن. والفواتير والمدفوعات لا تُحذف بالتتالي أبداً — `restrict` ثم أرشفة. ولا تعتمد على `cascade` لحذف حساب مستخدم بالكامل؛ اكتب دالة حذف صريحة تعرف الترتيب والملفات في Storage.

## القيود كخط دفاع أول

```sql
create table products (
  id            bigint generated always as identity primary key,
  sku           text   not null,
  name_ar       text   not null check (length(btrim(name_ar)) between 1 and 200),
  price_cents   integer not null check (price_cents >= 0),
  discount_pct  smallint not null default 0 check (discount_pct between 0 and 90),
  status        text   not null default 'draft'
                 check (status in ('draft','active','archived')),
  stock         integer not null default 0 check (stock >= 0),
  created_at    timestamptz not null default now(),
  constraint products_sku_uniq unique (sku)
);
```

`NOT NULL` هو القيد الأرخص والأعلى عائداً: اجعله الافتراضي في تصميمك وبرّر كل استثناء. و`CHECK` على النطاقات (نسبة بين 0 و100، كمية ≥ 0، تاريخ نهاية بعد البداية). و`UNIQUE` جزئي للحالات المشروطة:

```sql
-- بريد فريد بين الحسابات النشطة فقط
create unique index users_email_active_uniq
  on users (lower(email)) where deleted_at is null;
```

والتداخل الزمني يُمنع بـ `EXCLUDE` مع امتداد `btree_gist`:

```sql
create extension if not exists btree_gist;
alter table bookings add constraint no_overlap
  exclude using gist (room_id with =, during with &&);
```

التحقق في التطبيق **إضافة** للقيد لا بديل عنه: رسالة خطأ جميلة في الواجهة + قيد صارم في القاعدة.

## الأنواع الصحيحة

| الحاجة | النوع الصحيح | النوع الخاطئ الشائع |
|---|---|---|
| لحظة زمنية | `timestamptz` | `timestamp` بلا منطقة، `text` |
| تاريخ ميلاد / يوم عطلة | `date` | `timestamptz` |
| مال | `integer`/`bigint` بأصغر وحدة، أو `numeric(12,2)` | `float`, `real`, `money` |
| نسبة | `numeric(5,2)` أو `smallint` | `float` |
| نص | `text` | `varchar(n)` بلا سبب |
| صح/خطأ | `boolean` | `smallint 0/1` |
| قائمة قصيرة ثابتة | جدول مرجعي أو `enum` | `text` حر |
| بيانات متغيّرة الشكل | `jsonb` | `json` (لا يُفهرس) |
| رقم هاتف ليبي | `text` + `check` على النمط | `bigint` (يُسقط الصفر البادئ) |

`timestamptz` دائماً: Postgres يخزّنه UTC ويحوّل عند القراءة، بينما `timestamp` بلا منطقة يجعل فرق التوقيت الليبي (UTC+2 بلا توقيت صيفي) خطأ صامتاً في التقارير. ولا تخزّن مالاً في `float` أبداً — `0.1 + 0.2 <> 0.3` في العائم الثنائي، وستكتشف الفارق في تسوية آخر الشهر. و`varchar(n)` لا يعطي أداءً أفضل من `text`؛ استعمل `text` + `check (length(x) <= n)` لأن تغيير الـ check أسهل من تغيير النوع.

## تخزين المال كأعداد صحيحة

القرار الافتراضي: `amount_cents bigint` بأصغر وحدة، مع عمود عملة.

```sql
create table payments (
  id           bigint generated always as identity primary key,
  order_id     bigint not null references orders(id) on delete restrict,
  amount_minor bigint not null check (amount_minor > 0),  -- بالدرهم الليبي (1/1000 دينار)
  currency     char(3) not null default 'LYD' check (currency ~ '^[A-Z]{3}$'),
  created_at   timestamptz not null default now()
);
```

عدد الخانات العشرية يختلف بالعملة: LYD وTND ودينار الكويت = 3 خانات، USD وEUR = 2، JPY = 0 — خزّن العدد الصحيح مع رمز العملة ودع طبقة العرض تقسم. و`bigint` لا `integer`: الأخير يقف عند ~2.1 مليار، أي 2.1 مليون دينار بالدرهم فقط. وإن احتجت حسابات مالية معقّدة داخل SQL (فوائد، نِسب) استعمل `numeric` ثم قرّب مرة واحدة في النهاية. والدفع عند الاستلام يعني حالات متعددة — `pending`, `collected`, `settled`, `failed` — مثّلها كسجلّ حالات لا كعمود boolean واحد.

## الجداول المرجعية مقابل ENUM

| | `enum` | جدول مرجعي |
|---|---|---|
| إضافة قيمة | `alter type ... add value` — لا يعمل داخل معاملة في نسخ قديمة | `insert` عادي |
| حذف قيمة | مستحيل عملياً | `delete` |
| ترجمة عربية للقيمة | لا مكان لها | عمود `label_ar` |
| ترتيب عرض | ترتيب التعريف | عمود `sort_order` |
| التكلفة | 4 بايت | مفتاح خارجي + ربط |

القاعدة: `enum` للقيم التي تعرفها الشيفرة نفسها ولن تتغيّر (`'draft','active','archived'`). جدول مرجعي لأي قائمة يديرها المستخدم أو تحتاج تسمية عربية معروضة (المدن، فئات المنتجات، أسباب الإلغاء). البديل الأبسط من الاثنين: `text` + `check in (...)` — سهل التعديل بهجرة واحدة ويقرأه أي عميل بلا تحويل.

## الحذف الناعم ومشاكله

`deleted_at timestamptz` بدل `DELETE`. مشاكله حقيقية:

1. كل استعلام يجب أن يضيف `where deleted_at is null` — نسيان واحد يسرّب بيانات محذوفة.
2. قيود `UNIQUE` تنكسر: لا يمكن إعادة استعمال بريد محذوف. الحل فهرس فريد جزئي (أعلاه).
3. المفاتيح الخارجية لا تعرف الحذف الناعم — أب "محذوف" يبقى مرجعاً صالحاً.
4. لا يفي بطلب حذف حقيقي للبيانات الشخصية.

الحلول: أنشئ `view` تُخفي المحذوف واجعله سطح القراءة الافتراضي (`create view active_posts as select * from posts where deleted_at is null;`)، وفي Supabase أضف الشرط داخل سياسة RLS نفسها حتى لا يعتمد على انضباط الاستعلامات، واجعل مهمة pg_cron تحذف نهائياً ما مضى عليه 30 يوماً.

## التدقيق

```sql
create table posts (
  id         bigint generated always as identity primary key,
  ...
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid references auth.users(id),
  updated_by uuid references auth.users(id)
);

create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end $$;

create trigger posts_set_updated_at
  before update on posts
  for each row execute function set_updated_at();
```

لا تثق بـ `updated_at` القادم من العميل — اضبطه بـ trigger دائماً. ولتاريخ التغييرات الكامل استعمل جدول `audit_log(table_name, row_id, action, old_row jsonb, new_row jsonb, actor uuid, at timestamptz)` يُملأ بـ trigger عام، واحذف منه ما يزيد على مدة الاحتفاظ المقرّرة. ولا تكتب كلمات مرور أو رموزاً في سجل التدقيق.

## قائمة تحقق

- [ ] كل جدول له مفتاح أساسي، والنوع مبرَّر (uuid للمعروض، bigint للسجلات)
- [ ] كل مفتاح خارجي له فهرس منفصل وسلوك حذف مُختار عمداً
- [ ] الافتراضي `not null`؛ كل عمود قابل لـ NULL له سبب
- [ ] كل عمود نطاقي عليه `check` بحدود رقمية حقيقية
- [ ] لا `timestamp` بلا منطقة في المخطط كله — `timestamptz` فقط
- [ ] المال بعدد صحيح بأصغر وحدة + عمود عملة، ولا وجود لـ float
- [ ] `text` بدل `varchar(n)`، مع `check` على الطول عند اللزوم
- [ ] القوائم القابلة للتغيير جداول مرجعية لا enum
- [ ] الحذف الناعم مصحوب بفهرس فريد جزئي وview أو سياسة تُخفي المحذوف
- [ ] `created_at`/`updated_at` موجودان، و`updated_at` يُضبط بـ trigger
- [ ] لا لقطة تاريخية ناقصة: السعر والاسم منسوخان في سطور الطلب
- [ ] كل إزالة تطبيع مدعومة برقم من `EXPLAIN ANALYZE`
