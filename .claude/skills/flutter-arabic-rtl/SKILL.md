---
name: flutter-arabic-rtl
description: Arabic and RTL support in Flutter — localization with ARB files, runtime language switching, RTL-correct layout and icons, Arabic fonts, number and date formatting, plurals and gender. Use for any bilingual or Arabic-first app, or when the user says "عربي", "ترجمة", "اتجاه", "RTL", "localization", "l10n", "تعدد اللغات".
---

# Arabic & RTL in Flutter

## Setup

`pubspec.yaml`:

```yaml
dependencies:
  flutter_localizations:
    sdk: flutter
  intl: any

flutter:
  generate: true
```

`l10n.yaml` at the project root:

```yaml
arb-dir: lib/l10n
template-arb-file: app_ar.arb
output-localization-file: app_localizations.dart
output-class: AppLocalizations
nullable-getter: false
```

Use the Arabic file as the template when the app is Arabic-first — it keeps the source of truth in the language you actually design in.

`lib/l10n/app_ar.arb`:

```json
{
  "@@locale": "ar",
  "appTitle": "منصة البلاغات",
  "welcome": "مرحباً {name}",
  "@welcome": { "placeholders": { "name": { "type": "String" } } },
  "reportsCount": "{count, plural, =0{لا توجد بلاغات} =1{بلاغ واحد} =2{بلاغان} few{{count} بلاغات} many{{count} بلاغاً} other{{count} بلاغ}}",
  "@reportsCount": { "placeholders": { "count": { "type": "int" } } },
  "lastUpdated": "آخر تحديث {date}",
  "@lastUpdated": { "placeholders": { "date": { "type": "DateTime", "format": "yMMMd" } } }
}
```

Arabic has six plural forms — `=0`, `=1`, `=2`, `few` (3–10), `many` (11–99), `other`. Never build a plural with `if (n == 1)`; it is wrong in Arabic.

`lib/l10n/app_en.arb`:

```json
{
  "@@locale": "en",
  "appTitle": "Reports Platform",
  "welcome": "Welcome {name}",
  "reportsCount": "{count, plural, =0{No reports} =1{One report} other{{count} reports}}",
  "lastUpdated": "Last updated {date}"
}
```

Generated on `flutter pub get` / `flutter gen-l10n`.

## Wiring

```dart
MaterialApp(
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  supportedLocales: AppLocalizations.supportedLocales,
  locale: ref.watch(localeProvider),      // null = follow the device
  localeResolutionCallback: (device, supported) {
    if (device == null) return const Locale('ar');
    return supported.firstWhere((l) => l.languageCode == device.languageCode,
        orElse: () => const Locale('ar'));
  },
)
```

Text direction is then automatic — `Directionality` is set from the locale. Do not hardcode `TextDirection.rtl` at the app root; it breaks the English mode.

Usage: `final l = AppLocalizations.of(context); Text(l.welcome(name));`

**No user-visible string is ever a Dart literal.** That includes error messages, validation messages, snackbars, and dialog buttons.

## Runtime language switch

```dart
class LocaleController extends Notifier<Locale?> {
  @override
  Locale? build() {
    final code = ref.read(prefsProvider).getString('locale');
    return code == null ? null : Locale(code);
  }

  Future<void> set(Locale? l) async {
    state = l;
    final p = ref.read(prefsProvider);
    l == null ? await p.remove('locale') : await p.setString('locale', l.languageCode);
  }
}
final localeProvider = NotifierProvider<LocaleController, Locale?>(LocaleController.new);
```

Changing `MaterialApp.locale` rebuilds and flips direction instantly — no restart needed.

## RTL-correct layout

