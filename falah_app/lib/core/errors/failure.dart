/// تصنيفُ الأخطاء — واحدٌ لكل ما يمكن أن يقع، ولا `Exception` عارية.
///
/// القاعدةُ التي يقوم عليها هذا الملفّ: **ما يراه المستخدمُ غيرُ ما يُسجَّل.**
/// الخادمُ يردّ برسالةٍ عربيّةٍ آمنةٍ في `error`، وهي وحدها ما يُعرض. أمّا
/// نوعُ الخطأ ورمزُ الحالة و`requestId` فللتشخيص لا للعرض.
///
/// ولماذا `sealed`؟ لأن `switch` عليها يفشل في الترجمة إن نُسي نوعٌ — فلا
/// يمكن أن يُضاف صنفُ خطأٍ جديدٌ وتبقى شاشةٌ لا تعرف كيف تعرضه.
library;

sealed class Failure {
  const Failure(this.message, {this.requestId});

  /// رسالةٌ صالحةٌ للعرض. لا مسارات، ولا أسماءَ جداول، ولا أثرَ نداء.
  final String message;

  /// معرّفُ الطلب — يُعرض في شاشة الخطأ ليُقتبس عند الإبلاغ، ويُطابَق
  /// بسجلّ الخادم. ليس سرًّا، ولا يحمل معلومةً عن المستخدم.
  final String? requestId;

  @override
  String toString() => '$runtimeType($message)';
}

/// لا شبكةَ أصلًا — الجهازُ غيرُ متّصل أو المضيفُ لا يُحلّ.
final class NetworkFailure extends Failure {
  const NetworkFailure([super.message = 'لا اتصال بالشبكة']);
}

/// اتّصلَ ولم يردّ في الوقت المسموح.
final class TimeoutFailure extends Failure {
  const TimeoutFailure([super.message = 'انتهت المهلة قبل أن يردّ الخادم']);
}

/// ٤٠١ — لا جلسةَ أو انتهت. **الشاشةُ تعود إلى الدخول، ولا تقول «لا اتصال».**
///
/// هذا التمييزُ بعينه هو العيبُ الذي رصده التدقيق في العميل القديم: كان
/// انتهاءُ الجلسة يظهر للمستخدم رسالةَ شبكة.
final class UnauthorizedFailure extends Failure {
  const UnauthorizedFailure([
    super.message = 'انتهت الجلسة — سجّل الدخول من جديد',
  ]) : super(requestId: null);
}

/// ٤٠٣ — الجلسةُ صحيحةٌ والعمليةُ ممنوعة.
final class ForbiddenFailure extends Failure {
  const ForbiddenFailure([super.message = 'لا صلاحية لهذه العملية']);
}

/// ٤٠٤ — غيرُ موجود. وقد يعني «ليس لك»: الخادمُ يوحّد الردّين عمدًا.
final class NotFoundFailure extends Failure {
  const NotFoundFailure([super.message = 'غير موجود']);
}

/// ٤٠٠ · ٤٠٩ · ٤٢٢ — الطلبُ خاطئٌ أو يخالف قاعدةَ نطاق.
final class ValidationFailure extends Failure {
  const ValidationFailure(super.message, {super.requestId});
}

/// ٤١٣ — الجسمُ أكبرُ من الحدّ.
final class PayloadTooLargeFailure extends Failure {
  const PayloadTooLargeFailure([
    super.message = 'المحتوى أكبر من الحدّ المسموح',
  ]);
}

/// ٤٢٩ — تجاوزُ حدِّ المعدّل. `retryAfter` من الترويسة إن أرسلها الخادم.
final class RateLimitFailure extends Failure {
  const RateLimitFailure(super.message, {this.retryAfter, super.requestId});
  final Duration? retryAfter;
}

/// تجاوزُ حصّةِ الخطّة — لا يُصلحه الانتظار بل الترقية.
final class QuotaFailure extends Failure {
  const QuotaFailure(super.message, {super.requestId});
}

/// ٥xx — عطبٌ في الخادم. لا تفصيلَ للمستخدم.
final class ServerFailure extends Failure {
  const ServerFailure([super.message = 'خطأ في الخادم', String? requestId])
    : super(requestId: requestId);
}

/// ما لم يُصنَّف. وجودُه ليس عذرًا لترك خطأٍ بلا صنف.
final class UnknownFailure extends Failure {
  const UnknownFailure([
    super.message = 'حدث خطأ غير متوقّع',
    String? requestId,
  ]) : super(requestId: requestId);
}

/// يحوّل ما يخرج من `AsyncValue.error` إلى `Failure` مصنَّف.
///
/// مزوِّداتُ Riverpod ترمي الخطأَ كـ`Object`، وشاشاتُنا تعرض `Failure`.
/// وبلا هذه الدالّة يكتب كلُّ `error:` تحويلًا يدويًّا — فيُنسى في واحدةٍ
/// منها فتظهر `Instance of 'DioException'` للمستخدم.
Failure asFailure(Object e) =>
    e is Failure ? e : UnknownFailure(e.toString().split('\n').first);
