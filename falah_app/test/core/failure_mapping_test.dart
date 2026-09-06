/// تصنيفُ رموز الحالة — العيبُ الأوّلُ الذي وجده التدقيق في العميل القديم.
///
/// كان كلُّ ما ليس ٢xx رسالةً واحدة، فيقرأ المستخدمُ «لا اتصال» وسببُ
/// العطب انتهاءُ جلسته. هذه الاختباراتُ تمنع رجوعَ ذلك: لكلِّ رمزٍ صنفٌ،
/// ولكلِّ صنفٍ علاجٌ مختلفٌ في الواجهة.
library;

import 'package:dio/dio.dart';
import 'package:falah_app/core/errors/failure.dart';
import 'package:falah_app/core/network/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

/// خادمٌ وهميٌّ داخل dio نفسِه — بلا شبكةٍ ولا منفذ. يُختبر التصنيفُ
/// لا النقل، فلا حاجةَ إلى مقبسٍ حقيقيّ.
Dio _dioReturning(int code, {Object? body, Map<String, List<String>>? headers}) {
  final dio = Dio(BaseOptions(validateStatus: (_) => true));
  dio.httpClientAdapter = _FakeAdapter(code, body, headers);
  return dio;
}

class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter(this.code, this.body, this.headers);
  final int code;
  final Object? body;
  final Map<String, List<String>>? headers;

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<List<int>>? stream,
      Future<void>? cancelFuture) async {
    return ResponseBody.fromString(
      body == null ? '' : _encode(body!),
      code,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
        ...?headers,
      },
    );
  }

  static String _encode(Object b) =>
      b is String ? b : '{"error": "${(b as Map)['error']}"}';

  @override
  void close({bool force = false}) {}
}

Future<Failure> _failureFor(int code,
    {String? error, Map<String, List<String>>? headers}) async {
  final api = ApiClient(_dioReturning(code,
      body: error == null ? null : {'error': error}, headers: headers));
  final r = await api.get('/app/me');
  return switch (r) {
    Err(:final failure) => failure,
    Ok() => throw StateError('توقّعنا فشلًا لرمز $code'),
  };
}

void main() {
  group('تصنيفُ رموز الحالة', () {
    test('٤٠١ ⇒ UnauthorizedFailure — لا NetworkFailure', () async {
      final f = await _failureFor(401);
      expect(f, isA<UnauthorizedFailure>());
      // العيبُ القديمُ بعينه: كان يظهر كخطأ شبكة
      expect(f, isNot(isA<NetworkFailure>()));
    });

    test('٤٠٣ ⇒ ForbiddenFailure', () async {
      expect(await _failureFor(403), isA<ForbiddenFailure>());
    });

    test('٤٠٤ ⇒ NotFoundFailure', () async {
      expect(await _failureFor(404), isA<NotFoundFailure>());
    });

    test('٤١٣ ⇒ PayloadTooLargeFailure', () async {
      expect(await _failureFor(413), isA<PayloadTooLargeFailure>());
    });

    test('٥٠٠ ⇒ ServerFailure', () async {
      expect(await _failureFor(500), isA<ServerFailure>());
    });

    test('٥٠٣ ⇒ ServerFailure كذلك', () async {
      expect(await _failureFor(503), isA<ServerFailure>());
    });
  });

  group('٤٢٩ وحدُّ المعدّل', () {
    test('يُصنَّف RateLimitFailure', () async {
      expect(await _failureFor(429), isA<RateLimitFailure>());
    });

    test('يقرأ Retry-After ثوانيَ', () async {
      final f = await _failureFor(429, headers: {
        'retry-after': ['30']
      }) as RateLimitFailure;
      expect(f.retryAfter, const Duration(seconds: 30));
    });

    test('وبلا الترويسة يبقى null لا صفرًا', () async {
      final f = await _failureFor(429) as RateLimitFailure;
      expect(f.retryAfter, isNull);
    });
  });

  group('الحصّةُ تُفرَّق عن خطأ التحقّق', () {
    // كلاهما ٤٠٠ من الخادم، وعلاجُهما مختلف: الحصّةُ ترقيةٌ لا إعادةُ
    // محاولة. فالتفريقُ بالنصّ ضرورةٌ لا زخرفة.
    test('نصُّ الخطّة ⇒ QuotaFailure', () async {
      final f = await _failureFor(400,
          error: 'هذا المقاس غير متاح في خطّة «مجّاني»');
      expect(f, isA<QuotaFailure>());
    });

    test('«الحصّة» ⇒ QuotaFailure', () async {
      expect(await _failureFor(400, error: 'انتهت الحصّة لهذا الشهر'),
          isA<QuotaFailure>());
    });

    test('خطأٌ عاديّ ⇒ ValidationFailure', () async {
      expect(await _failureFor(400, error: 'حقل ناقص: email'),
          isA<ValidationFailure>());
    });
  });

  group('رسالةُ الخادم', () {
    test('تُعرض كما هي حين ترد', () async {
      final f = await _failureFor(403, error: 'لا صلاحية لهذه العملية');
      expect(f.message, 'لا صلاحية لهذه العملية');
    });

    test('وإلا فنصٌّ افتراضيٌّ مفهوم — لا رمزٌ عارٍ', () async {
      final f = await _failureFor(500);
      expect(f.message, isNotEmpty);
      expect(f.message, isNot(contains('500')));
    });
  });

  group('لا تسريبَ في الرسالة', () {
    test('لا أثرَ نداءٍ ولا مسارَ ملفّ', () async {
      for (final code in [400, 401, 403, 404, 413, 429, 500, 503]) {
        final f = await _failureFor(code);
        expect(f.message, isNot(contains('Traceback')));
        expect(f.message, isNot(contains('.py')));
        expect(f.message, isNot(contains('/home/')));
        expect(f.message, isNot(contains('sqlite')));
      }
    });
  });
}