| Never use | Use instead |
|---|---|
| `EdgeInsets.only(left: 16)` | `EdgeInsetsDirectional.only(start: 16)` |
| `Alignment.centerLeft` | `AlignmentDirectional.centerStart` |
| `BorderRadius.only(topLeft:)` | `BorderRadiusDirectional.only(topStart:)` |
| `Positioned(left: 8)` | `PositionedDirectional(start: 8)` |
| `Icons.arrow_back` | `Icons.arrow_back` is auto-mirrored by Flutter; custom arrows need `Transform.flip` |
| `MainAxisAlignment` with manual reversing | leave it — `Row` already follows direction |

Padding with `EdgeInsets.symmetric(horizontal:)` is direction-safe. `EdgeInsets.all` is safe.

Mirror a custom directional asset:

```dart
Transform.flip(
  flipX: Directionality.of(context) == TextDirection.rtl,
  child: const Icon(Icons.trending_flat),
)
```

Do **not** mirror: logos, media playback controls, clocks, or numbers.

## Mixed content

An Arabic UI containing an English name, a URL, or a phone number renders with the Unicode bidi algorithm. When a string starts with a Latin character inside an Arabic paragraph, punctuation can jump. Force the paragraph direction per string:

```dart
Text(value, textDirection: intl.Bidi.detectRtlDirectionality(value)
    ? TextDirection.rtl : TextDirection.ltr)
```

Phone numbers and codes should be wrapped in `Directionality(textDirection: TextDirection.ltr, child: ...)`.

Text fields: set `textDirection` and `textAlign` to match the content type — an email field is always LTR even in an Arabic app.

## Fonts

Bundled Roboto has no Arabic glyphs — Arabic falls back to the system font, which differs across devices and looks unpolished.

```yaml
flutter:
  fonts:
    - family: Cairo
      fonts:
        - asset: assets/fonts/Cairo-Regular.ttf
        - asset: assets/fonts/Cairo-SemiBold.ttf
          weight: 600
        - asset: assets/fonts/Cairo-Bold.ttf
          weight: 700
```

Good Arabic UI fonts: **Cairo**, **Tajawal**, **IBM Plex Sans Arabic**, **Noto Kufi Arabic**, **Almarai**. Ship only the weights you use — each weight is ~100–300 KB.

Arabic needs more vertical room than Latin: set `height: 1.6–1.8` in `TextStyle` for body text, or descenders and diacritics clip.

## Numbers, dates, currency

```dart
final ar = NumberFormat.decimalPattern('ar');       // ١٬٢٣٤
final arLatn = NumberFormat.decimalPattern('ar_LY'); // 1,234 — Libya uses Latin digits
final money = NumberFormat.currency(locale: 'ar_LY', symbol: 'د.ل');
final date = DateFormat.yMMMEd('ar').format(dt);     // الاثنين، ٨ سبتمبر ٢٠٢٦
final rel = DateFormat.Hm('ar').format(dt);
```

Choose the digit style deliberately — many Arabic regions (including Libya) use Latin digits in everyday UI; Arabic-Indic digits can feel wrong. Ask, or match your existing app.

Call `initializeDateFormatting('ar')` once at startup if you format dates before the localization delegates load.

Hijri dates need a package (`hijri`); `intl` does not convert calendars.

## Testing RTL

```dart
testWidgets('renders in RTL', (t) async {
  await t.pumpWidget(MaterialApp(
    locale: const Locale('ar'),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: const ReportsScreen(),
  ));
  expect(find.text('البلاغات'), findsOneWidget);
});
```

Manual pass before release: switch the device to Arabic and walk every screen looking for text stuck to the wrong edge, clipped descenders, arrows pointing the wrong way, and overflow — Arabic strings are often 20–30% longer or shorter than English.

## Checklist

- [ ] Zero hardcoded user-facing strings
- [ ] Plurals use ICU `plural`, not `if`
- [ ] `EdgeInsetsDirectional` / `AlignmentDirectional` everywhere
- [ ] Arabic font bundled with `height` set
- [ ] Email/phone/URL fields forced LTR
- [ ] Both languages walked through manually
- [ ] Language choice persisted
