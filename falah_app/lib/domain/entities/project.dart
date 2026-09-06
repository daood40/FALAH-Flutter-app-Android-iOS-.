/// المشروعُ وعناصرُه — وحدةُ العمل التي تُصدَّر بطاقاتٍ أو مقطعًا.
library;

/// حالةُ المهمّة في الطابور — الخمسةُ التي يعلنها `falah/jobs.py`.
/// لا تُضاف حالةٌ سادسةٌ في العميل: ما لا يعرفه الخادمُ لا يوجد.
enum JobState {
  queued,
  running,
  done,
  failed,
  canceled;

  static JobState parse(String? s) => switch (s) {
    'queued' => JobState.queued,
    'running' => JobState.running,
    'done' => JobState.done,
    'failed' => JobState.failed,
    'canceled' => JobState.canceled,
    _ => JobState.queued,
  };

  bool get isTerminal => this == done || this == failed || this == canceled;

  String get label => switch (this) {
    queued => 'في الطابور',
    running => 'يُصيَّر',
    done => 'اكتمل',
    failed => 'فشل',
    canceled => 'أُلغي',
  };
}

class Job {
  const Job({
    required this.id,
    required this.state,
    required this.progress,
    this.step,
    this.error,
    this.result,
  });

  final int id;
  final JobState state;

  /// ٠–١٠٠ — يفرضه قيدٌ في القاعدة، فلا يخرج عن المدى.
  final int progress;

  /// وصفُ الخطوة الجارية بالعربية — يُعرض كما هو.
  final String? step;
  final String? error;
  final Map<String, dynamic>? result;
}

class ProjectItem {
  const ProjectItem({
    required this.id,
    required this.kind,
    required this.title,
    required this.checks,
    this.reciter,
    this.drifted = false,
  });

  final int id;

  /// `quran` · `hadith` · `enc`
  final String kind;
  final String title;

  /// كم فحصًا من الخمسة والعشرين اجتازه هذا النصّ. ما دونها لا يُنشر.
  final int checks;
  final String? reciter;

  /// انجرفَ النصُّ عن بصمته المحفوظة — يحتاج قبولًا صريحًا من المستخدم.
  final bool drifted;

  bool get verified => checks >= 25;
}

class Project {
  const Project({
    required this.id,
    required this.title,
    required this.skin,
    required this.ratio,
    required this.itemCount,
    required this.updatedAt,
    this.items = const [],
  });

  final int id;
  final String title;

  /// `night` · `parch` · `clean`
  final String skin;

  /// `square` · `story` · `wide`
  final String ratio;
  final int itemCount;
  final DateTime updatedAt;
  final List<ProjectItem> items;
}
