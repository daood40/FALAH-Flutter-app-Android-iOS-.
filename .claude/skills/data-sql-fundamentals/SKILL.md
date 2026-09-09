---
name: data-sql-fundamentals
description: SQL عملي على Postgres — الربط والتجميع، CTE، دوال النوافذ، سلوك NULL، تكلفة DISTINCT، وقراءة EXPLAIN. تُفتح عند ذكر "SQL", "استعلام", "جوين", "خطة التنفيذ", "query", "join", "group by", "window function", "CTE", "explain".
---

# SQL عملي على Postgres

مهارة جانب الخادم. كل الأمثلة SQL قابلة للتنفيذ في Postgres 15+ (وهو ما تشغّله Supabase).

> استدعاء هذه الاستعلامات من تطبيق Flutter: افتح مهارة flutter-supabase.

## الترتيب المنطقي للتنفيذ (احفظه، يفسّر أغلب الأخطاء)

`FROM` → `JOIN` → `WHERE` → `GROUP BY` → `HAVING` → `SELECT` → `DISTINCT` → `ORDER BY` → `LIMIT`

نتيجتان مباشرتان: لا تستطيع استعمال الاسم المستعار المعرّف في `SELECT` داخل `WHERE` لأن `WHERE` نُفّذ قبله (لكن `ORDER BY` و`GROUP BY` يقبلانه كامتداد في Postgres). و`WHERE` تُرشّح الصفوف قبل التجميع بينما `HAVING` تُرشّح المجموعات بعده، فأي ترشيح لا يحتاج دالة تجميع يجب أن يكون في `WHERE` — وضعه في `HAVING` يجبر القاعدة على تجميع صفوف سترميها.

## الترشيح والترتيب

```sql
-- الفهرس يُستعمل هنا
select id, title, created_at from posts
where created_at >= now() - interval '30 days'
order by created_at desc limit 20;
-- الفهرس لا يُستعمل: العمود ملفوف بدالة
where date(created_at) = '2026-09-09';
-- الصواب: نطاق نصف مفتوح
where created_at >= '2026-09-09' and created_at < '2026-09-10';
```

قواعد صارمة: لا تكتب دالة على العمود في `WHERE` إن أردت الفهرس — اجعلها على الثابت أو أنشئ فهرساً تعبيرياً. و`ORDER BY` بلا `LIMIT` على جدول كبير فرز كامل، فأضف `LIMIT` دائماً في الواجهات. و`ORDER BY` غير حتمي بلا مفتاح فاصل: أضف `, id desc` بعد أي عمود قد يتكرر وإلا تكرّرت صفوف بين الصفحات. و`ILIKE '%نص%'` بالعربية لا تستفيد من فهرس B-tree إطلاقاً — للبحث الحقيقي استعمل `pg_trgm` أو `tsvector` (مهارة data-postgres-advanced).

## أنواع الربط ومتى كل نوع

| النوع | يُرجع | استعمله عندما |
|---|---|---|
| `INNER JOIN` | المتطابق فقط | تريد ما له مقابل مؤكد |
| `LEFT JOIN` | كل صفوف اليسار + المتطابق أو NULL | كل الطلبات حتى بلا دفعات |
| `FULL JOIN` | الطرفان كاملين | مطابقة مصدرين مستقلين (تسويات) |
| `CROSS JOIN` | الضرب الديكارتي | توليد شبكة (كل يوم × كل فرع) |
| `LATERAL` | استعلام يعتمد على صف اليسار | "أحدث 3 لكل عميل" |

`RIGHT JOIN` نادر الفائدة: اقلب ترتيب الجدولين واستعمل `LEFT`.

الخطأ الأكثر شيوعاً هنا: `LEFT JOIN` ثم شرط على الجدول اليمين داخل `WHERE`. هذا يحوّله إلى `INNER JOIN` صامتاً.

```sql
-- خطأ: يلغي أثر LEFT
from orders o left join payments p on p.order_id = o.id
where p.status = 'paid';
-- صواب: الشرط داخل ON
from orders o left join payments p on p.order_id = o.id and p.status = 'paid';
```

`LATERAL` هو الحل الصحيح لـ "آخر N لكل مجموعة"، وأسرع من النوافذ عندما N صغير ويوجد فهرس مناسب:

```sql
select c.id, c.name, o.id as last_order, o.total
from customers c
left join lateral (
  select id, total from orders where orders.customer_id = c.id
  order by created_at desc limit 1) o on true;
```

