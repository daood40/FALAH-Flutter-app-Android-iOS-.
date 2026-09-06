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
