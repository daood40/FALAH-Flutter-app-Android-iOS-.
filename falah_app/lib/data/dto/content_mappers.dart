/// محوِّلاتُ التصفّح والوكيل والجدولة والنشر.
///
/// وتُكتب هنا بالقاعدة نفسِها التي فرضها عيبُ العقد السابق: **الأشكالُ
/// مقروءةٌ من ردودٍ حقيقيّةٍ لا مفترَضة**، وكلُّ حقلٍ دفاعيٌّ إلا ما لا
/// يُقبل فيه التساهل.
library;

import '../../domain/entities/content.dart';
import '../../domain/entities/schedule.dart';
import '../../domain/repositories/content_repository.dart';

class ContentMappers {
  const ContentMappers._();

  static int intOf(Object? v, [int fallback = 0]) => switch (v) {
    int i => i,
    num n => n.toInt(),
    String s => int.tryParse(s) ?? fallback,
    _ => fallback,
  };

  static String strOf(Object? v, [String fallback = '']) =>
      v is String ? v : (v == null ? fallback : v.toString());

  static bool boolOf(Object? v) => v == true || v == 1 || v == '1';

  static DateTime? timeOrNull(Object? v) => v == null
      ? null
      : DateTime.fromMillisecondsSinceEpoch(
          intOf(v) * 1000,
          isUtc: true,
        ).toLocal();

  /// يحوّل قائمةً ويتخطّى الصفَّ المعطوبَ **بدل أن يُسقط القائمةَ كلَّها**.
  ///
  /// صفٌّ واحدٌ مخالفُ الشكل لا يجوز أن يُفرغ شاشةَ بحثٍ فيها ثلاثون نتيجة.
  static List<T> list<T>(
    List<dynamic> raw,
    T Function(Map<String, dynamic>) f,
  ) {
    final out = <T>[];
    for (final e in raw) {
      if (e is! Map) continue;
      try {
        out.add(f(Map<String, dynamic>.from(e)));
      } on Object {
        continue;
      }
    }
    return out;
  }

  // ــــــ المحتوى ــــــ

  static AyahHit ayah(Map<String, dynamic> j) => AyahHit(
    surah: intOf(j['surah']),
    ayah: intOf(j['ayah']),
    text: strOf(j['text']),
    surahName: strOf(j['name_ar'], 'سورة ${intOf(j['surah'])}'),
    page: intOf(j['page']),
    // غيابُ `card_ok` يُقرأ **غيرَ مجتاز**: عنصرٌ بلا تقريرٍ لم يُفحص،
    // فلا يُفترض أنه اجتاز. والافتراضُ إلى المنع لا إلى السماح.
    cardOk: boolOf(j['card_ok']),
  );

  static HadithHit hadith(Map<String, dynamic> j) => HadithHit(
    book: strOf(j['code']),
    bookName: strOf(j['name_ar'], strOf(j['code'])),
    number: intOf(j['number_in_book']),
    matn: strOf(j['matn']),
    // **الحكمُ لا يُخمَّن ولا يُملأ فراغُه.** حديثٌ بلا حكمٍ يُعرض بلا حكم.
    grade: strOf(j['grade']),
    narrator: j['narrator_ar'] == null ? null : strOf(j['narrator_ar']),
    cardOk: boolOf(j['card_ok']),
  );

  static HadithChapter chapter(Map<String, dynamic> j) => HadithChapter(
    id: intOf(j['chapter_id']),
    nameAr: strOf(j['name_ar']),
    count: intOf(j['n']),
  );

  /// صفوفُ `/chapter/hadiths` بلا اسم الكتاب — يُحقن من الطلب.
  static HadithHit chapterHadith(Map<String, dynamic> j, String book) =>
      HadithHit(
        book: book,
        bookName: book,
        number: intOf(j['no']),
        matn: strOf(j['matn']),
        grade: strOf(j['grade']),
        // هذا المسارُ لا يُصدر `card_ok`؛ فيُعامَل المعروضُ هنا على أنه
        // قابلٌ للمحاولة، والخادمُ هو من يحجب عند الإضافة. ولا يُدَّعى
        // اجتيازٌ لم يُخبر به.
        cardOk: j.containsKey('card_ok') ? boolOf(j['card_ok']) : true,
      );

