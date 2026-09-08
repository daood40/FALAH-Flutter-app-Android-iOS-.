---
name: flutter-package-authoring
description: Creating, structuring and publishing a reusable Dart/Flutter package — package vs plugin templates, public API design, semantic versioning, pubspec metadata and the pana score, dartdoc, CHANGELOG, publishing to pub.dev, and sharing code privately via git or path dependencies instead. Use when extracting shared code into a package, or when the user says "حزمة", "مكتبة", "باكج", "نشر مكتبة", "package", "plugin", "pub.dev", "publish".
---

# Authoring a Dart / Flutter Package

## Should this be a package at all?

Extract only when the code is used by **two or more apps you actually ship**, or when it is an isolated concern with a narrow surface (an HTTP wrapper, a design-system widget set) that you want to version and test on its own. Otherwise keep it as `lib/src/feature/` inside the app: a package adds a version boundary, a changelog, a release step and a second `pub get` to every change. Premature extraction is the most common mistake here — a folder with a clean import boundary gives 90% of the benefit at zero cost. For code shared between **your own** apps only, a git or path dependency (last section) is usually the right answer, not pub.dev.

## Creating

```bash
dart create -t package my_pkg                        # pure Dart, no Flutter
flutter create --template=package my_pkg             # Dart + Flutter widgets, no native code
flutter create --template=plugin --platforms=android,ios \
  -a kotlin -i swift my_plugin                       # native platform code
flutter create --template=plugin_ffi my_ffi_plugin   # C/C++ via dart:ffi
```

| Template | Use when | Contains |
|---|---|---|
| `package` | Pure Dart / Flutter widgets, no platform channels | `lib/`, `test/`, no platform folders |
| `plugin` | Android/iOS/desktop native code | Per-platform folders, method channels, `example/` |
| `plugin_ffi` | Calling a C library directly | Native `src/`, generated bindings |

A `package` compiles without an `example/`; write one anyway. A `plugin` gets one by default and it is the only way to run the native code.

## Layout

```
my_pkg/
  lib/my_pkg.dart        # barrel: exports only, no implementation
  lib/src/               # everything else — private by convention
  example/               # a real runnable app depending on ../
  test/  pubspec.yaml  README.md  CHANGELOG.md  LICENSE
```

```dart
// lib/my_pkg.dart
export 'src/client.dart' show ApiClient, ApiConfig;
export 'src/models/report.dart';
// src/internal_cache.dart is deliberately NOT exported
```

Anything under `lib/src/` is private by convention and the analyzer warns consumers who import it directly. Nothing else belongs in `lib/` unless it is an intentional second entry point (`lib/testing.dart` for test doubles is legitimate). Do not use `part` / `part of` chains: they break the `src/` privacy model, defeat per-file imports and make file order load-bearing. Use plain imports.

## Designing the public API

- **Keep the surface small** — every exported name is a maintenance promise; you can add later, you cannot remove without a major bump.
- **Take a config object, not eight positional parameters.** `ApiClient(ApiConfig(baseUrl: ..., timeout: ...))` survives new options; `ApiClient(url, timeout, retries, logger)` does not. Named parameters with defaults for anything optional, positional only for the one obvious argument.
- Prefer `sealed`/`final` classes and enums over open inheritance — an abstract class users may `implement` makes every added method breaking. Expose types you control, not third-party types, or you drag that dependency into every consumer's own API, and throw your own exception types rather than bare `Exception('...')`.
- Do not reach for global state (singletons, `SharedPreferences`) inside the package — take it as a parameter so it stays testable.

## Versioning

Semver, and pub's solver depends on it: backwards-compatible feature → minor, bug fix → patch, anything breaking → major. Below `1.0.0` the **minor** slot acts as the major (`^0.3.2` resolves `>=0.3.2 <0.4.0`), so a breaking change in a 0.x package means `0.4.0`.

Breaking includes things that are easy to miss:

- Removing or renaming any exported member, dropping it from the barrel, adding a **required** parameter, or changing a parameter's type.
- Adding a member to an abstract class or interface consumers implement, or a value to an enum — a Dart 3 exhaustive `switch` on it now fails to compile.
- Raising the minimum SDK or Flutter constraint, or changing observable default behaviour.

Deprecate for one minor release before removing:

```dart
@Deprecated('استخدم fetchReport بدلاً منها. ستُحذف في 2.0.0')
Future<Report> getReport(String id) => fetchReport(id);
```

## pubspec.yaml metadata

```yaml
name: my_pkg
description: A typed HTTP client with retry, caching and offline queueing for Flutter apps.
version: 1.3.0
repository: https://github.com/me/my_pkg
issue_tracker: https://github.com/me/my_pkg/issues
topics: [http, networking, offline]
environment: { sdk: ^3.5.0, flutter: '>=3.24.0' }
dependencies:
  flutter: { sdk: flutter }
  http: ^1.2.0
```

- `description`: aim for 60–180 characters; pub.dev deducts points outside that range. `topics`: up to 5, lowercase letters/digits/hyphens, and they drive discovery.
- **Never pin tightly in a library.** `http: 1.2.0` makes your package unusable alongside anything else — caret ranges only; exact pins belong in applications.
- Keep the SDK floor as low as the code allows (raising it later is breaking). Set `publish_to: none` if the package must never be published by accident.

