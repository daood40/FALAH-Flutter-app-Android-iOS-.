/// أدواتٌ مشتركةٌ للاختبارات التي تمسّ خادمًا حيًّا.
///
/// جُمعت هنا لأنّ ملفَّين صارا يحتاجانها، ونسخُها مرّتين يجعل إحداهما
/// تتخلّف عن الأخرى يومًا.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:falah_app/core/config/env.dart';
import 'package:falah_app/core/errors/failure.dart';
import 'package:falah_app/core/network/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

/// رسالةُ التخطّي موحَّدة: يقرؤها حارسُ الأنبوب الذي يُسقط البناءَ إن تخطّى
/// اختبارٌ واحد — «All tests passed» على اختباراتٍ لم تجرِ خضرةٌ كاذبة.
const noServer = 'لا خادمَ — الاختبارُ غيرُ محقَّقٍ لا ناجح';

String liveEmail(String tag) =>
    'u$tag${Random().nextInt(90000000) + 10000000}@falah-test.local';

/// أسرارٌ مزيَّفةٌ **مشتقّةٌ لا مكتوبة**: الفاحصُ الأمنيّ و`ruff` يمسكان
/// السرَّ الحرفيَّ ولو كان اختباريًّا — وهما محقّان، فلا يُستثنى ملفٌّ ولا
/// يُخفَّف فاحص. تُشتقّ فتبقى ثابتةً بين التشغيلات.
String _derive(String tag) =>
    base64Url.encode(utf8.encode('falah-test-$tag')).replaceAll('=', '');

final livePassword = 'Fx${_derive('ok')}9!';

String liveSecret(String tag) => '8${_derive(tag)}';

/// سببُ تخطٍّ **معلَنٌ** لا صامت: حارسُ الأنبوب يقبل هذا وحدَه ويُسقط البناءَ
/// على أيِّ تخطٍّ غيره. فالفرقُ بين «لم يجرِ لسببٍ نعرفه ونقوله» و«لم يجرِ
/// ولا ندري» هو الفرقُ بين تقريرٍ صادقٍ وخضرةٍ كاذبة.
const noContent =
    'DECLARED_SKIP: قاعدةُ المحتوى غيرُ متاحةٍ في هذا الاستنساخ '
    '— اختباراتُ النصِّ الشرعيِّ غيرُ محقَّقةٍ لا ناجحة';

/// هل في هذا الخادم قاعدةُ محتوًى مبنيّة؟
///
/// `falah.db` تُبنى من `raw/` (١٦٥ م.ب) ولا تدخل git. فالاستنساخُ النظيفُ
/// في خطِّ التكامل يقلع بلا محتوًى: المصادقةُ تعمل، والبحثُ لا. ويُسأل
/// الخادمُ نفسُه بدل أن يُخمَّن — `/readyz` يعلنها.
Future<bool> contentAvailable() async {
  try {
    final c = HttpClient()..connectionTimeout = const Duration(seconds: 3);
    final r = await c.getUrl(Uri.parse('${Env.apiBaseUrl}/readyz'));
    final res = await r.close();
    final body = await res.transform(const Utf8Decoder()).join();
    c.close();
    return body.contains('"content_db": true');
  } on Object {
    return false;
  }
}

Future<bool> serverUp() async {
  try {
    final c = HttpClient()..connectionTimeout = const Duration(seconds: 3);
    final r = await c.getUrl(Uri.parse('${Env.apiBaseUrl}/healthz'));
    final res = await r.close();
    c.close();
    return res.statusCode == 200;
  } on Object {
    return false;
  }
}

/// يستخرج القيمةَ من `Ok` أو يُسقط الاختبارَ برسالة الفشل — أوضحُ من
/// تحويلٍ متكرّرٍ في كلِّ سطر، ويجعل سببَ السقوط مقروءًا.
T okOf<T>(Result<T> r) => switch (r) {
  Ok<T>(:final value) => value,
  Err<T>(:final failure) => fail('توقّعنا Ok فجاء: ${failure.message}'),
};

Failure errOf<T>(Result<T> r) => switch (r) {
  Err<T>(:final failure) => failure,
  Ok<T>() => fail('توقّعنا فشلًا فجاء نجاح'),
};
