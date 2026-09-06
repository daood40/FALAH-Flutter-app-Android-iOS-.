/// إعدادُ البيئة — يُحقن وقتَ البناء، ولا يُكتب في الشيفرة.
///
///     flutter build apk --release --dart-define=FALAH_API=https://api.falah.example
///
/// ولماذا `--dart-define` لا ملفٌّ في `assets`؟ لأن الأصولَ تُحزَم في الـAPK
/// ويمكن استخراجُها بفكِّ ضغطٍ بسيط. و`--dart-define` يُخبز في الشيفرة
/// المترجَمة — وهو ليس مخبأً كذلك، ولهذا **لا يوضع هنا سرٌّ بحال**.
///
/// القاعدة: هنا عناوينُ وأعلامٌ فقط. لا مفاتيحَ API، ولا أسرارَ OAuth، ولا
/// اعتمادات. كلُّ سرٍّ يبقى في الخادم، والعميلُ يحمل جلسةً لا مفتاحًا.
library;

enum Flavor { dev, staging, prod }

final class Env {
  const Env._();

  /// عنوانُ الخادم. الافتراضيُّ محلّيٌّ للتطوير على المحاكي:
  /// `10.0.2.2` هو مضيفُ الجهاز من داخل محاكي أندرويد.
  static const String apiBaseUrl = String.fromEnvironment(
    'FALAH_API',
    defaultValue: 'http://10.0.2.2:8080',
  );

  static const String _flavor = String.fromEnvironment(
    'FALAH_FLAVOR',
    defaultValue: 'dev',
  );

  static Flavor get flavor => switch (_flavor) {
        'prod' => Flavor.prod,
        'staging' => Flavor.staging,
        _ => Flavor.dev,
      };

  static bool get isProd => flavor == Flavor.prod;

  /// مهلةُ الاتّصال ومهلةُ الاستقبال. الثانيةُ أطولُ لأن التصدير يُصيَّر
  /// في الخادم: بطاقةٌ ≈ ٣ث، فمهلةٌ قصيرةٌ تقطع عملًا ناجحًا.
  static const Duration connectTimeout = Duration(seconds: 15);
  static const Duration receiveTimeout = Duration(seconds: 45);

  /// **حارسٌ لا تحذير.** إن بُني للإنتاج على عنوانٍ غيرِ مشفَّر تُرمى
  /// الاستثناءُ عند الإقلاع بدل أن يُشحن تطبيقٌ يرسل الجلسةَ في العراء.
  static void assertValid() {
    if (isProd && !apiBaseUrl.startsWith('https://')) {
      throw StateError(
        'FALAH_API يجب أن يبدأ بـhttps في الإنتاج — الحاليّ: $apiBaseUrl',
      );
    }
    if (apiBaseUrl.isEmpty) {
      throw StateError('FALAH_API فارغ — مرّره بـ--dart-define');
    }
  }
}
