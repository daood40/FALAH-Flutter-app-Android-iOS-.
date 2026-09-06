/// عقودُ التصفّح والوكيل والجدولة والنشر.
library;

import '../../core/network/api_client.dart' show Result;
import '../entities/content.dart';
import '../entities/schedule.dart';

abstract interface class ContentRepository {
  /// بحثٌ في القرآن. **لا يُرسَل متنٌ ولا يُقبل** — يُعاد ما في القاعدة.
  Future<Result<List<AyahHit>>> searchQuran(String q, {int limit});

  Future<Result<List<HadithHit>>> searchHadith(String q, {int limit});

  Future<Result<List<HadithChapter>>> chapters(String book);

  Future<Result<List<HadithHit>>> chapterHadiths(String book, int chapter);

  /// المصادرُ وحالُ تراخيصها — إسنادٌ يراه المستخدمُ لا وعدٌ في وثيقة.
  Future<Result<List<ContentSource>>> sources();
}

/// الوكيل: **سؤالٌ واحدٌ في كلِّ مرّة، ولا يولّد نصًّا.**
///
/// أسئلتُه تُحدِّد *الاختيار* لا *النصّ*: أيُّ سورة، أيُّ رقم، أيُّ تصميم.
/// ثم يأخذ من القاعدة ما اجتاز الفحوص. وليس نموذجًا لغويًّا، ولا يخرج شيءٌ
/// من محتوى المستخدم إلى أيِّ مزوّدٍ خارجيّ.
abstract interface class AgentRepository {
  /// يعيد السؤالَ التالي، أو الخطّةَ حين تكتمل الإجابات.
  Future<Result<AgentStep>> ask(Map<String, dynamic> answers);

  /// يبني المشروعَ من إجاباتٍ مكتملة. يعيد رقمَ المشروع وعددَ ما أُضيف.
  Future<Result<AgentBuilt>> build(Map<String, dynamic> answers);
}

class AgentStep {
  const AgentStep({
    required this.done,
    required this.answers,
    required this.progress,
    required this.stepIndex,
    required this.stepTotal,
    this.questionId = '',
    this.question,
    this.why,
    this.options = const [],
    this.plan,
    this.preview,
  });

  final bool done;
  final String questionId;
  final String? question;

  /// «لماذا يُسأل هذا؟» — بنصّه من الخادم. الوكيلُ يشرح اختياراته.
  final String? why;
  final List<AgentOption> options;
  final Map<String, dynamic> answers;
  final double progress;
  final int stepIndex;
  final int stepTotal;

  /// الخطّةُ النهائيّة — تظهر حين `done`.
  final Map<String, dynamic>? plan;

  /// معاينةٌ تتغيّر مع كلِّ إجابة، حين تكفي الإجاباتُ لاختيار نصّ.
  final Map<String, dynamic>? preview;
}

class AgentOption {
  const AgentOption({required this.value, required this.label, this.hint});
  final String value;
  final String label;

  /// تلميحٌ من الخادم (المقاسُ مثلًا) — يُعرض ولا يُؤلَّف.
  final String? hint;
}

class AgentBuilt {
  const AgentBuilt({required this.projectId, required this.added});
  final int projectId;

  /// **ما أُضيف قد يقلّ عمّا خُطِّط**: ما لم يجتز الفحصَ لحظةَ الإضافة
  /// يُترك ولا يُستبدل بشيء. فيُعرض العددان معًا ولا يُدَّعى الاكتمال.
  final int added;
}

abstract interface class ScheduleRepository {
  Future<Result<List<Schedule>>> list();

  Future<Result<Schedule>> create({
    required int projectId,
    required String kind,
    required String title,
    required Recurrence recurrence,
    required String tz,
    required int atMinute,
    int? dayOf,
  });

  Future<Result<void>> setStatus(int id, ScheduleStatus status);

  Future<Result<void>> delete(int id);
}

abstract interface class PublishRepository {
  /// كلُّ المنصّات بحالتها — المنفَّذُ وغيرُ المنفَّذ معًا.
  Future<Result<List<PublishProvider>>> providers();

  Future<Result<List<PublishAccount>>> accounts();

  /// يربط حسابًا. **السرُّ يذهب مرّةً ولا يعود** — ولا يُحفظ في العميل.
  Future<Result<PublishAccount>> connect({
    required String provider,
    required String secret,
    required String label,
  });

  Future<Result<void>> disconnect(int id);
}
