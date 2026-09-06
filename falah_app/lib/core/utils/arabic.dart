/// أدواتُ العرض العربيّ — الأرقامُ الهنديّةُ وأسماءُ الخيارات.
///
/// الأرقامُ تُحوَّل يدويًّا لا بـ`intl`: المطلوبُ الأرقامُ العربيّةُ الهنديّة
/// (٠١٢٣) في كلِّ الأحوال، لا ما تختاره لغةُ الجهاز — فقد يكون الجهازُ
/// إنجليزيًّا والتطبيقُ عربيًّا.
library;

const String _digits = '٠١٢٣٤٥٦٧٨٩';

/// يحوّل أرقامَ أيّ نصٍّ إلى العربيّة الهنديّة، ويترك ما عداها.
String arabicNum(Object? value) {
  final s = value?.toString() ?? '';
  final b = StringBuffer();
  for (final r in s.runes) {
    // ٠x30–٠x39 هي 0–9 اللاتينيّة
    if (r >= 0x30 && r <= 0x39) {
      b.write(_digits[r - 0x30]);
    } else {
      b.writeCharCode(r);
    }
  }
  return b.toString();
}

/// أسماءُ النسب كما يعرفها الخادم — `square` · `story` · `wide`.
String ratioLabel(String ratio) => switch (ratio) {
  'square' => 'مربّع',
  'story' => 'طولي',
  'wide' => 'عريض',
  _ => ratio,
};

/// أسماءُ التصاميم — `parch` · `night` · `clean`.
String skinLabel(String skin) => switch (skin) {
  'parch' => 'رقّ',
  'night' => 'ليلي',
  'clean' => 'نقي',
  _ => skin,
};

/// نوعُ النصّ — `quran` · `hadith` · `enc`.
String kindLabel(String kind) => switch (kind) {
  'quran' => 'قرآن',
  'hadith' => 'حديث',
  'enc' => 'موسوعة',
  _ => kind,
};

/// تاريخٌ مختصرٌ بالعربية بلا اعتمادٍ على لغة الجهاز.
String shortDate(DateTime d) =>
    '${arabicNum(d.day)}/${arabicNum(d.month)}/${arabicNum(d.year)}';
