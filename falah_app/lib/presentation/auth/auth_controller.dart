/// حالةُ المصادقة — مصدرُ الحقيقة الذي يبني عليه الموجّهُ حرّاسَه.
///
/// **الخادمُ هو مصدرُ الحقيقة، لا هذا الكائن.** ما هنا انعكاسٌ لآخر ردٍّ
/// من `/app/me`، ويُستعمل ليعرف الموجّهُ إلى أين يذهب. ومن عدّل التطبيقَ
/// ليبقى في شاشةٍ محميّةٍ لا يجد فيها شيئًا: كلُّ نداءٍ يُفحص في الخادم.
///
/// وأهمُّ ما فيه `AuthExpired`: حالةٌ مستقلّةٌ عن `AuthAnonymous`. الفرقُ
/// أن الأولى تعني «كنتَ داخلًا وانتهت جلستُك» فتُعرض رسالتُها ويُعاد
/// المستخدمُ إلى الدخول؛ والثانيةُ زائرٌ لم يدخل أصلًا. وخلطُهما هو العيبُ
/// الذي رصده التدقيق في العميل القديم.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/failure.dart';
import '../../core/logging/logger.dart';
import '../../domain/entities/user.dart';
import '../../domain/repositories/auth_repository.dart';
import '../providers.dart';

sealed class AuthState {
  const AuthState();
}

/// لم يُسأل الخادمُ بعد — شاشةُ الإقلاع.
final class AuthUnknown extends AuthState {
  const AuthUnknown();
}

/// لا جلسة، ولم تكن هناك واحدة.
final class AuthAnonymous extends AuthState {
  const AuthAnonymous();
}

/// كانت جلسةٌ وانتهت أو أُبطلت. [reason] يُعرض مرّةً ثم يُمسح.
///
/// تغييرُ الدور في P1.2 **يُبطل الجلسات فورًا**، فهذه الحالةُ تقع فعلًا
/// في الاستعمال العاديّ لا في الحالات النادرة.
final class AuthExpired extends AuthState {
  const AuthExpired(this.reason);
  final String reason;
}

final class AuthSignedIn extends AuthState {
  const AuthSignedIn(this.user);
  final User user;
}

class AuthController extends Notifier<AuthState> {
  AuthRepository get _repo => ref.read(authRepositoryProvider);

  @override
  AuthState build() {
    // لا نداءَ في `build`: الإقلاعُ يستدعي `restore()` صراحةً، فيبقى
    // البناءُ متزامنًا ويُختبر بلا انتظار.
    return const AuthUnknown();
  }

  /// استرجاعُ الجلسة عند الإقلاع. الكعكةُ محفوظةٌ على القرص، فإن كانت
  /// صالحةً عاد المستخدمُ إلى مكانه بلا إعادة دخول.
  Future<void> restore() async {
    final r = await _repo.currentUser();
    state = r.fold(
      (f) => switch (f) {
        // ٤٠١ عند الاسترجاع = كعكةٌ قديمةٌ لم تعد صالحة. ليست عطبًا يُعرض،
        // بل زائرٌ يُطلب منه الدخول.
        UnauthorizedFailure() => const AuthAnonymous(),
        // انقطاعُ الشبكة **ليس** خروجًا: تُبقى الحالةُ مجهولةً كي لا
        // نُخرج مستخدمًا صحيحَ الجلسة لأن الشبكةَ تعثّرت لحظة.
        NetworkFailure() || TimeoutFailure() => const AuthUnknown(),
        _ => const AuthAnonymous(),
      },
      (u) => u == null ? const AuthAnonymous() : AuthSignedIn(u),
    );
    Log.info('auth.restore', {'state': state.runtimeType.toString()});
  }

  Future<Failure?> login(String email, String password) async {
    final r = await _repo.login(email: email, password: password);
    return r.fold((f) => f, (u) {
      state = AuthSignedIn(u);
      return null;
    });
  }

  Future<Failure?> register({
    required String email,
    required String password,
    required String name,
    String? watermark,
    String? invite,
    String? referral,
  }) async {
    final r = await _repo.register(
      email: email,
      password: password,
      name: name,
      watermark: watermark,
      invite: invite,
      referral: referral,
    );
    return r.fold((f) => f, (u) {
      state = AuthSignedIn(u);
      return null;
    });
  }

  /// خروجٌ صريح. **يُمسح الحالُ محلّيًّا حتى لو فشل نداءُ الخادم** — لأن
  /// المستخدمَ طلب الخروجَ وينبغي أن يخرج؛ والجلسةُ ستُبطَل بانتهائها.
  Future<void> logout() async {
    await _repo.logout();
    state = const AuthAnonymous();
    Log.info('auth.logout');
  }

  /// يُنادى من طبقةٍ أخرى حين يردّ الخادمُ ٤٠١ في أثناء الاستعمال —
  /// فيعود المستخدمُ إلى الدخول برسالةٍ مفهومة لا بـ«لا اتصال».
  void expire([String reason = 'انتهت الجلسة — سجّل الدخول من جديد']) {
    if (state is AuthSignedIn) {
      Log.warn('auth.expired');
      state = AuthExpired(reason);
    }
  }

  void clearExpiryNotice() {
    if (state is AuthExpired) state = const AuthAnonymous();
  }

  void updateUser(User u) {
    if (state is AuthSignedIn) state = AuthSignedIn(u);
  }
}

final authControllerProvider = NotifierProvider<AuthController, AuthState>(
  AuthController.new,
);

/// المستخدمُ الحاليُّ أو `null` — يُقرأ في الشاشات بلا `switch` كامل.
final currentUserProvider = Provider<User?>((ref) {
  final s = ref.watch(authControllerProvider);
  return s is AuthSignedIn ? s.user : null;
});
