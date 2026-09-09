---
name: data-supabase-backend
description: الجانب الخلفي من Supabase — سياسات RLS المعقّدة واختبارها، دوال RPC، المشغّلات، Edge Functions، service_role، pg_cron، Webhooks، سياسات Storage، والحدود. تُفتح عند ذكر "RLS", "سياسات", "rpc", "edge function", "service role", "pg_cron", "storage policy", "row level security".
---

# Supabase: الجانب الخلفي

كل ما هنا SQL ينفَّذ على القاعدة. لا شيء عن عميل Dart.

> استدعاء RPC والاشتراك في الوقت الحقيقي من التطبيق: مهارة flutter-supabase.

## ما تراه القاعدة عن المستخدم

`auth.uid()` تُرجع uuid المستخدم من JWT أو NULL، `auth.role()` تُرجع `anon` أو `authenticated` أو `service_role`، و`auth.jwt()->'app_metadata'->>'tenant_id'` تقرأ ادعاءً مخصّصاً تكتبه أنت. القاعدة الحاكمة: `user_metadata` **يعدّله المستخدم بنفسه**. لا تبنِ عليه أي قرار تفويض أبداً. `app_metadata` لا يعدّله إلا service_role — وهو مكان الدور والمستأجر.

## تفعيل RLS — لا استثناء

```sql
alter table public.orders enable row level security;
alter table public.orders force row level security;  -- يشمل مالك الجدول أيضاً
-- فحص CI: يجب أن يُرجع صفراً على الإنتاج
select relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname='public' and c.relkind='r' and not c.relrowsecurity;
```

جدول في `public` بلا RLS مفتوح للعالم عبر PostgREST. **بنية السياسة**: `using` تُطبَّق على الصفوف الموجودة (select/update/delete)، و`with check` على القيمة الجديدة (insert/update). و`UPDATE` يحتاج **الاثنين**: `using` تحدّد ما يعدّله و`with check` تمنعه من تحويل الصف لملكية غيره — نسيان `with check` في `UPDATE` هو الثغرة الأكثر شيوعاً في Supabase.

سياسات `permissive` تُجمع بـ OR و`restrictive` بـ AND كحاجز فوق الكل. واكتب `to authenticated` صراحةً؛ سياسة بلا `to` تنطبق على `anon` أيضاً.

## نمط الملكية

```sql
create policy "own select" on public.notes for select to authenticated
  using ( user_id = (select auth.uid()) );
create policy "own update" on public.notes for update to authenticated
  using ( user_id = (select auth.uid()) ) with check ( user_id = (select auth.uid()) );
-- ومثلهما insert بـ with check فقط، وdelete بـ using فقط
create index notes_user_id_idx on public.notes (user_id);   -- إلزامي
```

تحسين حاسم: اكتب `(select auth.uid())` بالأقواس لا `auth.uid()` مجرّدة — اللف في استعلام فرعي يجعل Postgres يقيّمها **مرة واحدة** (InitPlan) بدل مرة لكل صف، والفرق على 100k صف ملموس جداً.

## نمط الأدوار

جدول `user_roles(user_id, role)` عليه RLS و**بلا أي سياسة كتابة** — يُدار عبر service_role فقط وإلا رقّى المستخدم نفسه. و`SECURITY DEFINER` ضرورية في دالة الفحص: بدونها تحتاج سياسة قراءة على `user_roles` نفسه فتنشأ عودية.

```sql
create or replace function public.has_role(p_role text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.user_roles
                 where user_id = auth.uid() and role = p_role)
$$;
create policy "admins read all" on public.orders
  for select to authenticated using ( (select public.has_role('admin')) );
```

## نمط المشاركة

جدول `doc_shares(doc_id, user_id, perm)` بمفتاح مركّب وفهرس على `(user_id, doc_id)`، والسياسة تجمع الملكية بالمشاركة. لسياسة التعديل أضف `and s.perm = 'write'` داخل `exists`، و`with check ( owner_id = documents.owner_id )` لمنع نقل الملكية:
```sql
create policy "owner or shared read" on public.documents for select to authenticated
  using ( owner_id = (select auth.uid())
          or exists (select 1 from public.doc_shares s
                     where s.doc_id = documents.id and s.user_id = (select auth.uid())) );
```

## نمط تعدد المستأجرين

