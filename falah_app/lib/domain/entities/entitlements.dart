/// ما يملكه المستخدمُ الآن — خطّتُه وحدودُها وما استهلكه منها.
///
/// **مصدرُ الحقيقة هو الخادمُ لا هذا الكائن.** يُعرض هنا ليعرف المستخدمُ
/// ما بقي له، ولا يُبنى عليه منعٌ: من عدّل التطبيقَ ليُظهر زرًّا مقفلًا
/// يصطدم بالخادم الذي يفحص الحصّةَ **عند قبول العمل** لا عند عرض الزرّ.
library;

class Entitlements {
  const Entitlements({
    required this.plan,
    required this.planName,
    required this.status,
    required this.expiresAt,
    required this.renews,
    required this.limits,
    required this.used,
    required this.left,
    required this.features,
    required this.period,
  });

  /// `free` · `creator` · `studio` …
  final String plan;
  final String planName;

  /// `active` · `expired` · `canceled`
  final String status;

  /// تاريخُ الانتهاء — `null` يعني بلا انتهاء (الخطّةُ المجّانية).
  final DateTime? expiresAt;
  final bool renews;

  /// الحدُّ لكلِّ مقياس: `cards` · `videos` · `projects`
  final Map<String, int> limits;
  final Map<String, int> used;
  final Map<String, int> left;

  /// ما تتيحه الخطّة: النسبُ والتصاميم والصبغاتُ وحدُّ السلسلة…
  final Map<String, dynamic> features;

  /// مفتاحُ الفترة التي تُحسب فيها الحصّة — يتغيّر فتُصفَّر.
  final String period;

  bool get isFree => plan == 'free';
  bool get isActive => status == 'active';

  int leftOf(String metric) => left[metric] ?? 0;
  int limitOf(String metric) => limits[metric] ?? 0;

  /// النسبُ المتاحةُ في هذه الخطّة — تُقرأ من `features` لا تُخمَّن.
  List<String> get ratios =>
      (features['ratios'] as List?)?.cast<String>() ?? const ['square'];

  List<String> get designs =>
      (features['designs'] as List?)?.cast<String>() ?? const ['parch'];

  int get seriesMax => (features['series_max'] as int?) ?? 1;
}
