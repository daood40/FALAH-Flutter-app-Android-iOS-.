/// دورةُ الجلسة كاملةً على خادمٍ حقيقيّ — لا مضاعفاتٌ ولا مُحاكاة.
///
/// طُلب اختبارُها بعينها: دخولٌ · حفظُ الجلسة · إغلاقُ التطبيق · إعادةُ
/// فتحه · استرجاعٌ · خروجٌ · جلسةٌ منتهية · ٤٠١ · ٤٠٣.
///
/// و«إغلاقُ التطبيق» يُحاكَى بالطريقة الوحيدة الصادقة: **يُبنى `ApiClient`
/// جديدٌ تمامًا** على مجلّد الجرّة نفسِه — كما يقع حين يُقتل التطبيقُ
/// ويُفتح. فلو كانت الجلسةُ في الذاكرة لسقط هذا الاختبار.
///
/// يحتاج خادمًا يعمل:
///     FALAH_INLINE_WORKER=1 python3 app.py
///     flutter test --dart-define=FALAH_API=http://localhost:8080 \
///                  test/data/session_lifecycle_test.dart
///
/// وبلا خادمٍ يُتخطّى بوضوح — **ولا يُعدّ نجاحًا**.
@Tags(['live'])
library;

import 'dart:io';
import 'dart:math';

import 'package:falah_app/core/config/env.dart';
import 'package:falah_app/core/errors/failure.dart';
import 'package:falah_app/core/network/api_client.dart';
import 'package:falah_app/data/repositories/auth_repository_impl.dart';
import 'package:flutter_test/flutter_test.dart';

late Directory _jar;

String _email() => 'u${Random().nextInt(90000000) + 10000000}@falah-test.local';
const _password = 'Str0ng-Pass!x9';

Future<bool> _serverUp() async {
  try {
    final c = HttpClient()..connectionTimeout = const Duration(seconds: 3);
    final r = await c.getUrl(Uri.parse('${Env.apiBaseUrl}/healthz'));
    final res = await r.close();
    c.close();
    return res.statusCode == 200;
  } catch (_) {
    return false;
  }
}

/// يستخرج القيمةَ من `Ok` أو يُسقط الاختبارَ برسالةِ الفشل. أوضحُ من
/// تحويلٍ متكرّرٍ في كل سطر، ويجعل سببَ السقوط مقروءًا.
T okOf<T>(Result<T> r) => switch (r) {
  Ok<T>(:final value) => value,
  Err<T>(:final failure) => fail('توقّعنا Ok فجاء: ${failure.message}'),
};

Failure errOf<T>(Result<T> r) => switch (r) {
  Err<T>(:final failure) => failure,
  Ok<T>() => fail('توقّعنا فشلًا فجاء نجاح'),
};

