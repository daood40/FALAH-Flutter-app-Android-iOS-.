---
name: flutter-local-database
description: Local persistence in Flutter — choosing between shared_preferences, Hive, Drift/sqflite and Isar; schema and migrations; offline-first caching and sync with a remote backend. Use for offline support, local caching, or when the user says "قاعدة بيانات محلية", "حفظ البيانات", "أوفلاين", "sqlite", "drift", "hive", "offline".
---

# Local Database & Offline Storage

## Choosing

| Need | Use |
|---|---|
| A few scalar settings (theme, locale, onboarding seen) | `shared_preferences` |
| Tokens, keys, anything secret | `flutter_secure_storage` (see `flutter-security`) |
| Key–value objects, small cache, fast, no queries | `hive_ce` (maintained fork of Hive) |
| Relational data, joins, filters, reactive queries, migrations | **`drift`** (recommended) |
| Raw SQL control, minimal deps | `sqflite` |
| Large object graphs, very fast reads | `isar` (check maintenance status before adopting) |

Default recommendation: `shared_preferences` for settings + `drift` for real data.

## shared_preferences

```dart
final prefs = await SharedPreferences.getInstance();
await prefs.setString('locale', 'ar');
final locale = prefs.getString('locale') ?? 'ar';
```

Not for lists of records, not for secrets, not for anything over a few KB.

## Drift

```bash
flutter pub add drift drift_flutter
flutter pub add -d drift_dev build_runner
```

```dart
// tables
class Reports extends Table {
  TextColumn get id => text()();
  TextColumn get title => text().withLength(min: 1, max: 200)();
  TextColumn get status => text().withDefault(const Constant('open'))();
  DateTimeColumn get createdAt => dateTime()();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();
  @override
  Set<Column> get primaryKey => {id};
}

@DriftDatabase(tables: [Reports])
class AppDb extends _$AppDb {
  AppDb() : super(driftDatabase(name: 'app_db'));

  @override
  int get schemaVersion => 2;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onUpgrade: (m, from, to) async {
          if (from < 2) await m.addColumn(reports, reports.synced);
        },
      );

  // reactive query — the UI updates automatically on any write
  Stream<List<Report>> watchOpen() =>
      (select(reports)..where((r) => r.status.equals('open'))
                     ..orderBy([(r) => OrderingTerm.desc(r.createdAt)]))
          .watch();

  Future<void> upsertAll(List<Report> rows) =>
      batch((b) => b.insertAllOnConflictUpdate(reports, rows));
}
```

```bash
dart run build_runner build --delete-conflicting-outputs
```

Rules:
- **Bump `schemaVersion` and write the migration** for every schema change. Shipping a changed schema without a migration crashes every existing install on launch.
- Test migrations: `drift_dev schema dump` + `schema steps`, or at minimum install the old build, then upgrade over it.
- Use `batch()` for bulk writes — inserting 500 rows one by one takes seconds.
- Index columns you filter or sort on frequently.
- `.watch()` returns a `Stream` — feed it to a `StreamProvider` and the UI stays in sync for free.

## Offline-first pattern

Read from local, write to local, sync in the background. The UI never waits for the network.

```dart
class ReportRepository {
  ReportRepository(this._db, this._api, this._net);

  // UI always watches the local DB
  Stream<List<Report>> watch() => _db.watchOpen();

  // Pull
  Future<void> refresh() async {
    if (!await _net.isOnline) return;
    final since = await _db.lastSyncedAt();
    final remote = await _api.fetchSince(since);
    await _db.upsertAll(remote);
    await _db.setLastSyncedAt(DateTime.now());
  }

  // Push (write-behind)
  Future<void> create(Report r) async {
    await _db.insert(r.copyWith(synced: false));   // instant UI update
    unawaited(_syncPending());
  }

  Future<void> _syncPending() async {
    if (!await _net.isOnline) return;
    for (final r in await _db.pending()) {
      try {
        await _api.create(r);
        await _db.markSynced(r.id);
      } catch (_) { break; }   // retry on next connectivity event
    }
  }
}
```

Details that matter:
- Generate ids **client-side** (`uuid` package) so a row created offline keeps its identity after sync.
- Keep a `synced` / `pendingOp` column — never a separate "queue" list that can drift from the data.
- Retry on connectivity change: `Connectivity().onConnectivityChanged.listen((_) => _syncPending())` (`connectivity_plus`). Connectivity ≠ reachability; confirm with a real request before assuming online.
- Conflict policy: decide explicitly. Last-write-wins with `updated_at` is fine for most apps; anything collaborative needs server-side merge.
- Show sync state in the UI (a small "لم تتم المزامنة" badge) — silent failure is worse than a visible pending marker.

## Caching remote responses

```dart
Future<List<Report>> get({Duration maxAge = const Duration(minutes: 5)}) async {
  final age = await _db.cacheAge('reports');
  if (age != null && age < maxAge) return _db.all();
  final fresh = await _api.fetch();
  await _db.upsertAll(fresh);
  return fresh;
}
```

Stale-while-revalidate is usually better: return cached immediately, fetch in the background, emit again.

## Housekeeping

- Purge old rows on launch (`delete where createdAt < now - 30 days`) — an unbounded local DB eventually fills the device.
- Close the database in `dispose` for test isolation; in the app it lives for the process lifetime.
- Never store secrets or PII in an unencrypted local DB. For encryption use `sqlcipher_flutter_libs` with drift, or encrypt values before writing.
- Clear all local data on sign-out, or the next user on the device sees the previous user's records.