```sql
create or replace function public.current_tenant() returns uuid
language sql stable as $$
  select nullif(auth.jwt()->'app_metadata'->>'tenant_id','')::uuid $$;
create policy "tenant isolation" on public.invoices for all to authenticated
  using      ( tenant_id = (select public.current_tenant()) )
  with check ( tenant_id = (select public.current_tenant()) );
create index invoices_tenant_idx on public.invoices (tenant_id, created_at desc);
```

`tenant_id` عمود `not null` في **كل** جدول مستأجَر وأول عمود في كل فهرس مركّب. والخطأ الأكثر شيوعاً: جدول جديد يُضاف بعد أشهر بلا `enable row level security` — كل العزل ينهار من بابه.

## اختبار السياسات كمستخدم حقيقي

غير قابل للتفاوض — اختبر داخل معاملة تُلغى:

```sql
begin;
  select set_config('request.jwt.claims', json_build_object(
    'sub','11111111-1111-1111-1111-111111111111', 'role','authenticated',
    'app_metadata', json_build_object('tenant_id','aaaa1111-...'))::text, true);
  set local role authenticated;
  select count(*) from public.invoices;                  -- هذا المستأجر فقط
  insert into public.invoices (tenant_id, total_minor)
    values ('bbbb2222-...', 100);                        -- يجب أن يفشل
rollback;
```

`set local role authenticated` ضرورية: بدونها تبقى superuser وتتجاوز كل شيء وتظن أن السياسة تعمل. اختبر لكل جدول ثلاث حالات — المالك يرى، غير المالك لا يرى، وغير المالك لا يكتب على صف غيره — واختبر `anon` كذلك. و`explain` تحت RLS يُظهر شرط السياسة في الخطة؛ `Seq Scan` بسببه يعني فهرساً ناقصاً.

## دوال Postgres وRPC

كل دالة في `public` تصبح `POST /rest/v1/rpc/<name>` تلقائياً.

```sql
create or replace function public.place_order(p_items jsonb)
returns uuid language plpgsql security invoker set search_path = '' as $$
declare v_order uuid;
begin
  insert into public.orders (user_id, status)
  values (auth.uid(), 'pending') returning id into v_order;
  -- السعر يُقرأ من القاعدة لا من العميل: لقطة تاريخية وحماية من التلاعب
  insert into public.order_items (order_id, product_id, qty, unit_price_minor)
  select v_order, (i->>'product_id')::bigint, (i->>'qty')::int, p.price_minor
  from jsonb_array_elements(p_items) i
  join public.products p on p.id = (i->>'product_id')::bigint;
  return v_order;
end $$;
revoke all on function public.place_order(jsonb) from public;   -- ثم منح صريح
grant execute on function public.place_order(jsonb) to authenticated;
```

الدالة كلها معاملة واحدة — هذا سبب وجودها الأول: استبدال ثلاث نداءات شبكة بنداء ذرّي واحد. و`security invoker` هو الافتراضي والصحيح؛ لا تلجأ لـ `definer` إلا لتجاوز مقصود ومعه تحقق تفويض يدوي و`search_path` فارغ. الأخطاء: `raise exception 'رسالة' using errcode = 'P0001';` تصل للعميل كـ 400، فاستعمل رموزاً ثابتة يفهمها التطبيق، واجعل دوال القراءة `stable`.

نمط توليد الصفوف المرتبطة، إنشاء ملف تعريف تلقائياً عند التسجيل:
```sql
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'name', 'مستخدم'))
  on conflict (id) do nothing;
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();
```

`security definer` إلزامية لأن المشغّل يعمل في سياق `auth`، و`on conflict do nothing` يمنع فشل التسجيل عند إعادة المحاولة. أي استثناء هنا يُفشل إنشاء الحساب نفسه ويظهر كـ "Database error saving new user" — أبقِه بسيطاً جداً.

## Edge Functions: متى ومتى لا

| الحالة | الأداة |
|---|---|
| منطق يمسّ جداول القاعدة فقط، أو ذرّية عبر عدة جداول | دالة Postgres + RPC |
| نداء طرف ثالث (دفع، SMS، ذكاء اصطناعي)، أو إخفاء مفتاح API، أو استقبال webhook خارجي والتحقق من توقيعه | Edge Function |
| معالجة تتجاوز حدود المهلة | خدمة خارجية |