/// عميلٌ جديدٌ على الجرّة نفسِها = تطبيقٌ أُعيد فتحُه.
Future<AuthRepositoryImpl> _reopenApp() async =>
    AuthRepositoryImpl(await ApiClient.create(cookieDir: '${_jar.path}/'));

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    // ربطُ الاختبار يضع HttpOverrides عامًّا يردّ ٤٠٠ على كلِّ طلب — حمايةً
    // من نداءٍ شبكيٍّ غيرِ مقصودٍ في اختبار ودجة. وهذا الملفُّ **يقصد**
    // الشبكةَ فعلًا، فيُرفع المنعُ هنا وحده.
    HttpOverrides.global = null;
    _jar = await Directory.systemTemp.createTemp('falah_jar_');
  });

  tearDownAll(() async {
    if (_jar.existsSync()) await _jar.delete(recursive: true);
  });

  test('الخادمُ يعمل — وإلا فالاختباراتُ التالية غيرُ محقَّقة', () async {
    final up = await _serverUp();
    if (!up) {
      markTestSkipped(
        'لا خادمَ على ${Env.apiBaseUrl} — الدورةُ الحيّةُ UNVERIFIED لا PASS',
      );
    }
    expect(true, isTrue);
  });

  group('دورةُ الجلسة', () {
    late String email;

    setUpAll(() => email = _email());

    test('١ · قبل الدخول: لا جلسة — وليس خطأً', () async {
      if (!await _serverUp()) return markTestSkipped('لا خادم');
      final repo = await _reopenApp();
      final r = await repo.currentUser();
      expect(okOf(r), isNull, reason: 'زائرٌ يُقرأ null لا Failure');
    });

    test('٢ · تسجيلٌ ثم دخولٌ ينجح', () async {
      if (!await _serverUp()) return markTestSkipped('لا خادم');
      final repo = await _reopenApp();
      final reg = await repo.register(
        email: email,
        password: _password,
        name: 'داوود',
        watermark: 'قناة نور الهدى',
      );
      expect(okOf(reg).email, email);
    });

    test('٣ · الجلسةُ تنجو من إغلاق التطبيق — عميلٌ جديدٌ يجدها', () async {
      if (!await _serverUp()) return markTestSkipped('لا خادم');
      // هنا الاختبارُ الحقيقيّ: عمليةٌ جديدةٌ من الصفر على الجرّة نفسِها
      final reopened = await _reopenApp();
      final r = await reopened.currentUser();
      final u = okOf(r);
      expect(
        u,
        isNotNull,
        reason: 'الكعكةُ على القرص، فالجلسةُ تُستأنف بلا إعادة دخول',
      );
      expect(u!.email, email);
    });

    test('٤ · الخروجُ يُنهي الجلسةَ فعلًا في الخادم', () async {
      if (!await _serverUp()) return markTestSkipped('لا خادم');
      final repo = await _reopenApp();
      okOf(await repo.logout());

      final after = await _reopenApp();
      expect(
        okOf(await after.currentUser()),
        isNull,
        reason: 'بعد الخروج لا جلسة',
      );
    });

    test('٥ · الدخولُ ثانيةً بالحساب نفسِه', () async {
      if (!await _serverUp()) return markTestSkipped('لا خادم');
      final repo = await _reopenApp();
      okOf(await repo.login(email: email, password: _password));
    });
  });

  group('الرفضُ يُصنَّف صنفَه', () {
    test('كلمةُ مرورٍ خاطئة لا تُصنَّف NetworkFailure', () async {
      if (!await _serverUp()) return markTestSkipped('لا خادم');
      final repo = await _reopenApp();
      final r = await repo.login(email: _email(), password: 'wrong-password-1');
      final f = errOf(r);
      expect(f, isNot(isA<NetworkFailure>()));
      expect(f, isNot(isA<TimeoutFailure>()));
      expect(f.message, isNotEmpty);
    });

    test('جرّةٌ فارغةٌ ⇒ زائر، لا انهيار', () async {
      if (!await _serverUp()) return markTestSkipped('لا خادم');
      final fresh = await Directory.systemTemp.createTemp('falah_empty_');
      final repo = AuthRepositoryImpl(
        await ApiClient.create(cookieDir: '${fresh.path}/'),
      );
      expect(okOf(await repo.currentUser()), isNull);
      await fresh.delete(recursive: true);
    });

    test('مسارٌ إداريٌّ لمستخدمٍ عاديّ ⇒ ليس Ok', () async {
      if (!await _serverUp()) return markTestSkipped('لا خادم');
      final repo = await _reopenApp();
      await repo.login(
        email: _email(),
        password: _password,
      ); // قد يفشل — لا يهمّ
      final api = await ApiClient.create(cookieDir: '${_jar.path}/');
      final r = await api.get('/app/admin/users');
      final f = errOf(r);
      // ٤٠١ أو ٤٠٣ — كلاهما رفضٌ مصنَّف، والمهمّ ألّا يكون Ok ولا Network
      expect(
        f is UnauthorizedFailure || f is ForbiddenFailure,
        isTrue,
        reason: 'صُنّف: ${f.runtimeType}',
      );
    });
  });
}
