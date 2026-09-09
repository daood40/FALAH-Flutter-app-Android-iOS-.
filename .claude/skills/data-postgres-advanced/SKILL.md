---
name: data-postgres-advanced
description: Postgres المتقدّم — أنواع الفهارس والمركّبة والجزئية، JSONB، البحث النصي والعربية، pg_trgm، المشغّلات، SECURITY DEFINER، العزل والأقفال، وVACUUM. تُفتح عند ذكر "فهرس", "أداء قاعدة البيانات", "بحث نصي", "قفل", "index", "gin", "jsonb", "trigger", "vacuum", "isolation".
---

# Postgres المتقدّم

كل ما هنا SQL على الخادم. النسخة المرجعية Postgres 15+ كما في Supabase.

## أنواع الفهارس

| النوع | يخدم | مثال |
|---|---|---|
| B-tree (الافتراضي) | `=`, `<`, `>`, `between`, `like 'abc%'`, `order by` | `created_at` |
| GIN | الاحتواء داخل قيمة مركّبة: jsonb، مصفوفات، tsvector، trigram | `tags @> '["ar"]'` |
| GiST | النطاقات، الهندسة، التشابه، قيود EXCLUDE | حجز بلا تداخل |
| BRIN | جداول ضخمة مرتّبة طبيعياً بالزمن | أحداث 500M صف |
| HNSW (pgvector) | أقرب الجيران للمتجهات | بحث دلالي |

أحجام تقريبية: GIN على نص أكبر 3–10× من B-tree على نفس العمود وبناؤه أبطأ، لكن استعلامه أسرع بكثير. BRIN أصغر بمئات المرات لكنه مفيد فقط عند ارتباط فيزيائي عالٍ. `hnsw` يتطلب تطابق دالة المسافة بين الفهرس والاستعلام (`vector_cosine_ops` مع `<=>`) وإلا لن يُستعمل.

## الفهارس المركّبة والجزئية

قاعدة البادئة اليسرى: فهرس على `(a, b, c)` يخدم `a`، و`a,b`، و`a,b,c` — ولا يخدم `b` وحده. والترتيب: أعمدة المساواة `=` أولاً (الأعلى انتقائية أولاً) ثم عمود النطاق أو الترتيب أخيراً؛ وضع عمود النطاق في المنتصف يوقف استعمال ما بعده.

```sql
-- where tenant_id=$1 and status='open' order by created_at desc limit 20
create index orders_tenant_status_created_idx on orders (tenant_id, status, created_at desc);
-- INCLUDE يحقق Index Only Scan لأعمدة تُقرأ ولا تُرشَّح
create index orders_lookup_idx on orders (tenant_id, id) include (total_minor, status);
-- جزئي: أصغر وأسرع وأرخص صيانة
create index orders_open_idx on orders (created_at desc) where status = 'open';
create index posts_live_idx on posts (author_id, created_at desc) where deleted_at is null;
```

شرط استعمال الفهرس الجزئي: شرط الاستعلام يطابق شرط الفهرس أو يكون أضيق بشكل يستطيع المخطِّط إثباته — `status = 'open'` يطابق، أما `status <> 'closed'` فلا. وفهارس لا تُنشأ: على عمود boolean بتوزيع 50/50، أو عمود بأقل من 3 قيم، أو جدول أقل من 1000 صف. كل فهرس يبطّئ الكتابة ويستهلك مساحة. راقب غير المستعمل:
```sql
select relname, indexrelname, idx_scan, pg_size_pretty(pg_relation_size(indexrelid))
from pg_stat_user_indexes
where idx_scan=0 and indexrelid not in (select conindid from pg_constraint);
```

## JSONB

```sql
select * from products where attrs @> '{"color":"red"}';            -- احتواء
select * from products where attrs ? 'warranty';                     -- وجود مفتاح
select attrs->>'color', (attrs->>'weight_g')::int from products;     -- نص / رقم
select * from products where attrs #>> '{dims,width}' = '30';        -- مسار
select * from products, jsonb_array_elements_text(attrs->'tags') t;  -- تفكيك
create index products_attrs_gin on products using gin (attrs);                -- عام
create index products_attrs_gin on products using gin (attrs jsonb_path_ops); -- @> فقط، أصغر ~الثلث
create index products_color_idx on products ((attrs->>'color'));              -- مفتاح ساخن
```

`jsonb` لا `json` — الأخير يخزّن النص الخام ولا يُفهرس. و`->` يُرجع jsonb بينما `->>` يُرجع text، فـ `attrs->'n' = '5'` تختلف عن `attrs->>'n' = '5'`. ولا قيود NOT NULL أو CHECK داخل JSONB إلا بكتابتها: `check (jsonb_typeof(attrs->'tags') = 'array')`. والخطأ الأكثر شيوعاً استعمال JSONB ملاذاً من تصميم المخطط — إن كانت المفاتيح ثابتة معروفة فهي أعمدة، خصوصاً ما تربط عليه أو ترتّب به.

