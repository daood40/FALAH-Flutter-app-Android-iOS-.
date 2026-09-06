/// تنفيذُ عقد المصادقة على مسارات `/app/*` القائمة.
///
/// لا يُعاد بناءُ شيءٍ في الخادم: هذه المساراتُ الثمانيةُ موجودةٌ ومختبَرةٌ
/// منذ P1.2، والعميلُ الجديدُ يستهلكها كما هي.
library;

import '../../core/errors/failure.dart';
import '../../core/network/api_client.dart';
import '../../domain/entities/user.dart';
import '../../domain/repositories/auth_repository.dart';
import '../dto/mappers.dart';

class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl(this._api);

  final ApiClient _api;

  @override
  Future<Result<User?>> currentUser() async {
    final r = await _api.get('/app/me');
    return r.fold(
      (f) => Err(f),
      (j) {
        final u = j['user'];
        // `{"user": null}` جوابٌ صحيحٌ معناه: زائرٌ بلا جلسة. ليس خطأً،
        // ولا يُعرض له شيء — الموجّهُ وحده يقرّر إلى أين يذهب.
        if (u is! Map) return const Ok(null);
        try {
          return Ok(Mappers.user(Map<String, dynamic>.from(u)));
        } on FormatException catch (e) {
          return Err(UnknownFailure(e.message));
        }
      },
    );
  }

  @override
  Future<Result<User>> login({
    required String email,
    required String password,
  }) =>
      _withUser('/app/login', {'email': email, 'password': password});

  @override
  Future<Result<User>> register({
    required String email,
    required String password,
    required String name,
    String? watermark,
    String? invite,
    String? referral,
  }) =>
      _withUser('/app/register', {
        'email': email,
        'password': password,
        'name': name,
        // الحقولُ الاختياريّةُ تُرسل فارغةً لا تُحذف: الخادمُ يقرؤها
        // بـ`b[key]` فيرمي `KeyError` على الناقص — وهو سلوكٌ محفوظٌ عمدًا
        'watermark': watermark ?? '',
        'invite': invite ?? '',
        'ref': (referral ?? '').toUpperCase(),
      });

  Future<Result<User>> _withUser(String path, Map<String, dynamic> body) async {
    final r = await _api.post(path, body: body);
    return r.fold(
      (f) => Err(f),
      (j) {
        final u = j['user'];
        if (u is! Map) return const Err(UnknownFailure('ردٌّ بلا مستخدم'));
        try {
          return Ok(Mappers.user(Map<String, dynamic>.from(u)));
        } on FormatException catch (e) {
          return Err(UnknownFailure(e.message));
        }
      },
    );
  }

  @override
  Future<Result<void>> logout() async =>
      (await _api.post('/app/logout')).fold((f) => Err(f), (_) => const Ok(null));

  @override
  Future<Result<void>> requestPasswordReset(String email) async =>
      (await _api.post('/app/password/forgot', body: {'email': email}))
          .fold((f) => Err(f), (_) => const Ok(null));

  @override
  Future<Result<void>> resetPassword({
    required String token,
    required String password,
  }) async =>
      (await _api.post('/app/password/reset',
              body: {'token': token, 'password': password}))
          .fold((f) => Err(f), (_) => const Ok(null));

  @override
  Future<Result<User>> updateWatermark(String watermark) =>
      _withUser('/app/profile', {'watermark': watermark});

  @override
  Future<Result<void>> deleteAccount({required String confirm}) async =>
      (await _api.post('/app/account/delete', body: {'confirm': confirm}))
          .fold((f) => Err(f), (_) => const Ok(null));
}
