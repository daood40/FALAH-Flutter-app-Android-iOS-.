/// رموزُ التصميم — قيمةٌ واحدةٌ لكلِّ معنى، ولا لونَ خامٍ في شاشة.
///
/// هذه القيمُ مأخوذةٌ من الواجهة القائمة (`falah-app.html`) كي لا يختلف
/// المظهرُ بين العميلين: المستخدمُ نفسُه قد يفتح الويبَ اليومَ والتطبيقَ
/// غدًا، فيجب أن يرى المنتجَ نفسَه لا اثنين متشابهين.
///
/// والقاعدة: **من احتاج لونًا أخذه من هنا.** اللونُ الخامُ في ودجةٍ يعني
/// أن الوضعَ الفاتحَ سينكسر عندها ولن يُكتشف إلا بالصدفة.
library;

import 'package:flutter/material.dart';

final class Space {
  const Space._();
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 14;
  static const double lg = 22;
  static const double xl = 34;
  static const double xxl = 52;
}

final class Radii {
  const Radii._();
  static const double sm = 8;
  static const double md = 14;
  static const double lg = 22;
  static const BorderRadius card = BorderRadius.all(Radius.circular(md));
  static const BorderRadius pill = BorderRadius.all(Radius.circular(999));
}

/// لمساتُ الفرشاة: الذهبُ للتأكيد، والرقُّ للبطاقة، والليلُ للخلفية.
final class Palette {
  const Palette._();

  // ── الهويّة: ثابتةٌ في الوضعين، فهي علامةٌ لا سطح ──
  static const Color gold = Color(0xFFC9A247);
  static const Color goldSoft = Color(0xFFE0C989);
  static const Color parchment = Color(0xFFF1E7CE);
  static const Color ink = Color(0xFF2A2216);

  // ── الوضع الداكن ──
  static const Color darkBg = Color(0xFF070D0B);
  static const Color darkSurface = Color(0xFF0C1613);
  static const Color darkLine = Color(0xFF1E2E28);
  static const Color darkText = Color(0xFFF1E7CE);
  static const Color darkMuted = Color(0xFF9C8C62);

  // ── الوضع الفاتح ──
  // ليست عكسًا آليًّا للداكن: الورقُ الفاتحُ يميل إلى دفء الرقّ لا إلى
  // الأبيض الناصع، فيبقى النصُّ العربيُّ مريحًا للقراءة الطويلة.
  static const Color lightBg = Color(0xFFFBF8F1);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightLine = Color(0xFFE3DBC9);
  static const Color lightText = Color(0xFF1F1B12);
  static const Color lightMuted = Color(0xFF6B6047);

  // ── الحالات ──
  static const Color danger = Color(0xFFC86B5E);
  static const Color dangerSoft = Color(0xFFE2A79C);
  static const Color success = Color(0xFF5E9C7A);
  static const Color warn = Color(0xFFC9922F);
}

final class Fonts {
  const Fonts._();

  /// النصُّ الشرعيُّ العامّ وواجهةُ التطبيق.
  static const String amiri = 'Amiri';

  /// المصحفُ برسمه — خطٌّ مختلفٌ عن Amiri العاديّ، ولا يُستبدل به:
  /// علاماتُ الوقف والتشكيلُ العثمانيُّ لا تُرسم إلا به.
  static const String quran = 'AmiriQuran';
}