## Documentation and CHANGELOG

Every exported member gets a `///` comment whose first sentence is a complete sentence ending in a period — that is what pub.dev search shows. Square brackets become links in dartdoc.

```dart
/// Sends [report] to the server and returns the stored copy.
///
/// Throws [ApiException] when the server rejects the payload, and
/// [TimeoutException] after [ApiConfig.timeout].
///
/// ```dart
/// final saved = await client.submit(report);
/// ```
Future<Report> submit(Report report) async { ... }
```

Run `dart doc` and read it before publishing. `README.md` needs a one-sentence purpose, an install snippet and a **complete runnable example** — not fragments with `...` — plus a screenshot or GIF for anything visual. The tooling parses `CHANGELOG.md`, so keep the shape exact: a `##` heading whose version matches `pubspec.yaml`, newest first. A missing or mismatched top entry costs points and confuses the version picker.

```markdown
## 1.3.0

* Added `ApiConfig.retries`.
* **BREAKING**: `getReport` removed — use `fetchReport`.
```

## Publishing

```bash
dart format --output=none --set-exit-if-changed . && dart analyze --fatal-infos
flutter test
dart pub publish --dry-run     # validates everything pub.dev will check
dart pub publish
```

Publishing is **permanent** — a version can be retracted, never deleted or replaced. Read the file list `--dry-run` prints: anything not git-ignored ships, including stray keys and large fixtures. Use `.pubignore` for files that stay in git but not in the package.

The pub.dev score (160 points, computed by `pana`) covers file conventions and metadata, documentation (dartdoc coverage plus an `example/`), platform support, static analysis with no errors/warnings/lints, and up-to-date dependencies. Run it locally: `dart pub global activate pana` then `pana --no-warning .`. Points are lost most often for no `example/`, under 20% of the public API documented, analyzer warnings, unformatted code, dependencies behind their latest major, an over-tight constraint, and a missing or non-OSI `LICENSE`.

**Verified publisher**: create a publisher on pub.dev, verify the domain (DNS TXT record or Search Console), then transfer the package to it from the package's admin tab. Packages under a verified publisher show the domain instead of an uploader email.

## Federated plugins (native code)

For a plugin with native implementations, split it instead of branching on `Platform.isX` in Dart. `my_pkg` is the app-facing package and the only dependency users add; `my_pkg_platform_interface` holds an abstract class extending `PlatformInterface` from `plugin_platform_interface` — a private token, a `static instance` getter/setter that calls `PlatformInterface.verifyToken`, and a default `MethodChannel` implementation; `my_pkg_android` / `my_pkg_ios` / `my_pkg_windows` each declare `implements: my_pkg` in their `flutter: plugin:` pubspec block and register themselves by setting the interface `instance`. The app-facing pubspec names each platform's `default_package:`, so adding an OS is a new package rather than an edit. Only worth it if third parties may implement platforms; a single-package plugin is fine otherwise.

## Not publishing at all

Usually the right answer for a solo developer sharing code across their own apps.

```yaml
dependencies:
  my_pkg:
    git:
      url: git@github.com:me/my_pkg.git    # SSH works for private repos
      ref: v1.3.0                          # pin a tag, never a branch
      path: packages/my_pkg                # only if it lives in a monorepo
```

While developing locally, keep the git or published version in `dependencies:` and override it — `dependency_overrides` is not inherited by consumers, so it stays a local-only edit:

```yaml
dependency_overrides:
  my_pkg: { path: ../my_pkg }
```

Committing a `path:` entry under `dependencies:` breaks CI and anyone who clones without the sibling folder. Keep `path:` in overrides, or manage the links with `melos` in a monorepo.

## Testing in isolation

`example/pubspec.yaml` uses `my_pkg: { path: ../ }`. The example is both your manual harness and the pub.dev "Example" tab, so make it exercise the real API, not a hello-world screen: run `flutter test` in the package root and `flutter run` inside `example/`. Test as a consumer — import `package:my_pkg/my_pkg.dart`, never `package:my_pkg/src/...`. If a test needs `src/`, the public API is missing a seam. See `flutter-testing`.

## Common mistakes

- Extracting a package for code used by exactly one app, or exporting `src/` files from the barrel.
- Pinning exact dependency versions in a library.
- Adding a required parameter or an enum value in a minor release.
- Publishing without `--dry-run`, shipping secrets or 40 MB of fixtures, a README example that does not compile, or a `path:` dependency committed under `dependencies:` instead of `dependency_overrides`.

## Checklist

- [ ] The package is genuinely shared or genuinely isolated
- [ ] Correct template (`package` / `plugin` / `plugin_ffi`); barrel exports the minimum, implementation lives in `src/`
- [ ] Public API takes config objects, no positional-parameter soup
- [ ] Every exported member has a `///` summary sentence
- [ ] README has a complete runnable example; CHANGELOG top entry matches the pubspec version
- [ ] Caret constraints, low SDK floor, no tight pins
- [ ] `dart format`, `dart analyze`, `flutter test` all clean
- [ ] `example/` runs and exercises the real API
- [ ] `dart pub publish --dry-run` passes and the file list is clean
- [ ] Published under a verified publisher, or shared via a pinned git tag
