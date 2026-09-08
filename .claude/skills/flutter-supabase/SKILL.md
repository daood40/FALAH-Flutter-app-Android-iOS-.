---
name: flutter-supabase
description: Integrate Supabase with Flutter — auth (email, OTP, OAuth), Postgres queries, Row Level Security policies, realtime subscriptions, storage uploads, and edge functions. Use for any Supabase backend work, or when the user says "سوبابيس", "قاعدة البيانات", "تسجيل الدخول", "supabase", "RLS", "realtime".
---

# Flutter + Supabase

## Setup

```bash
flutter pub add supabase_flutter
```

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Supabase.initialize(
    url: Env.supabaseUrl,
    anonKey: Env.supabaseAnonKey,
    authOptions: const FlutterAuthClientOptions(authFlowType: AuthFlowType.pkce),
  );
  runApp(const ProviderScope(child: MyApp()));
}

final supabase = Supabase.instance.client;
```

The **anon key is public and safe to ship** — it is the RLS policies that protect your data. The `service_role` key must never appear in a Flutter app; it bypasses RLS entirely. Put anything needing it in an Edge Function.

## Auth

```dart
// Sign up
await supabase.auth.signUp(email: email, password: password,
    data: {'full_name': name});              // → raw_user_meta_data

// Sign in
await supabase.auth.signInWithPassword(email: email, password: password);

// Phone OTP
await supabase.auth.signInWithOtp(phone: '+2189XXXXXXX');
await supabase.auth.verifyOTP(phone: '+2189XXXXXXX', token: code, type: OtpType.sms);

// OAuth (Google)
await supabase.auth.signInWithOAuth(OAuthProvider.google,
    redirectTo: 'com.example.myapp://login-callback');

await supabase.auth.signOut();

// Reactive session
supabase.auth.onAuthStateChange.listen((data) {
  final session = data.session;   // null = signed out
});
final user = supabase.auth.currentUser;
```

Sessions persist and refresh automatically. Wire `onAuthStateChange` into your router's `refreshListenable` (see `flutter-navigation`).

Error handling — catch `AuthException` and map `e.message` to a localized string; never show the raw English message to an Arabic user.

For deep-link OAuth on Android add to `AndroidManifest.xml`:

```xml
<intent-filter>
  <action android:name="android.intent.action.VIEW" />
  <category android:name="android.intent.category.DEFAULT" />
  <category android:name="android.intent.category.BROWSABLE" />
  <data android:scheme="com.example.myapp" android:host="login-callback" />
</intent-filter>
```

## Queries

```dart
// Select with filters, join, pagination
final rows = await supabase
    .from('reports')
    .select('id, title, status, created_at, profiles!inner(full_name)')
    .eq('status', 'open')
    .gte('created_at', since.toIso8601String())
    .order('created_at', ascending: false)
    .range(0, 19);                       // page size 20

// Insert and get the row back
final row = await supabase.from('reports').insert({
  'title': title,
  'body': body,
  'user_id': supabase.auth.currentUser!.id,
}).select().single();

// Update
await supabase.from('reports').update({'status': 'closed'}).eq('id', id);

// Upsert
await supabase.from('settings').upsert({'user_id': uid, 'lang': 'ar'});

// Delete
await supabase.from('reports').delete().eq('id', id);

// Call a Postgres function
final res = await supabase.rpc('nearby_reports', params: {'lat': lat, 'lng': lng, 'km': 5});
```

Rules:
- Order matters: `.select()` first, then filters, then `.order()`/`.range()`, then `.single()`/`.maybeSingle()` last.
- `.single()` throws if the result is not exactly one row; use `.maybeSingle()` when zero is valid.
- Never `select('*')` in a list screen — request only the columns the UI shows.
- Always paginate with `.range()`. An unbounded select on a growing table is a future outage.
- Catch `PostgrestException`: `e.code` `'23505'` = unique violation, `'42501'` = RLS denial.

## Row Level Security — write the policies, always

RLS is off by default on a new table. **A table without RLS is world-readable with the anon key.**

```sql
alter table reports enable row level security;

-- read: everyone signed in
create policy "read_reports" on reports
  for select to authenticated using (true);

