/// طبقةُ الشبكة — نقطةٌ واحدةٌ يمرّ منها كلُّ طلب.
///
/// العميلُ القديم كان يفتقد ثلاثةَ أشياء كشفها التدقيق، وكلُّها هنا:
///
///   ١ · **مهلة** — `fetch` بلا مهلةٍ يُجمّد الواجهةَ إلى الأبد إن علّقت
///       الشبكة. هنا مهلتان: للاتّصال وللاستقبال.
///   ٢ · **تصنيفُ رموز الحالة** — كان ٤٠١ و٤٠٣ و٤٢٩ و٥٠٠ رسالةً واحدة،
///       فيقرأ المستخدمُ «لا اتصال» وسببُ العطب انتهاءُ جلسته. هنا لكلٍّ
///       صنفُه في `Failure`.
///   ٣ · **إلغاء** — الخروجُ من الشاشة يُلغي طلبَها فلا يعود ردٌّ إلى
///       ودجةٍ زالت.
///
/// والجلسةُ كعكةٌ `HttpOnly` كما يفرضها الخادم: تُحفظ في جرّةٍ على القرص
/// فتنجو من إغلاق التطبيق، ولا تمرّ بشيفرة Dart إطلاقًا.
library;

import 'dart:io';
import 'dart:math';

import 'package:cookie_jar/cookie_jar.dart';
import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';

import '../config/env.dart';
import '../errors/failure.dart';
import '../logging/logger.dart';

/// معرّفُ الطلب: يُولَّد هنا ويُرسل في `X-Request-Id`، فيُطابَق بسجلّ
/// الخادم عند التشخيص. ستّةَ عشرَ محرفًا ستّةَ عشريًّا — كما `audit.py`.
String newRequestId() {
  final r = Random.secure();
  return List.generate(8, (_) => r.nextInt(256).toRadixString(16).padLeft(2, '0'))
      .join();
}

/// ما يُعيده النداء: إمّا بيانات وإمّا `Failure`. لا استثناءاتٌ تتسرّب.
sealed class Result<T> {
  const Result();
  R fold<R>(R Function(Failure) onError, R Function(T) onOk) =>
      switch (this) {
        Err<T>(:final failure) => onError(failure),
        Ok<T>(:final value) => onOk(value),
      };
}

final class Ok<T> extends Result<T> {
  const Ok(this.value);
  final T value;
}

final class Err<T> extends Result<T> {
  const Err(this.failure);
  final Failure failure;
}

typedef Json = Map<String, dynamic>;

class ApiClient {
  ApiClient(this._dio);

  final Dio _dio;

  /// يبني عميلًا كاملًا: جرّةُ كعكٍ دائمة، ومهلٌ، وترويسات.
  ///
  /// [cookieDir] مسارُ الجرّة على الجهاز. في الاختبار يُمرَّر مجلّدٌ مؤقّت.
  static Future<ApiClient> create({required String cookieDir}) async {
    Env.assertValid();
    final dio = Dio(BaseOptions(
      baseUrl: Env.apiBaseUrl,
      connectTimeout: Env.connectTimeout,
      receiveTimeout: Env.receiveTimeout,
      // لا نرمي على رموز الحالة: نصنّفها بأنفسنا في `_classify`
      validateStatus: (_) => true,
      headers: const {
        // حارسُ CSRF في الخادم يشترطها، ولا يرسلها نموذجُ HTML من موقعٍ آخر
        'X-FALAH': '1',
        'Accept': 'application/json',
      },
    ));
    final jar = PersistCookieJar(storage: FileStorage(cookieDir));
    dio.interceptors.add(CookieManager(jar));
    return ApiClient(dio);
  }

  Future<Result<Json>> get(String path,
          {Json? query, CancelToken? cancel}) =>
      _send(() => _dio.get(path,
          queryParameters: query,
          cancelToken: cancel,
          options: _opts()));

