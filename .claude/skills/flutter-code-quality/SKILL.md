---
name: flutter-code-quality
description: Dart and Flutter code quality — effective Dart style, null safety, sealed classes and pattern matching, immutable models with freezed, error handling conventions, linting, and code review standards. Use when refactoring, reviewing code, or when the user says "تنظيف الكود", "إعادة هيكلة", "مراجعة", "refactor", "clean code", "lint", "best practices".
---

# Dart & Flutter Code Quality

## Naming

| Thing | Style |
|---|---|
| Files, folders | `snake_case.dart` |
| Classes, enums, typedefs, extensions | `UpperCamelCase` |
| Variables, functions, parameters | `lowerCamelCase` |
| Constants | `lowerCamelCase` (not `SCREAMING_CAPS`) |
| Private | leading `_` |

Names say what, not how: `fetchOpenReports()` not `getData2()`. Booleans read as predicates: `isLoading`, `hasError`, `canSubmit`.

## Null safety

```dart
// ❌
final name = user!.profile!.name!;

// ✅
final name = user?.profile?.name ?? 'مستخدم';
```

`!` is a promise you cannot break. Use it only where you have just checked, or where null is a genuine programming error. `late` without initialization throws at first read — prefer a nullable field or constructor injection.

```dart
if (value case final v?) { use(v); }        // pattern-matched null check
final list = maybeList ?? const [];          // const empty collections are free
```

## Immutability

```dart
@freezed
class Report with _$Report {
  const factory Report({
    required String id,
    required String title,
    @Default(ReportStatus.open) ReportStatus status,
  }) = _Report;
  factory Report.fromJson(Map<String, dynamic> j) => _$ReportFromJson(j);
}
```

`freezed` gives `copyWith`, `==`, `hashCode`, `toString` and unions for free. Without it, hand-write `copyWith` and equality — a state class without value equality causes rebuilds that never stop or updates that never happen.

Never mutate a list in place and expect a rebuild: `state = [...state, item]`, not `state.add(item)`.

## Sealed classes + pattern matching (Dart 3)

```dart
sealed class Result<T> {}
final class Ok<T> extends Result<T> { const Ok(this.value); final T value; }
final class Err<T> extends Result<T> { const Err(this.failure); final AppFailure failure; }

final message = switch (result) {
  Ok(:final value) => 'تم: ${value.title}',
  Err(:final failure) => failure.message,
};
```

`sealed` makes the switch exhaustive — add a new subtype and the compiler shows you every place that must handle it. This is the single biggest correctness win in modern Dart.

Records for small multi-returns: `(int count, String label) summarize() => (3, 'بلاغات');`

## Error handling convention

Pick one and apply it everywhere:

- **Exceptions** — throw a typed `AppFailure` from repositories, catch at the controller boundary, convert to UI state. Simplest; recommended.
- **Result type** — never throw; return `Result<T>`. More explicit, more ceremony.

Either way:
- Never `catch (e) {}` — an empty catch hides real bugs.
- Never `catch` without rethrowing or handling meaningfully.
- Never show a raw exception string to the user.
- Log the technical detail; show a localized sentence.

```dart
try {
  return await _api.list();
} on DioException catch (e, st) {
  logger.e('reports.list failed', error: e, stackTrace: st);
  throw mapDioError(e);
}
```

## Widget hygiene

- One widget per file once it exceeds ~100 lines.
- `const` constructors everywhere possible.
- Extract classes, not `_buildX()` methods.
- No business logic, no HTTP, no SQL inside `build`.
- No `BuildContext` stored in a field or passed into a controller.
- Keys: `ValueKey(item.id)` on list items; `GlobalKey` only when you truly need imperative access.

## Async

```dart
// ❌ sequential
for (final id in ids) { results.add(await fetch(id)); }

// ✅ parallel
final results = await Future.wait(ids.map(fetch));
```

- Return `Future<void>`, not `void`, from async methods so callers can await.
- Mark deliberately fire-and-forget calls with `unawaited(...)`.
- Always `await` or `.ignore()` — a silently dropped future hides errors.

## Lints

`analysis_options.yaml`:

```yaml
include: package:flutter_lints/flutter.yaml

analyzer:
  language:
    strict-casts: true
    strict-raw-types: true
  errors:
    missing_required_param: error
    missing_return: error
    invalid_annotation_target: ignore
  exclude: ["**/*.g.dart", "**/*.freezed.dart", "lib/l10n/**"]

linter:
  rules:
    always_declare_return_types: true
    avoid_print: true
    prefer_const_constructors: true
    prefer_const_declarations: true
    prefer_final_locals: true
    require_trailing_commas: true
    unawaited_futures: true
    use_super_parameters: true
    sized_box_for_whitespace: true
    avoid_unnecessary_containers: true
```

Consider `very_good_analysis` for a stricter preset. Run in CI:

```bash
dart format --set-exit-if-changed .
flutter analyze --fatal-infos
```

Trailing commas are how `dart format` produces readable multi-line widget trees — keep `require_trailing_commas` on.

## Comments

Write **why**, not what. `// نستخدم مهلة أطول هنا لأن استجابة النموذج تصل خلال 30 ثانية` is useful; `// increment i` is noise. Use `///` doc comments on public APIs. Delete commented-out code — git remembers it.

## Review checklist

- [ ] No hardcoded user-facing strings, colors, or sizes
- [ ] Errors typed, localized, and logged
- [ ] All four UI states handled (loading/empty/error/data)
- [ ] Controllers and subscriptions disposed
- [ ] `mounted` / `context.mounted` checked after every `await`
- [ ] Lists paginated and keyed
- [ ] No secrets, no `print`
- [ ] `flutter analyze` and `flutter test` clean
- [ ] RTL and dark mode checked
- [ ] New behaviour has a test
