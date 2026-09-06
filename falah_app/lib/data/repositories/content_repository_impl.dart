/// تنفيذُ عقود التصفّح والوكيل والجدولة والنشر على المسارات القائمة.
library;

import '../../core/network/api_client.dart';
import '../../domain/entities/content.dart';
import '../../domain/entities/schedule.dart';
import '../../domain/repositories/content_repository.dart';
import '../dto/content_mappers.dart';

class ContentRepositoryImpl implements ContentRepository {
  ContentRepositoryImpl(this._api);
  final ApiClient _api;

  @override
  Future<Result<List<AyahHit>>> searchQuran(String q, {int limit = 30}) async =>
      (await _api.getList(
        '/quran/search',
        query: {'q': q, 'limit': limit},
      )).fold(
        (f) => Err(f),
        (l) => Ok(ContentMappers.list(l, ContentMappers.ayah)),
      );

  @override
  Future<Result<List<HadithHit>>> searchHadith(
    String q, {
    int limit = 30,
  }) async =>
      (await _api.getList(
        '/hadith/search',
        query: {'q': q, 'limit': limit},
      )).fold(
        (f) => Err(f),
        (l) => Ok(ContentMappers.list(l, ContentMappers.hadith)),
      );

  @override
  Future<Result<List<HadithChapter>>> chapters(String book) async =>
      (await _api.getList('/chapters', query: {'book': book})).fold(
        (f) => Err(f),
        (l) => Ok(ContentMappers.list(l, ContentMappers.chapter)),
      );

  @override
  Future<Result<List<HadithHit>>> chapterHadiths(
    String book,
    int chapter,
  ) async =>
      (await _api.getList(
        '/chapter/hadiths',
        query: {'book': book, 'chapter': chapter},
      )).fold(
        (f) => Err(f),
        // عناصرُ هذا المسار تحمل `no` و`grade` و`matn` بلا اسم الكتاب،
        // فيُحقن من الطلب — الخادمُ لا يكرّره في كلِّ صفّ بلا داعٍ.
        (l) => Ok(
          ContentMappers.list(l, (m) => ContentMappers.chapterHadith(m, book)),
        ),
      );

  @override
  Future<Result<List<ContentSource>>> sources() async =>
      (await _api.getList('/sources')).fold(
        (f) => Err(f),
        (l) => Ok(ContentMappers.list(l, ContentMappers.source)),
      );
}

class AgentRepositoryImpl implements AgentRepository {
  AgentRepositoryImpl(this._api);
  final ApiClient _api;

  @override
  Future<Result<AgentStep>> ask(Map<String, dynamic> answers) async =>
      (await _api.post(
        '/app/agent',
        body: {'answers': answers},
      )).fold((f) => Err(f), (j) => Ok(ContentMappers.agentStep(j)));

  @override
  Future<Result<AgentBuilt>> build(Map<String, dynamic> answers) async =>
      (await _api.post('/app/agent/build', body: {'answers': answers})).fold(
        (f) => Err(f),
        (j) => Ok(
          AgentBuilt(
            projectId: ContentMappers.intOf(j['project']),
            added: ContentMappers.intOf(j['added']),
          ),
        ),
      );
}

class ScheduleRepositoryImpl implements ScheduleRepository {
  ScheduleRepositoryImpl(this._api);
  final ApiClient _api;

  @override
  Future<Result<List<Schedule>>> list() async =>
      (await _api.get('/app/schedules')).fold((f) => Err(f), (j) {
        final raw = j['schedules'];
        if (raw is! List) return const Ok(<Schedule>[]);
        return Ok(ContentMappers.list(raw, ContentMappers.schedule));
      });

  @override
  Future<Result<Schedule>> create({
    required int projectId,
    required String kind,
    required String title,
    required Recurrence recurrence,
    required String tz,
    required int atMinute,
    int? dayOf,
  }) async =>
      (await _api.post(
        '/app/schedules/create',
        body: {
          'project': projectId,
          'kind': kind,
          'title': title,
          'recurrence': recurrence.wire,
          'tz': tz,
          'at_minute': atMinute,
          // `day_of` يُرسَل حين يكون له معنًى (أسبوعيّ/شهريّ) ولا يُرسَل صفرًا:
          // صفرٌ في مكانِ «غيرِ محدَّد» يعني الأحدَ أو أوّلَ الشهر بلا قصد.
          'day_of': ?dayOf,
        },
      )).fold(
        (f) => Err(f),
        (j) => Ok(
          ContentMappers.schedule(
            j['schedule'] is Map
                ? Map<String, dynamic>.from(j['schedule'] as Map)
                : j,
          ),
        ),
      );

  @override
  Future<Result<void>> setStatus(int id, ScheduleStatus status) async =>
      (await _api.post(
        '/app/schedules/status',
        body: {'id': id, 'status': status.wire},
      )).fold((f) => Err(f), (_) => const Ok(null));

  @override
  Future<Result<void>> delete(int id) async => (await _api.post(
    '/app/schedules/delete',
    body: {'id': id},
  )).fold((f) => Err(f), (_) => const Ok(null));
}

class PublishRepositoryImpl implements PublishRepository {
  PublishRepositoryImpl(this._api);
  final ApiClient _api;

  @override
  Future<Result<List<PublishProvider>>> providers() async =>
      (await _api.get('/app/publish/providers')).fold((f) => Err(f), (j) {
        final raw = j['providers'];
        if (raw is! List) return const Ok(<PublishProvider>[]);
        return Ok(ContentMappers.list(raw, ContentMappers.provider));
      });

  @override
  Future<Result<List<PublishAccount>>> accounts() async =>
      (await _api.get('/app/publish/accounts')).fold((f) => Err(f), (j) {
        final raw = j['accounts'];
        if (raw is! List) return const Ok(<PublishAccount>[]);
        return Ok(ContentMappers.list(raw, ContentMappers.account));
      });

  @override
  Future<Result<PublishAccount>> connect({
    required String provider,
    required String secret,
    required String label,
  }) async =>
      (await _api.post(
        '/app/publish/connect',
        // السرُّ يمرّ مرّةً واحدةً في هذا الطلب. ولا يُحفظ في العميل، ولا
        // يُسجَّل، ولا يعود من الخادم بعدها.
        body: {'provider': provider, 'secret': secret, 'label': label},
      )).fold(
        (f) => Err(f),
        (j) => Ok(
          ContentMappers.account(
            j['account'] is Map
                ? Map<String, dynamic>.from(j['account'] as Map)
                : j,
          ),
        ),
      );

  @override
  Future<Result<void>> disconnect(int id) async => (await _api.post(
    '/app/publish/disconnect',
    body: {'id': id},
  )).fold((f) => Err(f), (_) => const Ok(null));
}