  Future<Result<Json>> post(String path,
          {Json? body, CancelToken? cancel}) =>
      _send(() => _dio.post(path,
          data: body ?? const <String, dynamic>{},
          cancelToken: cancel,
          options: _opts()));

  Options _opts() => Options(headers: {'X-Request-Id': newRequestId()});

  Future<Result<Json>> _send(Future<Response<dynamic>> Function() run) async {
    try {
      final r = await run();
      final rid = r.requestOptions.headers['X-Request-Id'] as String?;
      final code = r.statusCode ?? 0;
      if (code >= 200 && code < 300) {
        final d = r.data;
        if (d is Map) return Ok(Map<String, dynamic>.from(d));
        // ردٌّ ناجحٌ بجسمٍ غيرِ متوقَّع: لا يُبتلع، يُصنَّف
        Log.error('response.shape', {'code': code, 'request_id': rid});
        return const Err(UnknownFailure('ردٌّ غيرُ مفهوم من الخادم'));
      }
      return Err(_classify(code, r, rid));
    } on DioException catch (e) {
      return Err(_fromDio(e));
    } catch (e) {
      Log.error('request.unexpected', {'type': e.runtimeType.toString()});
      return const Err(UnknownFailure());
    }
  }

  /// رسالةُ الخادم العربية إن وُجدت — وإلا نصٌّ افتراضيٌّ لكل صنف.
  /// ولا يُعرض جسمُ الردّ كما هو: قد يحمل تفصيلًا لا يخصّ المستخدم.
  Failure _classify(int code, Response<dynamic> r, String? rid) {
    final data = r.data;
    final msg = (data is Map && data['error'] is String)
        ? data['error'] as String
        : null;
    Log.warn('response.error', {'code': code, 'request_id': rid});

    return switch (code) {
      401 => UnauthorizedFailure(msg ?? 'انتهت الجلسة — سجّل الدخول من جديد'),
      403 => ForbiddenFailure(msg ?? 'لا صلاحية لهذه العملية'),
      404 => NotFoundFailure(msg ?? 'غير موجود'),
      413 => PayloadTooLargeFailure(msg ?? 'المحتوى أكبر من الحدّ المسموح'),
      429 => RateLimitFailure(
          msg ?? 'محاولاتٌ كثيرةٌ — انتظر قليلًا',
          retryAfter: _retryAfter(r),
          requestId: rid,
        ),
      // الخادمُ يردّ ٤٠٠ لأخطاء النطاق، ومنها تجاوزُ الحصّة. تُفرَّق
      // بالنصّ لأن علاجَها مختلف: الحصّةُ ترقيةٌ لا إعادةُ محاولة.
      400 || 409 || 422 => _isQuota(msg)
          ? QuotaFailure(msg!, requestId: rid)
          : ValidationFailure(msg ?? 'طلبٌ غيرُ صالح', requestId: rid),
      >= 500 => ServerFailure(msg ?? 'خطأ في الخادم', rid),
      _ => UnknownFailure(msg ?? 'حدث خطأ غير متوقّع', rid),
    };
  }

  static bool _isQuota(String? m) =>
      m != null &&
      (m.contains('خطّة') || m.contains('الحصّة') || m.contains('حصّتك'));

  static Duration? _retryAfter(Response<dynamic> r) {
    final v = r.headers.value('retry-after');
    final s = int.tryParse(v ?? '');
    return s == null ? null : Duration(seconds: s);
  }

  Failure _fromDio(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return const TimeoutFailure();
      case DioExceptionType.connectionError:
        return const NetworkFailure();
      case DioExceptionType.cancel:
        // إلغاءٌ مقصود: ليس عطبًا يُعرض
        return const UnknownFailure('أُلغي الطلب');
      case DioExceptionType.badCertificate:
        return const NetworkFailure('شهادةُ الخادم غيرُ موثوقة');
      default:
        if (e.error is SocketException) return const NetworkFailure();
        Log.error('dio.unhandled', {'type': e.type.name});
        return const UnknownFailure();
    }
  }
}