إن كان المنطق SQL خالصاً، فوضعه في Edge Function يضيف قفزة شبكة وبرد بدء بلا مقابل. وداخلها مرّر ترويسة `Authorization` الخاصة بالمستخدم إلى عميل Supabase لتبقى RLS فعّالة، ولا تستعمل `service_role` إلا بعد تحقق تفويض تكتبه بنفسك. فمفتاح `anon` يعيش داخل تطبيق العميل وخاضع لـ RLS، أما `service_role` فعلى الخادم فقط (Edge Functions، GitHub Actions) و**يتجاوز RLS كله**: لا يدخل تطبيق Flutter ولا موقع ويب ولا مستودعاً عاماً، وتسريبه = تسريب القاعدة كاملة، ومكانه في GitHub Actions هو Repository Secrets وحدها. ولا أسرار نصية في جداول القاعدة — لأسرار الاستعمال داخل SQL استعمل Supabase Vault، ودوّرها فوراً عند أي شك.

## pg_cron

```sql
select cron.schedule('purge-soft-deleted', '0 3 * * *',
  $$ delete from public.posts
     where deleted_at is not null and deleted_at < now() - interval '30 days' $$);
select * from cron.job_run_details order by start_time desc limit 20;   -- المهام تفشل بصمت
```
الجدولة بتوقيت UTC؛ ليبيا UTC+2 بلا توقيت صيفي فاطرح ساعتين. المهمة تعمل كمالكها وتتجاوز RLS — اكتب شروط الترشيح كاملة بنفسك. الحد الأدنى العملي للتكرار 5 دقائق لأي شيء يمسّ جدولاً كبيراً، وافحص `job_run_details` دورياً لأن المهام تفشل بصمت. ولنداء HTTP مجدول استعمل `pg_net` مع `net.http_post` داخل مهمة cron.

## Webhooks وسياسات Storage

Database Webhooks مشغّلات تستدعي `net.http_post` بعد insert/update/delete، وحمولتها تحوي `record` و`old_record`. اجعل المستقبِل **idempotent** — التسليم قد يتكرر. وStorage جداول عادية عليها RLS (`storage.objects`, `storage.buckets`) تحصر المستخدم في مجلد باسم معرّفه:
```sql
create policy "own folder upload" on storage.objects for insert to authenticated
  with check ( bucket_id = 'avatars'
               and (storage.foldername(name))[1] = (select auth.uid())::text );
```

bucket خاص + رابط موقّع محدود المدة لأي محتوى شخصي لا bucket عام، وحدّد الحجم الأقصى وأنواع MIME على مستوى الـ bucket لا في العميل، وعند الحذف احذف الصف والملف معاً — لا رابط تلقائي بينهما.

## مراقبة الاستهلاك والحدود

```sql
select calls, round(mean_exec_time::numeric,1) ms,
       round(total_exec_time::numeric) total, left(query, 90) q
from pg_stat_statements order by total_exec_time desc limit 15;
```
افحص `total_exec_time` لا `mean_exec_time` وحده: استعلام 8ms يُنفَّذ مليون مرة أسوأ من استعلام 900ms يُنفَّذ عشراً. نبّه عند 70% من حد حجم القاعدة، وراقب الـ egress (ثاني أكبر مفاجأة في الفاتورة) ومساحة Storage والملفات اليتيمة. الاتصال المباشر (5432) للجلسات الطويلة فقط وأي شيء عابر يمرّ عبر الـ pooler، ولا تُبثّ عبر Realtime جداول عالية الكتابة.

## قائمة تحقق

- [ ] كل جدول في `public` عليه `enable row level security`، وفحص CI يثبت ذلك
- [ ] كل سياسة `UPDATE` لها `using` و`with check` معاً، وكل سياسة مقيّدة بدور صريح
- [ ] `auth.uid()` مكتوبة `(select auth.uid())`، وفهرس موجود على `user_id` و`tenant_id`
- [ ] لا قرار تفويض يعتمد على `user_metadata`
- [ ] السياسات مُختبرة داخل `begin ... rollback` مع `set local role authenticated`
- [ ] كل دالة `SECURITY DEFINER` فيها `set search_path = ''` وتحقق تفويض داخلي
- [ ] `revoke ... from public` ثم `grant execute to authenticated` لكل دالة RPC
- [ ] `service_role` غير موجود في أي شيء يصل للعميل، ومشغّل إنشاء المستخدم فيه `on conflict do nothing`
- [ ] مهام pg_cron مجدولة بـ UTC ونتائجها مراقَبة في `job_run_details`
- [ ] سياسات Storage تحصر المستخدم في مجلده، والـ bucket الشخصي خاص
- [ ] `pg_stat_statements` مُراجَع، والتنبيه على حجم القاعدة والـ egress مضبوط
