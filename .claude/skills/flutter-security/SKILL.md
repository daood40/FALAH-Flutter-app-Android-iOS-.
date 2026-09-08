---
name: flutter-security
description: Secure a Flutter app — secret and token storage, API key handling, code obfuscation, certificate pinning, biometric auth, permissions, root/jailbreak awareness, and a pre-release security review. Use when handling auth, payments, personal data, or when the user says "أمان", "حماية", "تشفير", "security", "secure storage", "keys", "biometric".
---

# Flutter Security

## Threat model in one line

Anything shipped in the app binary — Dart code, assets, `--dart-define` values, `.env` files — is readable by anyone with the APK. Build accordingly.

## Secrets

| Kind | Where it belongs |
|---|---|
| LLM / payment / email provider API key | Server only (Edge Function, Cloud Function). Never in the app. |
| Supabase / Firebase **anon/public** key | Fine in the app — access is controlled by RLS / Security Rules |
| Access & refresh tokens | `flutter_secure_storage` |
| User preferences | `shared_preferences` (not secure, and that's fine) |
| Signing keystore, service accounts | Local machine + CI secret store, never in git |

```dart
const _storage = FlutterSecureStorage(
  aOptions: AndroidOptions(encryptedSharedPreferences: true),
  iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
);

await _storage.write(key: 'refresh_token', value: token);
final t = await _storage.read(key: 'refresh_token');
await _storage.deleteAll();       // on sign-out
```

`flutter_secure_storage` uses the Android Keystore and the iOS Keychain. Keychain items **survive app uninstall** on iOS — clear them on first launch if you don't want that:

```dart
if (prefs.getBool('installed') != true) {
  await _storage.deleteAll();
  await prefs.setBool('installed', true);
}
```

## Never do these

```dart
// ❌ key in source
const openAiKey = 'sk-proj-...';
// ❌ key in an asset .env — assets/ is just a zip entry in the APK
// ❌ trusting a client-side role check for authorization
if (user.isAdmin) { deleteEverything(); }   // enforce on the server
// ❌ logging tokens or PII
print('token: $token');
```

Client-side checks are UX, not security. Every permission decision must be re-enforced server-side (RLS policy, endpoint check).

## Build hardening

```bash
flutter build apk --release --obfuscate --split-debug-info=build/symbols
flutter build ipa --release --obfuscate --split-debug-info=build/symbols
```

Keep `build/symbols` — you need it to de-obfuscate crash reports (`flutter symbolize`).

Android `android/app/build.gradle.kts` release block:

```kotlin
buildTypes {
    release {
        isMinifyEnabled = true
        isShrinkResources = true
        proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
}
```

Obfuscation raises the cost of reverse engineering; it does not make a hardcoded key safe.

## Network

- HTTPS only. Never disable certificate validation, not even "temporarily for testing" — that line always ships.
- Android: keep `usesCleartextTraffic` false; add a `network_security_config.xml` if you must allow a local dev host, and only in the debug manifest.
- **Certificate pinning** for high-value apps (banking, payments):

```dart
(dio.httpClientAdapter as IOHttpClientAdapter).createHttpClient = () {
  final ctx = SecurityContext(withTrustedRoots: false);
  ctx.setTrustedCertificatesBytes(pemBytes);
  return HttpClient(context: ctx);
};
```

Pin to an intermediate CA or pin two certificates (current + next), and ship a remote kill-switch — a pinned cert that expires bricks every installed app.

## Biometric lock

```bash
flutter pub add local_auth
```

```dart
final auth = LocalAuthentication();
final ok = await auth.authenticate(
  localizedReason: 'تأكيد هويتك للمتابعة',
  options: const AuthenticationOptions(biometricOnly: false, stickyAuth: true),
);
```

Biometrics gate access to a locally stored secret — they are not a login. The server still needs a real token. Always provide a passcode fallback (`biometricOnly: false`).

Android needs `<uses-permission android:name="android.permission.USE_BIOMETRIC"/>` and `FlutterFragmentActivity` instead of `FlutterActivity`. iOS needs `NSFaceIDUsageDescription`.

## Permissions

Request the minimum, at the moment of use, with an explanation first.

```dart
final status = await Permission.camera.request();
if (status.isPermanentlyDenied) await openAppSettings();
```

Every iOS permission needs a purpose string in `Info.plist` written in the user's language — Apple rejects vague ones ("لالتقاط صورة للبلاغ" not "we need camera access"). Remove any permission you no longer use; unexplained permissions cause store rejections.

## Data at rest

- Do not write PII to an unencrypted local DB. Encrypt with SQLCipher, or store only ids locally and fetch details.
- Clear all local data on sign-out: secure storage, local DB, image cache.
- Disable screenshots on sensitive screens if required:
  Android — `FLAG_SECURE` via a platform channel or the `no_screenshot` package. iOS has no equivalent flag; blur on `AppLifecycleState.inactive` instead.

## Input & injection

- Validate and sanitize before sending anywhere.
- Never build SQL by string concatenation — use parameters (drift/sqflite both parameterize).
- Never render untrusted HTML in a `WebView` without sanitizing; disable JS if not needed, and restrict `navigationDelegate` to allowed hosts.
- Validate deep-link parameters — a deep link is untrusted input from anywhere on the internet.

## Root / jailbreak & tampering

`flutter_jailbreak_detection` or Play Integrity can detect a compromised device, but every check is bypassable. Use it as a signal (log it, raise fraud scoring server-side), never as the only defense.

## Pre-release review

- [ ] No secret in source, assets, or `--dart-define`
- [ ] Server enforces every authorization rule; client checks are cosmetic
- [ ] RLS / security rules written and tested as a non-owner user
- [ ] Tokens in secure storage; cleared on sign-out
- [ ] `--obfuscate --split-debug-info` on release builds; symbols archived
- [ ] No `print`/`debugPrint` of tokens, emails, or bodies in release (`avoid_print` lint on)
- [ ] Keystore, `key.properties`, service-account JSON out of git — check `git log` history too
- [ ] Only necessary permissions, each with a localized purpose string
- [ ] Dependencies reviewed: `flutter pub outdated`, and check that each package is maintained
- [ ] Privacy policy matches what the app actually collects (required by both stores)