## التجميع وHAVING

```sql
select customer_id,
       count(*)                                    as orders_count,
       sum(total_cents)                            as revenue_cents,
       count(*) filter (where status = 'refunded') as refunds
from orders
where created_at >= date_trunc('month', now())
group by customer_id having count(*) >= 3
order by revenue_cents desc;
```

`filter (where ...)` أنظف وأسرع من `sum(case when ... then 1 else 0 end)` وهو معيار SQL. وكل عمود في `SELECT` غير مجمَّع يجب أن يكون في `GROUP BY` إلا إن كان تابعاً وظيفياً للمفتاح الأساسي المذكور (`group by c.id` يكفي لجلب `c.name`). و`count(*)` تعدّ الصفوف بينما `count(col)` تتجاهل NULL و`count(distinct col)` أغلى بكثير. و`sum()` على مجموعة فارغة تُرجع NULL لا صفراً — استعمل `coalesce(sum(x), 0)`.

## الاستعلامات الفرعية وCTE

| الشكل | متى يُفضَّل |
|---|---|
| `IN (select ...)` | قائمة صغيرة، بسيط وواضح |
| `EXISTS (select 1 ...)` | التحقق من الوجود — يتوقف عند أول تطابق |
| `NOT EXISTS` | النفي — **دائماً** بدل `NOT IN` |
| `CTE (WITH)` | خطوة منطقية مسمّاة، أو استعمال متكرر، أو recursive |

قاعدة لا تُخالف: `NOT IN` مع عمود يحتمل NULL يُرجع نتيجة فارغة دائماً، لأن `x NOT IN (1, NULL)` تساوي UNKNOWN. استعمل `NOT EXISTS`.

منذ Postgres 12 صار CTE قابلاً للدمج (inlined) افتراضياً، فلم يعد "جداراً تحسينياً" إلا إن كتبت `MATERIALIZED` صراحة. اكتب `WITH x AS MATERIALIZED (...)` عندما تريد حساب الجزء مرة واحدة فعلاً.

```sql
with recursive tree as (
  select id, parent_id, name, 1 as depth from categories where parent_id is null
  union all
  select c.id, c.parent_id, c.name, t.depth + 1
  from categories c join tree t on c.parent_id = t.id
  where t.depth < 10)         -- حاجز أمان إلزامي ضد الدورات
select * from tree order by depth, name;
```

## دوال النوافذ

النافذة لا تدمج الصفوف — تُبقيها وتضيف حساباً عبرها.

```sql
select order_id, created_at, total_cents,
  row_number() over w                            as seq,
  rank() over (order by total_cents desc)        as rank_by_value,
  sum(total_cents) over (order by created_at
        rows between unbounded preceding and current row) as running_total,
  lag(total_cents) over w                        as prev_total,
  total_cents - lag(total_cents) over w          as delta,
  avg(total_cents) over (order by created_at
        rows between 6 preceding and current row) as ma7
from orders
window w as (partition by customer_id order by created_at);
```

`row_number` يعطي ترقيماً فريداً، `rank` يترك فجوات عند التعادل، و`dense_rank` لا يترك فجوات. و`rows` تعدّ صفوفاً فعلية بينما `range` تعدّ قيماً متساوية في `ORDER BY`: في المجموع التراكمي اليومي مع تواريخ مكرّرة سيجمع `range` كل صفوف اليوم دفعة واحدة، وهو الافتراضي — لذلك اكتب `rows` صراحة. ولا تستطيع وضع نافذة في `WHERE`؛ لفّها في CTE أو استعلام فرعي ثم رشّح، وهذا نمط "الأول لكل مجموعة":

```sql
select * from (select *, row_number() over
  (partition by customer_id order by created_at desc) rn from orders) t where rn = 1;
```

## NULL وسلوكه المفاجئ

| التعبير | النتيجة |
|---|---|
| `NULL = NULL` و`NULL <> 1` | NULL لا true — لا يظهر الصف في WHERE |
| `x IS NOT DISTINCT FROM y` | true عندما الاثنان NULL |
| `'a' \|\| NULL` | NULL — استعمل `concat()` التي تتجاهله |
| `count(col)` / `sum` على لا شيء | يتجاهل NULL / يُرجع NULL |
| `UNIQUE` مع NULL | يسمح بتكرار NULL (إلا `nulls not distinct` في PG15+) |
| `ORDER BY` تصاعدي | NULL في النهاية افتراضياً؛ تنازلي في البداية |