-- insert: only as yourself
create policy "insert_own" on reports
  for insert to authenticated with check (auth.uid() = user_id);

-- update/delete: only your own rows
create policy "update_own" on reports
  for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "delete_own" on reports
  for delete to authenticated using (auth.uid() = user_id);
```

`using` filters existing rows (select/update/delete); `with check` validates the new row (insert/update). An update policy needs both.

Role-based access — avoid recursive policies by putting the role in the JWT or in a separate table queried with a `security definer` function:

```sql
create or replace function public.is_admin()
returns boolean language sql security definer stable as $$
  select exists(select 1 from profiles where id = auth.uid() and role = 'admin');
$$;

create policy "admin_all" on reports for all to authenticated using (public.is_admin());
```

Test every policy signed in as a normal user, as another user, and signed out. "It works in the SQL editor" proves nothing — the editor runs as `service_role`.

## Profiles table + trigger

```sql
create table profiles (
  id uuid primary key references auth.users on delete cascade,
  full_name text,
  avatar_url text,
  role text default 'user',
  created_at timestamptz default now()
);

create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, full_name)
  values (new.id, new.raw_user_meta_data->>'full_name');
  return new;
end; $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
```

## Realtime

```dart
// Simple: a stream of a whole table
final stream = supabase
    .from('messages')
    .stream(primaryKey: ['id'])
    .eq('room_id', roomId)
    .order('created_at');

// Granular: channel with event types
final channel = supabase.channel('room:$roomId')
  ..onPostgresChanges(
    event: PostgresChangeEvent.insert,
    schema: 'public',
    table: 'messages',
    filter: PostgresChangeFilter(
      type: PostgresChangeFilterType.eq, column: 'room_id', value: roomId),
    callback: (payload) => _add(Message.fromJson(payload.newRecord)),
  )
  ..subscribe();

// in dispose:
await supabase.removeChannel(channel);
```

Realtime must be enabled per table in the dashboard (Database → Replication) or via `alter publication supabase_realtime add table messages;`. Realtime respects RLS — if a client sees nothing, check the select policy first. Always remove the channel on dispose or you leak sockets.

## Storage

```dart
await supabase.storage.from('avatars').uploadBinary(
  '$uid/avatar.jpg',
  bytes,
  fileOptions: const FileOptions(upsert: true, contentType: 'image/jpeg'),
);

// public bucket
final url = supabase.storage.from('avatars').getPublicUrl('$uid/avatar.jpg');

// private bucket
final signed = await supabase.storage.from('docs')
    .createSignedUrl('$uid/file.pdf', 3600);
```

Storage policies are RLS on `storage.objects`; scope by the first path segment:

```sql
create policy "own_folder" on storage.objects for all to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);
```

Compress images client-side before upload (`flutter_image_compress`) — a 6 MB phone photo is an unnecessary cost on both ends.

## Edge Functions

Use for anything needing a secret, third-party API calls, payment webhooks, or logic that must not be trusted to the client.

```dart
final res = await supabase.functions.invoke('send-notification',
    body: {'user_id': id, 'title': t});
if (res.status != 200) throw Exception(res.data);
```

## Repository wrapper

Never call `supabase.from(...)` from a widget. Wrap it:

```dart
class ReportRepository {
  ReportRepository(this._c);
  final SupabaseClient _c;

  Future<List<Report>> fetchAll({int page = 0, int size = 20}) async {
    try {
      final rows = await _c.from('reports').select()
          .order('created_at', ascending: false)
          .range(page * size, page * size + size - 1);
      return rows.map(Report.fromJson).toList();
    } on PostgrestException catch (e) {
      throw AppException(_mapPostgres(e));
    } on SocketException {
      throw AppException('لا يوجد اتصال بالإنترنت');
    }
  }
}
```

This is what makes the app testable and what keeps error messages localized in one place.

## Checklist

- [ ] RLS enabled on every table, policies tested as a real user
- [ ] `service_role` key nowhere in the app
- [ ] All list queries paginated and column-limited
- [ ] Realtime channels removed on dispose
- [ ] Auth errors mapped to Arabic messages
- [ ] Uploads compressed and scoped to the user's folder
