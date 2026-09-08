---
name: flutter-state-management
description: Choose and implement Flutter state management — Riverpod, Bloc/Cubit, Provider, ValueNotifier — with async state, loading/error handling, and testable controllers. Use when wiring data into UI, refactoring setState spaghetti, or when the user says "إدارة الحالة", "state management", "riverpod", "bloc", "provider".
---

# Flutter State Management

## Choosing

| Situation | Use |
|---|---|
| State lives in one widget (a toggle, a controller, form fields) | `StatefulWidget` + `setState` |
| One value shared by a subtree | `ValueNotifier` + `ValueListenableBuilder` or `InheritedNotifier` |
| App-wide, async data, dependency injection, testability | **Riverpod** (default recommendation) |
| Team already on Bloc, or you want explicit event→state auditing | **Bloc / Cubit** |
| Legacy codebase | `provider` — fine, but do not start new projects on it |

Do not mix two solutions in one app. Pick one and be consistent.

## Riverpod (recommended default)

```yaml
dependencies:
  flutter_riverpod: ^2.5.0
  riverpod_annotation: ^2.3.0
dev_dependencies:
  riverpod_generator: ^2.4.0
  build_runner: ^2.4.0
```

```dart
void main() => runApp(const ProviderScope(child: MyApp()));
```

### The four shapes you actually need

```dart
// 1. A dependency (service, client) — never changes
final supabaseProvider = Provider((ref) => Supabase.instance.client);

// 2. Read-only async data
final reportsProvider = FutureProvider.autoDispose<List<Report>>((ref) async {
  final repo = ref.watch(reportRepositoryProvider);
  return repo.fetchAll();
});

// 3. A live stream
final authStateProvider = StreamProvider((ref) =>
    ref.watch(supabaseProvider).auth.onAuthStateChange);

// 4. Mutable state with logic
class ReportsController extends AsyncNotifier<List<Report>> {
  @override
  Future<List<Report>> build() => ref.read(reportRepositoryProvider).fetchAll();

  Future<void> add(Report r) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      await ref.read(reportRepositoryProvider).create(r);
      return ref.read(reportRepositoryProvider).fetchAll();
    });
  }
}

final reportsControllerProvider =
    AsyncNotifierProvider<ReportsController, List<Report>>(ReportsController.new);
```

`AsyncValue.guard` catches errors into `AsyncError` instead of letting them escape — use it for every mutation.

### In the widget

```dart
class ReportsScreen extends ConsumerWidget {
  const ReportsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final reports = ref.watch(reportsControllerProvider);

    return reports.when(
      loading: () => const ReportsSkeleton(),
      error: (e, st) => ErrorView(message: e.toString(),
          onRetry: () => ref.invalidate(reportsControllerProvider)),
      data: (list) => list.isEmpty
          ? const EmptyView()
          : ListView.builder(
              itemCount: list.length,
              itemBuilder: (c, i) => ReportTile(list[i]),
            ),
    );
  }
}
```

### watch vs read vs listen

- `ref.watch` — inside `build`. Rebuilds when the value changes.
- `ref.read` — inside callbacks (`onPressed`, `initState`). **Never** in `build`.
- `ref.listen` — inside `build`, for side effects (snackbar, navigation) without rebuilding.

```dart
ref.listen(reportsControllerProvider, (prev, next) {
  if (next case AsyncError(:final error)) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error')));
  }
});
```

### Parameterized and disposable

```dart
final reportProvider =
    FutureProvider.autoDispose.family<Report, String>((ref, id) async {
  ref.keepAlive();  // optional: survive a brief unmount
  return ref.watch(reportRepositoryProvider).byId(id);
});
```

Use `.autoDispose` by default for screen-scoped data — without it, memory and stale data accumulate.

### Optimistic update

```dart
Future<void> toggleLike(String id) async {
  final old = state.valueOrNull ?? [];
  state = AsyncData([for (final r in old) r.id == id ? r.copyWith(liked: !r.liked) : r]);
  try {
    await repo.toggleLike(id);
  } catch (_) {
    state = AsyncData(old);   // roll back
    rethrow;
  }
}
```

## Bloc / Cubit

Use Cubit unless you genuinely need an event log.

```dart
sealed class ReportsState {}
final class ReportsLoading extends ReportsState {}
final class ReportsLoaded extends ReportsState { ReportsLoaded(this.items); final List<Report> items; }
final class ReportsFailed extends ReportsState { ReportsFailed(this.message); final String message; }

class ReportsCubit extends Cubit<ReportsState> {
  ReportsCubit(this._repo) : super(ReportsLoading());
  final ReportRepository _repo;

  Future<void> load() async {
    emit(ReportsLoading());
    try {
      emit(ReportsLoaded(await _repo.fetchAll()));
    } catch (e) {
      emit(ReportsFailed(e.toString()));
    }
  }
}
```

```dart
BlocBuilder<ReportsCubit, ReportsState>(
  builder: (context, state) => switch (state) {
    ReportsLoading() => const CircularProgressIndicator(),
    ReportsFailed(:final message) => ErrorView(message: message),
    ReportsLoaded(:final items) => _List(items),
  },
)
```

`BlocBuilder` rebuilds; `BlocListener` does side effects; `BlocConsumer` does both. Always `close()` a Cubit created manually (`BlocProvider` does it for you).

## Rules that apply to any solution

- **No business logic in widgets.** A widget reads state and emits intent. Fetching, parsing, retrying, caching belong in a controller/repository.
- **State classes are immutable.** Use `copyWith` (hand-written or via `freezed`). Mutating a list in place will not trigger a rebuild.
- **Model the failure state explicitly** — never `List<Report>?` where `null` means both "loading" and "error".
- **Do not put `BuildContext` in a controller.** Return a result; let the widget navigate.
- **Keep the widget subtree that rebuilds small** — watch the narrowest provider you need (`ref.watch(p.select((s) => s.count))`).