الخطأ الأكثر شيوعاً: `where status <> 'archived'` تُسقط الصفوف التي فيها `status IS NULL`. اكتب `where status is distinct from 'archived'`.

## DISTINCT وتكلفته

`DISTINCT` يعني فرزاً أو hash لكل النتيجة. في 90% من الحالات وجوده يعني أن الربط ضاعف الصفوف — أصلح الربط لا العرض.
```sql
-- بدل distinct على ربط مضاعِف
select c.* from customers c
where exists (select 1 from orders o where o.customer_id = c.id);
-- distinct on: صف واحد لكل مفتاح، امتداد Postgres مفيد جداً
select distinct on (customer_id) customer_id, id, total_cents
from orders order by customer_id, created_at desc;
```

`distinct on` يشترط أن يبدأ `ORDER BY` بنفس أعمدته.

## قراءة EXPLAIN

`EXPLAIN` يعرض الخطة المقدَّرة. `EXPLAIN (ANALYZE, BUFFERS)` ينفّذ فعلاً ويعطي أرقاماً حقيقية — استعمل الثاني دائماً عند التشخيص (وضعه داخل `BEGIN; ... ROLLBACK;` إن كان الاستعلام يكتب).

```sql
explain (analyze, buffers, format text)
select ... ;
```

ما تقرؤه:

| العنصر | معناه | متى يكون مشكلة |
|---|---|---|
| `Seq Scan` | مسح كامل | جدول > 10k صف مع ترشيح انتقائي = فهرس ناقص |
| `Index Scan` / `Index Only Scan` | فهرس ثم جلب / من الفهرس وحده | جيد / ممتاز (يتطلب VACUUM حديثاً) |
| `Bitmap Heap Scan` | فهرس لنطاق واسع | طبيعي عند 1–10% من الجدول |
| `Nested Loop` | حلقة | سيئ إن كان الجانب الداخلي كبيراً |
| `Hash Join` | بناء جدول hash | جيد للأحجام المتوسطة والكبيرة |
| `rows=1000 ... actual rows=900000` | تقدير خاطئ | السبب الجذري لأغلب الخطط السيئة |
| `Sort Method: external merge Disk:` | فرز على القرص | ارفع `work_mem` أو أضف فهرس ترتيب |

خطوات التشخيص بالترتيب: ابحث أولاً عن أكبر فجوة بين `rows` المقدَّر و`actual rows` — ابدأ من هناك لا من العقدة الأبطأ. إن كانت الفجوة كبيرة شغّل `ANALYZE table_name;`، وإن استمرت فقد تحتاج `create statistics` للأعمدة المترابطة. تذكّر أن `actual time` تراكمي ومضروب في `loops`، فالزمن الحقيقي للعقدة = `actual time` × `loops`. و`Buffers: shared read=` عالٍ يعني قراءة من القرص بينما `hit=` من الذاكرة. و`Rows Removed by Filter` كبير يعني أن الفهرس يجلب أكثر مما يلزم، ففكّر في فهرس مركّب أو جزئي.

## قائمة تحقق

- [ ] كل `ORDER BY` في واجهة معه `LIMIT` ومفتاح فاصل ثابت (`, id`)
- [ ] لا دالة على العمود داخل `WHERE`؛ التاريخ بنطاق نصف مفتوح
- [ ] شروط الجدول اليمين في `LEFT JOIN` موضوعة داخل `ON` لا `WHERE`
- [ ] لا وجود لـ `NOT IN` على عمود يحتمل NULL — استُبدل بـ `NOT EXISTS`
- [ ] `count`/`sum` ملفوفة بـ `coalesce` حيث تُعرض، و`filter (where ...)` بدل `case when`
- [ ] كل `DISTINCT` مبرَّر؛ وإلا فالسبب ربط مضاعِف تم إصلاحه
- [ ] النوافذ تستعمل `rows` صراحة عند المجاميع التراكمية، وCTE التكراري فيه حاجز عمق
- [ ] `EXPLAIN (ANALYZE, BUFFERS)` مُشغَّل على كل استعلام يخدم شاشة رئيسية
- [ ] لا `Seq Scan` على جدول كبير في المسارات الساخنة
- [ ] فجوة التقدير مقابل الفعلي أقل من 10× في العقد الرئيسية
