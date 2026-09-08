---
name: flutter-networking-api
description: HTTP and REST in Flutter — dio setup, interceptors, auth token refresh, retries, timeouts, JSON serialization with freezed/json_serializable, typed error handling, file upload/download, WebSockets and GraphQL. Use when calling any API, or when the user says "API", "ربط بالسيرفر", "http", "dio", "json", "رفع ملف".
---

# Networking & APIs

## Client setup (dio)

```bash
flutter pub add dio
flutter pub add pretty_dio_logger
```

```dart
Dio buildDio() {
  final dio = Dio(BaseOptions(
    baseUrl: Env.apiBaseUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 20),
    sendTimeout: const Duration(seconds: 30),
    headers: {'Accept': 'application/json'},
    validateStatus: (s) => s != null && s < 500,   // handle 4xx yourself
  ));

  dio.interceptors.addAll([
    AuthInterceptor(),
    RetryInterceptor(dio),
    if (kDebugMode) PrettyDioLogger(requestBody: true, responseBody: false),
  ]);
  return dio;
}
```

Always set timeouts. The default is "wait forever", which on a bad network looks like a frozen app.

## Auth interceptor with refresh

```dart
class AuthInterceptor extends Interceptor {
  Completer<void>? _refreshing;

  @override
  void onRequest(RequestOptions o, RequestInterceptorHandler h) async {
    final token = await TokenStore.access();
    if (token != null) o.headers['Authorization'] = 'Bearer $token';
    h.next(o);
  }

  @override
  void onError(DioException e, ErrorInterceptorHandler h) async {
    if (e.response?.statusCode != 401) return h.next(e);

    // single-flight refresh: concurrent 401s wait for one refresh
    if (_refreshing != null) {
      await _refreshing!.future;
    } else {
      _refreshing = Completer<void>();
      try {
        await TokenStore.refresh();
        _refreshing!.complete();
      } catch (err) {
        _refreshing!.completeError(err);
        await AuthService.signOut();
        return h.next(e);
      } finally {
        _refreshing = null;
      }
    }

    try {
      final clone = await Dio().fetch(e.requestOptions
        ..headers['Authorization'] = 'Bearer ${await TokenStore.access()}');
      return h.resolve(clone);
    } catch (_) {
      return h.next(e);
    }
  }
}
```

The single-flight guard matters: without it, ten parallel requests hitting 401 trigger ten refreshes and the server invalidates your refresh token.

## Retry with backoff

Retry only idempotent requests (GET/PUT/DELETE) and only on network errors or 5xx / 429. Never retry a POST that creates something unless you send an idempotency key.

```dart
const delays = [Duration(seconds: 1), Duration(seconds: 2), Duration(seconds: 5)];
```

Add jitter (`+ Random().nextInt(300) ms`) so a fleet of clients doesn't retry in lockstep. Honour `Retry-After` on 429.

## Typed errors

Never let `DioException` reach the UI.

```dart
sealed class AppFailure {
  const AppFailure(this.message);
  final String message;
}
class NetworkFailure extends AppFailure { const NetworkFailure() : super('لا يوجد اتصال بالإنترنت'); }
class TimeoutFailure extends AppFailure { const TimeoutFailure() : super('انتهت مهلة الاتصال'); }
class UnauthorizedFailure extends AppFailure { const UnauthorizedFailure() : super('انتهت الجلسة، سجّل الدخول من جديد'); }
class ValidationFailure extends AppFailure { const ValidationFailure(super.m, this.fields); final Map<String, String> fields; }
class ServerFailure extends AppFailure { const ServerFailure() : super('خطأ في الخادم، حاول لاحقاً'); }

AppFailure mapDioError(DioException e) => switch (e.type) {
  DioExceptionType.connectionError || DioExceptionType.unknown => const NetworkFailure(),
  DioExceptionType.connectionTimeout ||
  DioExceptionType.receiveTimeout ||
  DioExceptionType.sendTimeout => const TimeoutFailure(),
  _ => switch (e.response?.statusCode) {
      401 || 403 => const UnauthorizedFailure(),
      422 => ValidationFailure('تحقق من البيانات', _fields(e.response)),
      _ => const ServerFailure(),
    },
};
```

Log the technical detail (`e.message`, status, endpoint) to your crash reporter; show the user the localized sentence.

## JSON models

```bash
flutter pub add freezed_annotation json_annotation
flutter pub add -d freezed json_serializable build_runner
```

```dart
@freezed
class Report with _$Report {
  const factory Report({
    required String id,
    required String title,
    @Default('open') String status,
    @JsonKey(name: 'created_at') required DateTime createdAt,
    @JsonKey(name: 'user_id') String? userId,
  }) = _Report;

  factory Report.fromJson(Map<String, dynamic> json) => _$ReportFromJson(json);
}
```

```bash
dart run build_runner watch --delete-conflicting-outputs
```

Never hand-parse with `json['x'] as String` scattered across the codebase — one API change then breaks in twenty places instead of one. Make every field that the server may omit nullable or defaulted; a missing key on a non-nullable field is a runtime crash in production only.

## Repository

```dart
class ReportApi {
  ReportApi(this._dio);
  final Dio _dio;

  Future<List<Report>> list({int page = 1}) async {
    try {
      final res = await _dio.get('/reports', queryParameters: {'page': page});
      return (res.data['data'] as List)
          .map((e) => Report.fromJson(e as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }
}
```

## Cancellation

```dart
final token = CancelToken();
_dio.get('/search', queryParameters: {'q': q}, cancelToken: token);
// on new keystroke / dispose:
token.cancel('superseded');
```

Cancel in-flight search requests and cancel everything in `dispose()`, or a slow response will call `setState` on a dead widget.

Debounce user-typed search by ~350 ms before firing.

## Upload & download with progress

```dart
final form = FormData.fromMap({
  'file': await MultipartFile.fromFile(path, filename: 'photo.jpg'),
  'report_id': id,
});
await _dio.post('/upload', data: form,
    onSendProgress: (sent, total) => onProgress(sent / total));

await _dio.download(url, savePath,
    onReceiveProgress: (r, t) => onProgress(t > 0 ? r / t : 0));
```

Compress images before upload; a 6 MB photo over a mobile network is a failed request waiting to happen.

## WebSockets

```dart
final ch = WebSocketChannel.connect(Uri.parse('wss://api.example.com/ws'));
ch.stream.listen(onData, onError: _reconnect, onDone: _reconnect);
ch.sink.add(jsonEncode({'type': 'subscribe', 'room': id}));
// dispose:
await ch.sink.close();
```

Implement reconnect with exponential backoff and re-subscribe after reconnect. Pause the socket when the app is backgrounded (`AppLifecycleState.paused`).

## Checklist

- [ ] Timeouts set on every client
- [ ] Errors mapped to a sealed failure type with localized messages
- [ ] Tokens refreshed once, not per-request
- [ ] Retries only where safe, with backoff + jitter
- [ ] Requests cancelled on dispose
- [ ] No API keys in the client (see `flutter-security`)
- [ ] Responses parsed through generated models
