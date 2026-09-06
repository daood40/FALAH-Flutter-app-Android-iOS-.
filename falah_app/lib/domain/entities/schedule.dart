/// الجدولةُ والنشر — كيانان يشتركان في قاعدةٍ واحدة: **لا يُدَّعى ما ليس
/// منفَّذًا.**
library;

enum Recurrence {
  once('once', 'مرّةً واحدة'),
  daily('daily', 'يوميًّا'),
  weekly('weekly', 'أسبوعيًّا'),
  monthly('monthly', 'شهريًّا');

  const Recurrence(this.wire, this.label);
  final String wire;
  final String label;

  static Recurrence parse(String? s) => Recurrence.values.firstWhere(
    (r) => r.wire == s,
    // مجهولٌ يُقرأ «مرّةً واحدة» لا «يوميًّا»: الخطأُ إلى الأقلّ أثرًا.
    // جدولٌ يُظنّ مرّةً فيتكرّر أسوأُ من عكسه.
    orElse: () => Recurrence.once,
  );
}

enum ScheduleStatus {
  active('active', 'نشط'),
  paused('paused', 'معلَّق'),
  done('done', 'انتهى');

  const ScheduleStatus(this.wire, this.label);
  final String wire;
  final String label;

  static ScheduleStatus parse(String? s) => ScheduleStatus.values.firstWhere(
    (x) => x.wire == s,
    orElse: () => ScheduleStatus.paused,
  );
}

class Schedule {
  const Schedule({
    required this.id,
    required this.projectId,
    required this.title,
    required this.recurrence,
    required this.tz,
    required this.atMinute,
    required this.status,
    required this.runs,
    required this.failures,
    this.nextRunAt,
    this.lastRunAt,
    this.dayOf,
  });

  final int id;
  final int projectId;
  final String title;
  final Recurrence recurrence;

  /// المنطقةُ الزمنيّةُ **تُحفظ ولا تُحوَّل في العميل**: الخادمُ يحسب الموعدَ
  /// في المنطقة ثم يحوّله، فتبقى «السادسةُ صباحًا» سادسةً عبر التوقيت
  /// الصيفيّ. ولو حسبها العميلُ لانزلقت ساعةً مرّتين في السنة.
  final String tz;

  /// دقائقُ من منتصف الليل في تلك المنطقة.
  final int atMinute;
  final ScheduleStatus status;
  final int runs;
  final int failures;
  final DateTime? nextRunAt;
  final DateTime? lastRunAt;
  final int? dayOf;

  String get timeLabel {
    final h = (atMinute ~/ 60).toString().padLeft(2, '0');
    final m = (atMinute % 60).toString().padLeft(2, '0');
    return '$h:$m';
  }

  /// فشلٌ متكرّرٌ يُعرض — جدولٌ «نشطٌ» يفشل كلَّ مرّةٍ ليس نشطًا عمليًّا.
  bool get failing => failures > 0 && failures >= runs;
}

/// حالةُ منصّةِ نشر — **صريحةٌ لا مستنتَجة.**
enum ProviderStatus {
  ready('ready', 'جاهز'),
  notImplemented('not_implemented', 'غير منفَّذ');

  const ProviderStatus(this.wire, this.label);
  final String wire;
  final String label;

  /// المجهولُ يُقرأ **غيرَ منفَّذ** لا جاهزًا: الخطأُ إلى المنع لا إلى
  /// الادّعاء. ومنصّةٌ جديدةٌ لا يعرفها هذا العميلُ لا تُعرض جاهزةً بالخطأ.
  static ProviderStatus parse(String? s) =>
      s == 'ready' ? ProviderStatus.ready : ProviderStatus.notImplemented;
}

class PublishProvider {
  const PublishProvider({
    required this.key,
    required this.name,
    required this.status,
    required this.auth,
    required this.note,
  });

  final String key;
  final String name;
  final ProviderStatus status;
  final String auth;

  /// سببُ عدم التنفيذ — يُعرض للمستخدم بنصّه من الخادم. وعرضُ المنصّة
  /// معطَّلةً **مع سببها** خيرٌ من إخفائها: من لا يجد إنستغرام يظنّه عطبًا.
  final String note;

  bool get ready => status == ProviderStatus.ready;
}

class PublishAccount {
  const PublishAccount({
    required this.id,
    required this.provider,
    required this.label,
    required this.hint,
    required this.status,
  });

  final int id;
  final String provider;
  final String label;

  /// آخرُ أربعةِ محارفَ فقط. **السرُّ لا يعود من الخادم أبدًا** — لا هنا
  /// ولا في أيِّ حقلٍ آخر، ولا يُحفظ في العميل بحال.
  final String hint;
  final String status;

  bool get active => status == 'active';
}
