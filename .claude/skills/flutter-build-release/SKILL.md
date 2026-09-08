---
name: flutter-build-release
description: Build, sign and publish a Flutter app — Android signing and App Bundle, iOS archive and TestFlight, versioning, store listings for Google Play and the App Store, and CI/CD with GitHub Actions or Codemagic. Use when preparing a release, or when the user says "نشر", "رفع التطبيق", "جوجل بلاي", "متجر", "release", "build apk", "app store", "signing".
---

# Building & Releasing

## Versioning

`pubspec.yaml`: `version: 1.4.2+37` → `versionName 1.4.2`, `versionCode 37`.

The build number (`+37`) must **increase on every upload** to either store; it can never be reused or lowered. Bump it in CI (`--build-number=${{ github.run_number }}`) so you cannot forget.

## Android signing

Generate a keystore once — **losing it means you can never update the app** (unless Play App Signing is enabled, which it is by default for new apps; keep the upload key safe regardless):

```bash
keytool -genkey -v -keystore ~/upload-keystore.jks \
  -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

`android/key.properties` (git-ignored):

```properties
storePassword=...
keyPassword=...
keyAlias=upload
storeFile=/absolute/path/upload-keystore.jks
```

`android/app/build.gradle.kts`:

```kotlin
import java.util.Properties

val keystoreProperties = Properties().apply {
    val f = rootProject.file("key.properties")
    if (f.exists()) load(f.inputStream())
}

android {
    signingConfigs {
        create("release") {
            keyAlias = keystoreProperties["keyAlias"] as String?
            keyPassword = keystoreProperties["keyPassword"] as String?
            storeFile = (keystoreProperties["storeFile"] as String?)?.let { file(it) }
            storePassword = keystoreProperties["storePassword"] as String?
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = true
            isShrinkResources = true
        }
    }
}
```

Back up the keystore and its passwords somewhere you will still have in three years.

## Android build

```bash
flutter build appbundle --release \
  --dart-define-from-file=env/prod.json \
  --obfuscate --split-debug-info=build/symbols
# → build/app/outputs/bundle/release/app-release.aab
```

Upload the `.aab` to Play. Build an APK only for direct distribution or testing:

```bash
flutter build apk --release --split-per-abi
```

Also check before uploading: `applicationId` is final and unique, `minSdk` matches your packages' requirements, the app icon and label are set in `AndroidManifest.xml`, and `INTERNET` plus only the permissions you actually use are declared.

## iOS build

Requires macOS + Xcode. On a phone-only setup, use **Codemagic** or GitHub Actions `macos-latest` runners.

```bash
flutter build ipa --release \
  --dart-define-from-file=env/prod.json \
  --obfuscate --split-debug-info=build/symbols
xcrun altool --upload-app -f build/ios/ipa/*.ipa -u "$APPLE_ID" -p "$APP_PASSWORD"
```

In Xcode set: bundle identifier, team, signing certificate + provisioning profile, deployment target, display name, and every `NS*UsageDescription` in `Info.plist` (each one localized in `ar.lproj` too if the app is Arabic).

## Google Play listing

- Short description ≤ 80 chars, full description ≤ 4000.
- Feature graphic 1024×500, icon 512×512, at least 2 phone screenshots (up to 8).
- Content rating questionnaire, target audience, **Data safety form** (must match reality), privacy policy URL (required if you collect anything).
- Provide test credentials in "App access" if the app requires login — a reviewer who cannot log in will reject.
- First release goes to **internal testing** first. Review typically takes hours to a few days; new developer accounts face extra verification and a closed-testing requirement before production.

## App Store listing

- Screenshots for 6.7" and 6.5"/5.5" sizes, icon 1024×1024 with no alpha.
- Privacy nutrition labels, privacy policy URL, support URL.
- Demo account for the reviewer.
- Common rejections: missing purpose strings, broken links, a login wall with no demo account, "app does not offer enough functionality", and using non-Apple payment for digital goods (see `flutter-monetization`).
- Ship to TestFlight first; TestFlight review is lighter than App Store review.

## CI/CD — GitHub Actions (Android)

```yaml
name: release-android
on:
  push:
    tags: ['v*']

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: zulu, java-version: '17' }
      - uses: subosito/flutter-action@v2
        with: { channel: stable, cache: true }

      - run: flutter pub get
      - run: flutter analyze --fatal-infos
      - run: flutter test

      - name: Restore keystore
        run: echo "${{ secrets.KEYSTORE_BASE64 }}" | base64 -d > android/upload.jks
      - name: key.properties
        run: |
          cat > android/key.properties <<EOF
          storePassword=${{ secrets.STORE_PASSWORD }}
          keyPassword=${{ secrets.KEY_PASSWORD }}
          keyAlias=${{ secrets.KEY_ALIAS }}
          storeFile=${{ github.workspace }}/android/upload.jks
          EOF

      - run: echo '${{ secrets.PROD_ENV_JSON }}' > env/prod.json
      - run: flutter build appbundle --release --dart-define-from-file=env/prod.json --build-number=${{ github.run_number }} --obfuscate --split-debug-info=build/symbols

      - uses: r0adkll/upload-google-play@v1
        with:
          serviceAccountJsonPlainText: ${{ secrets.PLAY_SERVICE_ACCOUNT }}
          packageName: com.example.myapp
          releaseFiles: build/app/outputs/bundle/release/app-release.aab
          track: internal

      - uses: actions/upload-artifact@v4
        with: { name: debug-symbols, path: build/symbols }
```

Every secret goes in repository **Settings → Secrets**, never in the workflow file. Always archive `build/symbols` — without it, release crash reports are unreadable.

This workflow means a phone-only developer can ship: push a tag from the GitHub mobile app or from Claude Code, and CI builds, signs and uploads.

## Release checklist

- [ ] Version and build number bumped
- [ ] Release build tested on a **physical** device, not just the emulator
- [ ] Production env/keys used; no dev endpoint left in
- [ ] `flutter analyze` and `flutter test` clean
- [ ] Obfuscation on; symbols archived
- [ ] Crash reporting (Sentry / Crashlytics) wired and verified with a test crash
- [ ] Both languages / RTL checked on the release build
- [ ] Store listing, screenshots, privacy policy, data-safety form complete
- [ ] Demo account provided for reviewers
- [ ] Staged rollout (start at 10–20%) rather than 100% on day one
- [ ] Tag the release in git so you can map a crash to a commit
