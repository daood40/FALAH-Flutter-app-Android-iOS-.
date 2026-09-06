/// عقدُ المصادقة — يعرفه النطاقُ ولا يعرف كيف يُنفَّذ.
///
/// الفائدةُ ليست شكليّة: الشاشاتُ تعتمد على هذا العقد، فيُختبر منطقُها
/// بمُنفِّذٍ في الذاكرة بلا خادمٍ ولا شبكة. ولو تغيّر النقلُ يومًا — كعكةٌ
/// إلى رمزٍ حامل — لم تتغيّر شاشةٌ واحدة.
library;

import '../../core/network/api_client.dart' show Result;
import '../entities/user.dart';

abstract interface class AuthRepository {
  /// الجلسةُ الحالية إن وُجدت. `Ok(null)` تعني: لا جلسة — وهذا ليس خطأً.
  Future<Result<User?>> currentUser();

  Future<Result<User>> login({
    required String email,
    required String password,
  });

  Future<Result<User>> register({
    required String email,
    required String password,
    required String name,
    String? watermark,
    String? invite,
    String? referral,
  });

  /// يُنهي الجلسةَ في الخادم ويمحو الكعكةَ من الجهاز.
  Future<Result<void>> logout();

  /// يطلب بريدَ استرجاع. **الردُّ واحدٌ سواءٌ وُجد الحسابُ أو لم يوجد** —
  /// كي لا يصير المسارُ أداةً لمعرفة من له حسابٌ عندنا.
  Future<Result<void>> requestPasswordReset(String email);

  Future<Result<void>> resetPassword({
    required String token,
    required String password,
  });

  Future<Result<User>> updateWatermark(String watermark);

  /// حذفٌ لا رجعةَ فيه: المشاريعُ والصادراتُ والجلساتُ معًا.
  Future<Result<void>> deleteAccount({required String confirm});
}
