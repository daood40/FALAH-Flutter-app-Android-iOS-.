/// تحويلُ JSON إلى كياناتِ النطاق — الحدُّ الذي لا يعبره `dynamic`.
///
/// كلُّ قراءةٍ هنا **دفاعيّة**: الحقلُ الناقصُ أو المخالفُ للنوع لا يُسقط
/// التطبيق، بل يأخذ قيمةً افتراضيّةً معلومة. وسببُ ذلك أن العميلَ قد يكون
/// أقدمَ من الخادم على جهاز مستخدمٍ لم يُحدِّث — فينبغي أن يبقى عاملًا
/// بما يفهمه لا أن ينهار على حقلٍ زائد.
///
/// وما لا يُقبل فيه التساهلُ يُرمى صراحةً: `id` بلا رقمٍ ليس مشروعًا.
library;

import '../../domain/entities/entitlements.dart';
import '../../domain/entities/project.dart';
import '../../domain/entities/user.dart';

int _int(Object? v, [int fallback = 0]) => switch (v) {
  int i => i,
  num n => n.toInt(),
  String s => int.tryParse(s) ?? fallback,
  _ => fallback,
};

String _str(Object? v, [String fallback = '']) =>
    v is String ? v : (v == null ? fallback : v.toString());

bool _bool(Object? v) => v == true || v == 1 || v == '1';

/// الخادمُ يرسل الزمنَ ثوانيَ منذ الحقبة (كما `store.now()`).
DateTime _time(Object? v) => v == null
    ? DateTime.fromMillisecondsSinceEpoch(0)
    : DateTime.fromMillisecondsSinceEpoch(
        _int(v) * 1000,
        isUtc: true,
      ).toLocal();

DateTime? _timeOrNull(Object? v) => v == null ? null : _time(v);

Map<String, int> _ints(Object? v) {
  if (v is! Map) return const {};
  return {for (final e in v.entries) e.key.toString(): _int(e.value)};
}

class Mappers {
  const Mappers._();

  static User user(Map<String, dynamic> j) {
    final id = _int(j['id'], -1);
    if (id < 0) throw const FormatException('مستخدمٌ بلا معرّف');
    return User(
      id: id,
      email: _str(j['email']),
      name: _str(j['name']),
      watermark: _str(j['watermark']),
      createdAt: _time(j['created_at']),
      // الدورُ غيرُ المعلَن يُقرأ `user` — أضعفُ الأدوار، لا أقواها
      role: _str(j['role'], 'user'),
    );
  }

  static Entitlements entitlements(Map<String, dynamic> j) => Entitlements(
    plan: _str(j['plan'], 'free'),
    planName: _str(j['plan_name'], 'مجّاني'),
    status: _str(j['status'], 'active'),
    expiresAt: _timeOrNull(j['expires_at']),
    renews: _bool(j['renews']),
    limits: _ints(j['limits']),
    used: _ints(j['used']),
    left: _ints(j['left']),
    features: (j['features'] is Map)
        ? Map<String, dynamic>.from(j['features'] as Map)
        : const {},
    period: _str(j['period']),
  );

  static Project project(Map<String, dynamic> j) => Project(
    id: _int(j['id']),
    title: _str(j['title'], 'بلا عنوان'),
    skin: _str(j['skin'], 'parch'),
    ratio: _str(j['ratio'], 'square'),
    itemCount: _int(j['items']),
    updatedAt: _time(j['updated_at']),
  );

  /// المشروعُ المفتوح: العناصرُ داخله قائمةُ خرائط، لا عددٌ.
  static Project projectDetail(Map<String, dynamic> j) {
    final raw = j['project'] is Map
        ? Map<String, dynamic>.from(j['project'] as Map)
        : j;
    final rawItems = (j['items'] ?? raw['items']);
    final items = rawItems is List
        ? rawItems
              .whereType<Map>()
              .map((e) => item(Map<String, dynamic>.from(e)))
              .toList()
        : const <ProjectItem>[];
    return Project(
      id: _int(raw['id']),
      title: _str(raw['title'], 'بلا عنوان'),
      skin: _str(raw['skin'], 'parch'),
      ratio: _str(raw['ratio'], 'square'),
      itemCount: items.length,
      updatedAt: _time(raw['updated_at']),
      items: items,
    );
  }

  static ProjectItem item(Map<String, dynamic> j) => ProjectItem(
    id: _int(j['id']),
    kind: _str(j['kind'], 'quran'),
    title: _str(j['title']),
    checks: _int(j['checks']),
    reciter: j['reciter'] == null ? null : _str(j['reciter']),
    drifted: _bool(j['drifted']),
  );

  static Job job(Map<String, dynamic> j) {
    final raw = j['job'] is Map
        ? Map<String, dynamic>.from(j['job'] as Map)
        : j;
    return Job(
      id: _int(raw['id']),
      state: JobState.parse(raw['state'] as String?),
      // القيدُ في القاعدة يحصره ٠–١٠٠، ونحصره هنا كذلك: طبقتان لا واحدة
      progress: _int(raw['progress']).clamp(0, 100),
      step: raw['step'] == null ? null : _str(raw['step']),
      error: raw['error'] == null ? null : _str(raw['error']),
      result: raw['result'] is Map
          ? Map<String, dynamic>.from(raw['result'] as Map)
          : null,
    );
  }
}