## البحث النصي الكامل والعربية

Postgres لا يملك مُحلّلاً للعربية في تهيئات البحث المدمجة، فستستعمل `simple` — يقسّم على الفراغ ويحوّل لحروف صغيرة بلا اشتقاق. النتيجة العملية: "الكتاب" و"كتاب" و"كتب" كلمات مختلفة تماماً، والبحث بالجذر لن يعمل بلا عمل إضافي.

```sql
create or replace function ar_normalize(t text) returns text
language sql immutable strict as $$
  select translate(regexp_replace(t, '[ً-ْـ]', '', 'g'), 'أإآىة', 'ااايه')
$$;
alter table posts add column search_vec tsvector generated always as (
  to_tsvector('simple', ar_normalize(coalesce(title,'') || ' ' || coalesce(body,'')))
) stored;
create index posts_search_idx on posts using gin (search_vec);

select id, title, ts_rank(search_vec, q) rank
from posts, websearch_to_tsquery('simple', ar_normalize('طرابلس شحن')) q
where search_vec @@ q order by rank desc limit 20;
```

العمود المولَّد `stored` أفضل من trigger لأنه لا يمكن أن يفقد التزامن. و`websearch_to_tsquery` يقبل مدخل المستخدم الحر بأمان، بينما `to_tsquery` يرمي خطأ على مدخل غير صالح — لا تُمرّر له نص المستخدم مباشرة. والتطبيع (حذف التشكيل، أ/إ/آ → ا، ى → ي، ة → ه، حذف التطويل) يجب أن يُطبَّق في الفهرسة **وفي الاستعلام** معاً، ودالته `IMMUTABLE` وإلا رفض العمود المولَّد استعمالها. وللبحث الجزئي داخل الكلمة أو أقل من 3 حروف، FTS ليست الأداة.

## pg_trgm

```sql
create index products_name_trgm on products using gin (ar_normalize(name_ar) gin_trgm_ops);
set pg_trgm.similarity_threshold = 0.25;   -- الافتراضي 0.3
select name_ar, similarity(ar_normalize(name_ar), ar_normalize($1)) s
from products
where ar_normalize(name_ar) % ar_normalize($1)     -- يستعمل الفهرس
order by s desc limit 10;
```

`gin_trgm_ops` هو ما يجعل `ILIKE '%نص%'` قابلاً للفهرسة، وهذا سبب وجوده الأول. القسمة العملية: FTS للنصوص الطويلة، وtrigram للأسماء القصيرة والبحث أثناء الكتابة وتصحيح الأخطاء الإملائية.

## المشغّلات والدوال

```sql
create or replace function bump_comment_count() returns trigger
language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    update posts set comments_count = comments_count + 1 where id = new.post_id;
  elsif tg_op = 'DELETE' then
    update posts set comments_count = comments_count - 1 where id = old.post_id;
  end if;
  return null;             -- AFTER trigger: القيمة المرجعة مهملة
end $$;
create trigger comments_count_trg after insert or delete on comments
  for each row execute function bump_comment_count();
```

`BEFORE` لتعديل `NEW` أو منع الصف، و`AFTER` للآثار الجانبية على جداول أخرى، و`for each statement` مع `referencing new table as nt` أرخص كثيراً عند التحديثات الجماعية. لا تجعل trigger على A يحدّث B وtrigger على B يحدّث A — سبب رئيسي للجمود. و**لا نداءات شبكة داخل trigger**: اكتب في جدول طابور ودع pg_cron أو Webhook يعالجه. والتقلّبية مهمة — `IMMUTABLE` مطلوبة للفهارس التعبيرية والأعمدة المولَّدة، `STABLE` لدوال القراءة (تُستدعى مرة لكل استعلام)، و`VOLATILE` هي الافتراضي والأبطأ.

## SECURITY DEFINER ومخاطره

الدالة تعمل بصلاحيات مالكها لا المستدعي، فتتجاوز RLS.

```sql
create or replace function get_team_stats(p_team uuid) returns table (total bigint)
language plpgsql security definer set search_path = ''   -- search_path إلزامي
as $$
begin
  if not exists (select 1 from public.team_members
                 where team_id = p_team and user_id = auth.uid()) then
    raise exception 'forbidden' using errcode = '42501';
  end if;
  return query select count(*) from public.orders o where o.team_id = p_team;
end $$;
revoke all on function get_team_stats(uuid) from public;
grant execute on function get_team_stats(uuid) to authenticated;
```

`set search_path = ''` يمنع اختطاف المسار: بدونه يستطيع مستخدم إنشاء جدول باسم مطابق في مخططه ليُنفَّذ بدل جدولك، فاكتب كل الأسماء مؤهَّلة بالمخطط. وابدأ بـ `SECURITY INVOKER` (الافتراضي) دائماً؛ `DEFINER` فقط لتجاوز مقصود ومع تحقق تفويض صريح داخل الدالة. و`revoke ... from public` ثم منح صريح، وإلا فالدالة متاحة للجميع.

