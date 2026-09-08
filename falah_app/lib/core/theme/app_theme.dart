/// السمتان — فاتحةٌ وداكنة، وكلتاهما مبنيّةٌ من الرموز لا من ألوانٍ خام.
///
/// الوضعُ الفاتحُ ليس عكسًا آليًّا للداكن: الورقُ يميل إلى دفء الرقّ لا إلى
/// الأبيض الناصع، لأن النصَّ العربيَّ يُقرأ طويلًا هنا. وقد كان العميلُ
/// القديمُ داكنًا فقط رغم أن المواصفة تنصّ على «فاتح/داكن/النظام» — وهذه
/// فجوةٌ رصدها التدقيق وتُغلَق هنا.
library;

import 'package:flutter/material.dart';

import 'tokens.dart';

final class AppTheme {
  const AppTheme._();

  static ThemeData get dark => _build(
    brightness: Brightness.dark,
    bg: Palette.darkBg,
    surface: Palette.darkSurface,
    line: Palette.darkLine,
    text: Palette.darkText,
    muted: Palette.darkMuted,
  );

  static ThemeData get light => _build(
    brightness: Brightness.light,
    bg: Palette.lightBg,
    surface: Palette.lightSurface,
    line: Palette.lightLine,
    text: Palette.lightText,
    muted: Palette.lightMuted,
  );

  static ThemeData _build({
    required Brightness brightness,
    required Color bg,
    required Color surface,
    required Color line,
    required Color text,
    required Color muted,
  }) {
    final scheme = ColorScheme(
      brightness: brightness,
      primary: Palette.gold,
      onPrimary: Palette.ink,
      secondary: Palette.goldSoft,
      onSecondary: Palette.ink,
      error: Palette.danger,
      onError: Colors.white,
      surface: surface,
      onSurface: text,
      outline: line,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: bg,
      fontFamily: Fonts.amiri,
      // نصٌّ عربيٌّ يحتاج ارتفاعَ سطرٍ أوسعَ من الافتراضيّ اللاتينيّ:
      // التشكيلُ والمدُّ يمتدّان فوق السطر وتحته، ويتلامسان بدونه.
      textTheme: _text(text, muted),
      appBarTheme: AppBarTheme(
        backgroundColor: bg,
        foregroundColor: text,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontFamily: Fonts.amiri,
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: text,
          height: 1.6,
        ),
      ),
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: Radii.card,
          side: BorderSide(color: line),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: Space.md,
          vertical: Space.md,
        ),
        border: OutlineInputBorder(
          borderRadius: Radii.card,
          borderSide: BorderSide(color: line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: Radii.card,
          borderSide: BorderSide(color: line),
        ),
        focusedBorder: const OutlineInputBorder(
          borderRadius: Radii.card,
          borderSide: BorderSide(color: Palette.gold, width: 1.6),
        ),
        errorBorder: const OutlineInputBorder(
          borderRadius: Radii.card,
          borderSide: BorderSide(color: Palette.danger),
        ),
        hintStyle: TextStyle(color: muted, fontFamily: Fonts.amiri),
        labelStyle: TextStyle(color: muted, fontFamily: Fonts.amiri),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: Palette.gold,
          foregroundColor: Palette.ink,
          // ٤٨ ارتفاعًا: الحدُّ الأدنى لهدفِ لمسٍ مريح — تُوجبه إرشاداتُ
          // الوصولية في المنصّتين، ولا تُقاس بالعين
          minimumSize: const Size.fromHeight(48),
          shape: const RoundedRectangleBorder(borderRadius: Radii.card),
          textStyle: const TextStyle(
            fontFamily: Fonts.amiri,
            fontSize: 17,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: text,
          minimumSize: const Size.fromHeight(48),
          side: BorderSide(color: line),
          shape: const RoundedRectangleBorder(borderRadius: Radii.card),
          textStyle: const TextStyle(fontFamily: Fonts.amiri, fontSize: 16),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: Palette.gold,
          minimumSize: const Size(48, 48),
          textStyle: const TextStyle(fontFamily: Fonts.amiri, fontSize: 15),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: surface,
        contentTextStyle: TextStyle(color: text, fontFamily: Fonts.amiri),
        shape: const RoundedRectangleBorder(borderRadius: Radii.card),
        behavior: SnackBarBehavior.floating,
      ),
      dividerTheme: DividerThemeData(color: line, thickness: 1, space: 1),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: Palette.gold,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: surface,
        shape: const RoundedRectangleBorder(borderRadius: Radii.card),
      ),
    );
  }

  static TextTheme _text(Color text, Color muted) => TextTheme(
    displaySmall: TextStyle(
      fontSize: 28,
      fontWeight: FontWeight.w700,
      color: text,
      height: 1.7,
    ),
    headlineSmall: TextStyle(
      fontSize: 22,
      fontWeight: FontWeight.w700,
      color: text,
      height: 1.7,
    ),
    titleMedium: TextStyle(
      fontSize: 18,
      fontWeight: FontWeight.w700,
      color: text,
      height: 1.7,
    ),
    bodyLarge: TextStyle(fontSize: 17, color: text, height: 1.9),
    bodyMedium: TextStyle(fontSize: 15, color: text, height: 1.9),
    bodySmall: TextStyle(fontSize: 13.5, color: muted, height: 1.8),
    labelLarge: TextStyle(
      fontSize: 15,
      fontWeight: FontWeight.w700,
      color: text,
      height: 1.6,
    ),
  );
}