  static ContentSource source(Map<String, dynamic> j) => ContentSource(
    code: strOf(j['code']),
    name: strOf(j['name']),
    kind: strOf(j['kind']),
    origin: strOf(j['origin']),
    licenseStatus: strOf(j['license_status'], 'غير محدَّد'),
    enabled: boolOf(j['enabled']),
  );

  // ــــــ الوكيل ــــــ

  /// شكلُ الردِّ **مقروءٌ من الخادم الحيّ**: `question` كائنٌ فيه
  /// `id`/`text`/`why`/`type`/`options[{value,label,hint}]`/`index`/`total`،
  /// و`progress` **كائنٌ** فيه `done`/`total` — لا عددٌ كما ظننّا أوّلًا.
  static AgentStep agentStep(Map<String, dynamic> j) {
    final q = j['question'];
    final qMap = q is Map
        ? Map<String, dynamic>.from(q)
        : const <String, dynamic>{};
    final rawOpts = qMap['options'];
    final prog = j['progress'] is Map
        ? Map<String, dynamic>.from(j['progress'] as Map)
        : const <String, dynamic>{};
    final total = intOf(prog['total'], intOf(qMap['total'], 9));
    final done = intOf(prog['done'], intOf(qMap['index'], 1) - 1);
    return AgentStep(
      done: boolOf(j['done']),
      questionId: strOf(qMap['id']),
      question: qMap['text'] == null ? null : strOf(qMap['text']),
      // «لماذا يُسأل» يُعرض للمستخدم بنصّه من الخادم: سؤالٌ بلا سببٍ يبدو
      // تعنّتًا، وسببٌ نؤلّفه في العميل يفترق عن منطق الخادم.
      why: qMap['why'] == null ? null : strOf(qMap['why']),
      options: rawOpts is List
          ? list(
              rawOpts,
              (m) => AgentOption(
                value: strOf(m['value']),
                label: strOf(m['label'], strOf(m['value'])),
                hint: m['hint'] == null ? null : strOf(m['hint']),
              ),
            )
          : const [],
      answers: j['answers'] is Map
          ? Map<String, dynamic>.from(j['answers'] as Map)
          : <String, dynamic>{},
      progress: total <= 0 ? 0.0 : (done / total).clamp(0.0, 1.0),
      stepIndex: done,
      stepTotal: total,
      plan: j['plan'] is Map
          ? Map<String, dynamic>.from(j['plan'] as Map)
          : null,
      preview: j['preview'] is Map
          ? Map<String, dynamic>.from(j['preview'] as Map)
          : null,
    );
  }

  // ــــــ الجدولة ــــــ

  static Schedule schedule(Map<String, dynamic> j) => Schedule(
    id: intOf(j['id']),
    projectId: intOf(j['project_id']),
    title: strOf(j['title'], 'جدولٌ بلا عنوان'),
    recurrence: Recurrence.parse(j['recurrence'] as String?),
    tz: strOf(j['tz'], 'UTC'),
    atMinute: intOf(j['at_minute']),
    status: ScheduleStatus.parse(j['status'] as String?),
    runs: intOf(j['runs']),
    failures: intOf(j['failures']),
    nextRunAt: timeOrNull(j['next_run_at']),
    lastRunAt: timeOrNull(j['last_run_at']),
    dayOf: j['day_of'] == null ? null : intOf(j['day_of']),
  );

  // ــــــ النشر ــــــ

  static PublishProvider provider(Map<String, dynamic> j) => PublishProvider(
    key: strOf(j['key']),
    name: strOf(j['name'], strOf(j['key'])),
    status: ProviderStatus.parse(j['status'] as String?),
    auth: strOf(j['auth']),
    note: strOf(j['note']),
  );

  static PublishAccount account(Map<String, dynamic> j) => PublishAccount(
    id: intOf(j['id']),
    provider: strOf(j['provider']),
    label: strOf(j['label'], strOf(j['provider'])),
    hint: strOf(j['hint'], '····'),
    status: strOf(j['status'], 'active'),
  );
}