## المعاملات ومستويات العزل

| المستوى | يمنع | تكلفته |
|---|---|---|
| `read committed` (الافتراضي) | القراءة المتّسخة | لا شيء |
| `repeatable read` | + غير القابلة للتكرار والصفوف الشبح | فشل `40001` يحتاج إعادة محاولة |
| `serializable` | كل شذوذات التزامن | أعلى معدّل فشل serialization |

في `read committed` كل **أمر** يرى لقطة جديدة، فـ `select` ثم `update` في نفس المعاملة قد يعملان على حالتين مختلفتين — سبب كلاسيكي لخصم رصيد مرتين. والحل للأرصدة والعدّادات تحديث ذرّي واحد:

```sql
-- خطأ: قراءة ثم حساب في التطبيق ثم كتابة.  صواب:
update wallets set balance = balance - 100
where id = $1 and balance >= 100 returning balance;   -- صفر صفوف = رصيد غير كافٍ
```

عند الحاجة لقراءة ثم قرار استعمل `select ... for update`، و`serializable` بلا منطق إعادة محاولة على `40001` لا معنى له. وأبقِ المعاملات قصيرة: معاملة مفتوحة تنتظر رد شبكة تُجمّد VACUUM وتُراكم التضخّم.

## الأقفال والجمود

القرّاء لا يُحجبون بالكتّاب (MVCC)، لكن `alter table` يأخذ `ACCESS EXCLUSIVE` ويحجب **كل شيء** بما فيه `SELECT` — اضبط `set lock_timeout = '3s';` قبل أي DDL على الإنتاج. والجمود يحدث عندما معاملتان تقفلان صفين بترتيب معكوس، والوقاية أن تقفل دائماً بترتيب ثابت (تصاعدياً بالمعرّف). ولطابور المهام `for update skip locked` هو النمط الصحيح — كل عامل يأخذ صفاً مختلفاً بلا انتظار:

```sql
update jobs set status = 'running', started_at = now()
where id in (select id from jobs where status = 'queued'
             order by created_at for update skip locked limit 10)
returning *;
```

لرؤية الحجب الحالي: `select * from pg_locks join pg_stat_activity using (pid) where not granted;`

## VACUUM والتضخّم

`UPDATE` يكتب صفاً جديداً ويترك القديم ميتاً، وVACUUM يستردّ المساحة. وعتبة `autovacuum` الافتراضية 20% من الجدول — على جدول 50M صف يعني 10M صف ميت قبل أن يبدأ. اخفضها للجداول الساخنة:

```sql
alter table orders set (autovacuum_vacuum_scale_factor = 0.02,
                        autovacuum_analyze_scale_factor = 0.01);
```
`VACUUM` العادي لا يُرجع المساحة لنظام الملفات بل يعيد استعمالها داخلياً؛ و`VACUUM FULL` يُرجعها لكنه يأخذ `ACCESS EXCLUSIVE` فلا تشغّله على الإنتاج — البديل `pg_repack`. وشغّل `ANALYZE` يدوياً بعد أي هجرة تُدخل بيانات ضخمة وإلا انهارت خطط الاستعلام. والمعاملات الطويلة و replication slots المهجورة تمنع التنظيف؛ وتجاوز 20% صفوف ميتة في جدول ساخن يعني ضبطاً خاطئاً للـ autovacuum لا حاجة لـ VACUUM يدوي متكرر:

```sql
select relname, n_live_tup, n_dead_tup, last_autovacuum,
       round(100.0 * n_dead_tup / nullif(n_live_tup + n_dead_tup, 0), 1) dead_pct
from pg_stat_user_tables where n_dead_tup > 10000 order by dead_pct desc;
```

## قائمة تحقق

- [ ] كل استعلام ساخن له فهرس مطابق، والترتيب داخله: مساواة ثم نطاق
- [ ] الفهارس الجزئية مستعملة حيث الشرط ثابت (`deleted_at is null`، `status='open'`)
- [ ] لا فهارس بصفر `idx_scan` باقية بعد شهر من التشغيل
- [ ] JSONB مفهرس بـ `jsonb_path_ops` إن كان `@>` هو الاستعمال الوحيد
- [ ] النص العربي يمرّ بدالة تطبيع `IMMUTABLE` في الفهرسة والاستعلام معاً، والمدخل الحر بـ `websearch_to_tsquery`
- [ ] كل دالة `SECURITY DEFINER` فيها `set search_path = ''` وتحقق تفويض صريح
- [ ] لا نداءات شبكة داخل أي trigger
- [ ] الأرصدة والعدّادات تُحدَّث بأمر ذرّي واحد لا بقراءة ثم كتابة
- [ ] `set lock_timeout` قبل أي DDL على الإنتاج، وطوابير المهام تستعمل `for update skip locked`
- [ ] `dead_pct` تحت 20% في الجداول الساخنة و`autovacuum_vacuum_scale_factor` مضبوط لها
