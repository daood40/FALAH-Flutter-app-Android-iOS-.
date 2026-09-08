---
name: flutter-debugging
description: Diagnose and fix Flutter errors — build and Gradle failures, dependency conflicts, layout overflow and unbounded constraints, setState after dispose, null and async errors, platform channel issues, plus DevTools and crash reporting. Use when something is broken or an error is pasted, or when the user says "خطأ", "لا يعمل", "مشكلة", "error", "crash", "build failed", "overflow".
---

# Flutter Debugging

## First moves

```bash
flutter clean && flutter pub get
flutter doctor -v
flutter analyze
flutter run -v            # verbose: shows the real underlying error
```

`flutter clean` fixes a surprising share of "impossible" build errors. If it doesn't, read the **first** error in the output, not the last — later errors are usually consequences.

## Layout errors

**`RenderFlex overflowed by N pixels`**
The child is bigger than the space. Wrap the flexible child in `Expanded`/`Flexible`, add `overflow: TextOverflow.ellipsis` + `maxLines` to text, or make the parent scrollable (`SingleChildScrollView`). Never "fix" it by shrinking the font.

**`Vertical viewport was given unbounded height`** / **`RenderBox was not laid out`**
A `ListView`/`Column` inside a `Column`/`ScrollView` with no height. Fix: `Expanded` around the list, or `shrinkWrap: true` + `NeverScrollableScrollPhysics` (short lists only), or use slivers.

**`Incorrect use of ParentDataWidget`**
`Expanded`/`Flexible`/`Positioned` used outside its required parent (`Row`/`Column`/`Flex` or `Stack`).

**`BoxConstraints forces an infinite width/height`**
Usually `double.infinity` inside an unbounded parent. Use `SizedBox.expand`, `Expanded`, or give a concrete size.

Debug tools: `debugPaintSizeEnabled = true`, or the **Widget Inspector** in DevTools — click the overflowing widget and read its constraints in the Layout Explorer.

## State & lifecycle errors

**`setState() called after dispose()`**
An async callback finished after the widget was removed.

```dart
final data = await repo.fetch();
if (!mounted) return;          // always
setState(() => _data = data);
```

Also cancel subscriptions and timers in `dispose()`.

**`Looking up a deactivated widget's ancestor` / `context used after await`**

```dart
await save();
if (!context.mounted) return;
Navigator.of(context).pop();
```

**`setState() or markNeedsBuild() called during build`**
You changed state inside `build`. Move it to `initState`, a callback, or defer: `WidgetsBinding.instance.addPostFrameCallback((_) => ...)`.

**`No MaterialLocalizations found` / `No Directionality widget found`**
The widget is not under a `MaterialApp`. Common in tests — wrap with `MaterialApp(home: ...)`.

**`Scaffold.of() called with a context that does not contain a Scaffold`**
You used the same `build` context that created the `Scaffold`. Use a `Builder`, or `ScaffoldMessenger.of(context)` for snackbars.

## Build & dependency errors

**`Because X depends on Y >=... version solving failed`**
```bash
flutter pub upgrade --major-versions
flutter pub deps        # find who requires the conflicting version
```
Relax your own constraint before adding a `dependency_overrides` — overrides silently ship an untested combination.

**`Execution failed for task ':app:...'` / Gradle**
Check the Java version (`java -version` — Flutter needs JDK 17 for recent AGP), `minSdk`/`compileSdk` vs what a package requires, and try:
```bash
cd android && ./gradlew clean && cd .. && flutter clean && flutter pub get
```

**`Duplicate class` / `Program type already present`**
Two packages pulling different versions of the same native library. Find with `./gradlew app:dependencies`, then align versions or exclude one.

**`Could not resolve com.google...`** — a network/mirror problem, or a missing `google()` repository.

**CocoaPods errors (iOS)**
```bash
cd ios && pod repo update && pod install --repo-update && cd ..
```
Delete `Podfile.lock` and `ios/Pods` if it persists. Check the platform line in `ios/Podfile` matches the minimum iOS version your packages need.

**`*.g.dart` / `*.freezed.dart` not found**
```bash
dart run build_runner build --delete-conflicting-outputs
```

## Runtime errors

**`Null check operator used on a null value`**
Somewhere a `!` on a null. Find it in the stack trace; replace with a real check or a default. Common sources: `currentUser!` before login, `data!['key']` on a response missing the key.

**`type 'Null' is not a subtype of type 'String'`**
JSON parsing — the server omitted a field your model declared non-nullable. Make it nullable or give it a default.

**`Unhandled Exception: ... FormatException`**
Bad `int.parse` / `jsonDecode` input. Use `int.tryParse` and validate before decoding.

**`PlatformException(channel-error, Unable to establish connection...)`**
A plugin was added without a full restart. **Hot reload does not load new native code** — stop the app and `flutter run` again.

**`MissingPluginException`** — same cause; full restart, and check the plugin supports the current platform (web especially).

## Async traps

- `await` in a loop is sequential — use `Future.wait` for parallel work.
- An unawaited `Future` swallows its error. Either `await` it or attach `.catchError`.
- `async` in `initState` cannot be awaited by the framework — call an async method and handle errors inside it.
- Errors thrown inside an `Isolate`/`compute` must be caught there or forwarded.

## Global error capture

```dart
void main() {
  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    Sentry.captureException(details.exception, stackTrace: details.stack);
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    Sentry.captureException(error, stackTrace: stack);
    return true;
  };
  runApp(const MyApp());
}
```

Ship with Sentry or Firebase Crashlytics from day one — and keep `build/symbols` from the obfuscated build so stack traces are readable (`flutter symbolize -i trace.txt -d build/symbols/app.android-arm64.symbols`).

## DevTools

```bash
flutter run
# press 'v' or open the printed DevTools URL
```

- **Inspector** — widget tree, layout constraints, "select widget mode".
- **Performance** — frame timeline, UI vs raster.
- **CPU profiler** — where Dart time goes.
- **Memory** — leak hunting, heap snapshots.
- **Network** — HTTP requests and timings.
- **Logging** — filterable, better than `print`.

## Debugging method

1. Reproduce reliably. An intermittent bug you cannot trigger cannot be verified as fixed.
2. Read the **full** stack trace and find the first frame in *your* code.
3. Narrow: comment out half the widget tree, or build a minimal repro in a fresh file.
4. Form one hypothesis, test it, don't change five things at once.
5. After fixing, add the regression test.

Do not "fix" by adding `try/catch` around the symptom, or by making a field nullable to silence a crash — find why it is null.
