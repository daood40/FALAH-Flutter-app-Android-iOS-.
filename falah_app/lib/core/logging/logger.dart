/// سجلٌّ مبنيٌّ لا `print` — ويحذف الأسرارَ حذفًا لا يستر بنجوم.
///
/// القاعدةُ المأخوذةُ من `falah/audit.py` في الخادم: **الحقلُ المشبوهُ
/// يُحذف بالكامل.** الاستبدالُ بنجومٍ يُبقي الطولَ وموضعَ الحقل، وكلاهما
/// معلومةٌ لمن يقرأ السجلّ. والحذفُ لا يُبقي شيئًا.
///
/// وطبقتان للكشف كما هناك: **الاسمُ** (ما يشبه اسمُه سرًّا) و**الشكلُ**
/// (سلسلةٌ طويلةٌ من محارف الترميز الآمن) — لأن سرًّا قد يُسمّى `data`.
library;

import 'dart:developer' as dev;

enum LogLevel { debug, info, warning, error }

/// أسماءُ الحقول التي لا تُسجَّل قيمتُها أبدًا.
final RegExp _secretName = RegExp(
  r'pass|pwd|secret|token|cookie|session|auth|api_?key|credential|salt|'
  r'hash|signature|receipt|private',
  caseSensitive: false,
);

/// شكلُ السرّ: ٢٤ محرفًا فأكثر من أبجديّة الترميز الآمن، بلا فراغ.
final RegExp _secretShape = RegExp(r'^[A-Za-z0-9_\-+/=]{24,}$');

/// يحذف ما يُشتبه أنه سرّ. يعمل على الخرائط والقوائم في العمق.
Object? scrub(Object? value) {
  if (value is Map) {
    final out = <String, Object?>{};
    value.forEach((k, v) {
      final key = k.toString();
      if (_secretName.hasMatch(key)) return; // يُحذف الحقلُ كلُّه
      out[key] = scrub(v);
    });
    return out;
  }
  if (value is List) return value.map(scrub).toList();
  if (value is String && _secretShape.hasMatch(value)) return null;
  return value;
}

final class Log {
  const Log._();

  static LogLevel minLevel = LogLevel.debug;

  static void _emit(
    LogLevel level,
    String event,
    Map<String, Object?>? fields,
  ) {
    if (level.index < minLevel.index) return;
    final safe =
        scrub(fields ?? const <String, Object?>{}) as Map<String, Object?>;
    final parts = safe.entries
        .where((e) => e.value != null)
        .map((e) => '${e.key}=${e.value}')
        .join(' ');
    dev.log(
      '[${level.name}] $event${parts.isEmpty ? '' : ' $parts'}',
      name: 'falah',
    );
  }

  static void debug(String event, [Map<String, Object?>? f]) =>
      _emit(LogLevel.debug, event, f);
  static void info(String event, [Map<String, Object?>? f]) =>
      _emit(LogLevel.info, event, f);
  static void warn(String event, [Map<String, Object?>? f]) =>
      _emit(LogLevel.warning, event, f);

  /// خطأٌ يستحقّ التتبّع. `error` نفسُه يُمرَّر لا يُسلسَل — فقد يحمل جسمَ
  /// ردٍّ فيه ما لا يُسجَّل.
  static void error(String event, [Map<String, Object?>? f]) =>
      _emit(LogLevel.error, event, f);
}
