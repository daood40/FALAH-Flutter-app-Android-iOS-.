---
name: flutter-project-setup
description: Create or bootstrap a new Flutter project — folder structure, pubspec dependencies, analysis_options, flavors, .env config, app icons and splash. Use when starting a new app, restructuring an existing one, or when the user says "أنشئ تطبيق جديد", "ابدأ مشروع فلتر", "setup project", "flutter create".
---

# Flutter Project Setup

## Before writing code

Ask (or infer) three things: platforms (Android / iOS / Web), backend (Supabase / Firebase / REST / local only), and whether the app is Arabic-first. These change the scaffold.

## Create

```bash
flutter create --org com.example --platforms=android,ios,web my_app
cd my_app
flutter pub get
flutter doctor
```

`--org` sets the bundle/application id. Changing it later means editing `android/app/build.gradle.kts`, `ios/Runner.xcodeproj`, and `AndroidManifest.xml` — pick it correctly the first time.

## Folder structure (feature-first — use this by default)

```
lib/
  main.dart
  app/
    app.dart                # MaterialApp, theme, router wiring
    router.dart
    theme/
  core/
    constants/
    errors/                 # Failure/AppException types
    network/                # dio client, interceptors
    utils/
    widgets/                # shared widgets only
  features/
    auth/
      data/                 # models, remote/local data sources, repo impl
      domain/               # entities, repository interfaces, use cases
      presentation/         # screens, widgets, controllers/providers
    home/
    ...
  l10n/
```

Rules:
- A feature never imports from another feature's `data/` or `presentation/`. Cross-feature sharing goes through `core/` or a domain entity.
- `presentation` may depend on `domain`; `data` implements `domain`. `domain` depends on nothing.
- For small apps (< 5 screens) collapse to `features/<name>/{models,screens,widgets,service.dart}` — do not force clean architecture on a small app.

## pubspec.yaml baseline

```yaml
dependencies:
  flutter:
    sdk: flutter
  flutter_localizations:
    sdk: flutter
  intl: any
  go_router: ^14.0.0
  flutter_riverpod: ^2.5.0
  dio: ^5.4.0
  shared_preferences: ^2.2.0
  flutter_secure_storage: ^9.0.0

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^4.0.0
  build_runner: ^2.4.0
```

Always run `flutter pub add <pkg>` instead of hand-editing versions — it resolves a compatible constraint. Check pub.dev for the package's latest version and Dart 3 / null-safety support before adding it.

## analysis_options.yaml

```yaml
include: package:flutter_lints/flutter.yaml

analyzer:
  errors:
    invalid_annotation_target: ignore
  exclude:
    - "**/*.g.dart"
    - "**/*.freezed.dart"

linter:
  rules:
    prefer_const_constructors: true
    prefer_const_literals_to_create_immutables: true
    avoid_print: true
    require_trailing_commas: true
    use_super_parameters: true
```

## Environment config

Never hardcode keys in Dart source that ships to the client. Use compile-time defines:

```dart
class Env {
  static const supabaseUrl = String.fromEnvironment('SUPABASE_URL');
  static const supabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');
  static const isProd = bool.fromEnvironment('PROD', defaultValue: false);
}
```

```bash
flutter run --dart-define-from-file=env/dev.json
flutter build apk --dart-define-from-file=env/prod.json
```

Add `env/*.json` to `.gitignore` and commit an `env/example.json`. Note: `--dart-define` values are still readable in a decompiled binary — anything truly secret belongs on the server (see `flutter-security`).

## Flavors (dev / staging / prod)

Android: add `productFlavors` in `android/app/build.gradle.kts` with distinct `applicationIdSuffix` (`.dev`) so all three can be installed side by side. iOS: duplicate the scheme and set a different bundle id per configuration.

## Icons and splash

```bash
flutter pub add -d flutter_launcher_icons flutter_native_splash
dart run flutter_launcher_icons
dart run flutter_native_splash:create
```

Source icon: 1024×1024 PNG, no transparency for iOS, with safe padding for Android adaptive icons.

## .gitignore additions

```
env/*.json
!env/example.json
*.jks
*.keystore
key.properties
ios/Runner/GoogleService-Info.plist
android/app/google-services.json
.env
```

## Verify before saying "done"

```bash
flutter analyze
flutter test
flutter build apk --debug
```
