---
name: flutter-testing
description: Testing Flutter apps — unit tests, widget tests, integration tests, mocking with mocktail, testing Riverpod/Bloc, golden tests, and CI. Use when adding tests, fixing flaky tests, or when the user says "اختبار", "تست", "test", "unit test", "widget test", "coverage".
---

# Flutter Testing

## The pyramid, applied

- **Unit** (many, fast): pure logic — validators, mappers, use cases, controllers with mocked repositories.
- **Widget** (fewer): one screen or component, with fake data. This is where most Flutter bugs are caught.
- **Integration** (few): critical end-to-end flows only — sign in, create, pay.

Do not chase a coverage number. Cover business rules, error paths, and anything that has broken before.

## Setup

```yaml
dev_dependencies:
  flutter_test: { sdk: flutter }
  integration_test: { sdk: flutter }
  mocktail: ^1.0.0
  golden_toolkit: ^0.15.0
```

Mirror `lib/` in `test/`: `lib/features/auth/domain/login_use_case.dart` → `test/features/auth/domain/login_use_case_test.dart`.

## Unit

```dart
void main() {
  group('Validators.libyanPhone', () {
    test('accepts a valid local number', () {
      expect(Validators.libyanPhone('0912345678'), isNull);
    });
    test('accepts the international form', () {
      expect(Validators.libyanPhone('+218912345678'), isNull);
    });
    test('rejects a short number', () {
      expect(Validators.libyanPhone('0912'), isNotNull);
    });
  });
}
```

One behaviour per test. The name states the behaviour, not the method.

## Mocking with mocktail

```dart
class MockReportRepo extends Mock implements ReportRepository {}

void main() {
  late MockReportRepo repo;

  setUp(() {
    repo = MockReportRepo();
    registerFallbackValue(FakeReport());   // needed for any() on custom types
  });

  test('loads reports', () async {
    when(() => repo.fetchAll()).thenAnswer((_) async => [report1]);

    final controller = ReportsCubit(repo);
    await controller.load();

    expect(controller.state, isA<ReportsLoaded>());
    verify(() => repo.fetchAll()).called(1);
  });

  test('emits failure on error', () async {
    when(() => repo.fetchAll()).thenThrow(const NetworkFailure());

    final controller = ReportsCubit(repo);
    await controller.load();

    expect(controller.state, isA<ReportsFailed>());
  });
}
```

`thenAnswer` for async, `thenReturn` for sync, `thenThrow` for errors. Test the failure path — that is where the real bugs are.

## Widget tests

```dart
testWidgets('shows the list when data arrives', (tester) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        reportsControllerProvider.overrideWith(() => FakeReportsController([r1, r2])),
      ],
      child: const MaterialApp(home: ReportsScreen()),
    ),
  );

  await tester.pumpAndSettle();

  expect(find.text('بلاغ أول'), findsOneWidget);
  expect(find.byType(ReportTile), findsNWidgets(2));
});

testWidgets('shows the empty state', (tester) async { /* ... */ });
testWidgets('retry calls the controller again', (tester) async {
  await tester.tap(find.text('إعادة المحاولة'));
  await tester.pump();
  verify(() => controller.load()).called(1);
});
```

`pump()` advances one frame; `pumpAndSettle()` runs until no animations remain — it **hangs** on an infinite animation (a looping spinner), so use `pump(Duration(...))` there instead.

Finders: prefer `find.byKey`, `find.text`, `find.byType`. Add `Key`s to the widgets you assert on so a copy change does not break the test.

Provide localizations when the widget uses them:

```dart
MaterialApp(
  locale: const Locale('ar'),
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  supportedLocales: AppLocalizations.supportedLocales,
  home: screen,
)
```

Set a screen size for layout-dependent tests:

```dart
tester.view.physicalSize = const Size(1080, 1920);
tester.view.devicePixelRatio = 3.0;
addTearDown(tester.view.reset);
```

Mock network images or `Image.network` throws in tests — wrap with `mockNetworkImagesFor(() async { ... })` (`network_image_mock`).

## Riverpod

```dart
final container = ProviderContainer(overrides: [repoProvider.overrideWithValue(mockRepo)]);
addTearDown(container.dispose);

expect(container.read(reportsProvider), const AsyncLoading<List<Report>>());
await container.read(reportsProvider.future);
expect(container.read(reportsProvider).value, hasLength(2));
```

## Golden tests

```dart
testGoldens('report card renders', (tester) async {
  await tester.pumpWidgetBuilder(const ReportCard(...));
  await screenMatchesGolden(tester, 'report_card');
});
```

```bash
flutter test --update-goldens
```

Goldens are font-sensitive — load your Arabic font in `flutter_test_config.dart`, and run goldens only on one platform (usually CI Linux) or they will fail on every machine.

## Integration tests

```dart
// integration_test/login_flow_test.dart
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('user signs in and reaches home', (tester) async {
    app.main();
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('email')), 'a@b.com');
    await tester.enterText(find.byKey(const Key('password')), 'secret123');
    await tester.tap(find.byKey(const Key('submit')));
    await tester.pumpAndSettle(const Duration(seconds: 5));

    expect(find.byType(HomeScreen), findsOneWidget);
  });
}
```

```bash
flutter test integration_test/
```

Point these at a **test backend**, never production. Keep them few — they are slow and the first thing to become flaky.

## Running

```bash
flutter test
flutter test --coverage
genhtml coverage/lcov.info -o coverage/html
flutter test test/features/auth/          # one folder
flutter test --name "libyanPhone"          # one test
```

## CI (GitHub Actions)

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
        with: { channel: stable, cache: true }
      - run: flutter pub get
      - run: dart format --set-exit-if-changed .
      - run: flutter analyze --fatal-infos
      - run: flutter test --coverage
```

## Flaky test causes

- `pumpAndSettle` on an infinite animation → use `pump(duration)`
- Real timers/network in a test → inject a fake clock and mock the client
- Depending on test order → build all state in `setUp`
- Time zone or locale assumptions → pin them in the test
- Golden mismatch across platforms → run goldens on one OS only
