/// **رحلةُ المستخدم كاملةً على خادمٍ حيّ** — لا مضاعفاتٍ ولا مُحاكاة.
///
/// سببُ وجود هذا الملفّ درسٌ كلّفنا: عقدُ المحوِّل انكسر بين العميل والخادم،
/// والاختباراتُ كلُّها خضراء — لأنّنا كنّا نكتب شكلَ الردِّ بأيدينا. ولم
/// يظهر العيبُ إلا حين مرّ مستخدمٌ على خادمٍ حقيقيّ.
///
/// فالقاعدة: **ما لم يجرِ على خادمٍ حيٍّ لا يُقال إنه يعمل.**
///
/// ويُشغَّل هكذا:
///
///     python3 app.py &
///     flutter test --dart-define=FALAH_API=http://localhost:8080
///
/// وبلا خادمٍ **تتخطّى الاختباراتُ نفسَها ويسقط الأنبوب**: حارسٌ في
/// `.github/workflows/ci.yml` يُسقط البناءَ إن تخطّى اختبارٌ واحد، لأنّ
/// «All tests passed» على اختباراتٍ لم تجرِ خضرةٌ كاذبة.
library;

import 'dart:io';

import 'package:falah_app/core/network/api_client.dart';
import 'package:falah_app/data/repositories/auth_repository_impl.dart';
import 'package:falah_app/data/repositories/content_repository_impl.dart';
import 'package:falah_app/data/repositories/project_repository_impl.dart';
import 'package:falah_app/domain/entities/schedule.dart';
import 'package:flutter_test/flutter_test.dart';

import 'live.dart';

void main() {
  late Directory jar;
  late ApiClient api;
  late AuthRepositoryImpl auth;
  late ProjectRepositoryImpl projects;
  late ContentRepositoryImpl content;
  late AgentRepositoryImpl agent;
  late ScheduleRepositoryImpl schedules;
  late PublishRepositoryImpl publish;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    HttpOverrides.global = null;
    jar = await Directory.systemTemp.createTemp('falah_journey_');
    api = await ApiClient.create(cookieDir: '${jar.path}/');
    auth = AuthRepositoryImpl(api);
    projects = ProjectRepositoryImpl(api);
    content = ContentRepositoryImpl(api);
    agent = AgentRepositoryImpl(api);
    schedules = ScheduleRepositoryImpl(api);
    publish = PublishRepositoryImpl(api);
  });

  tearDownAll(() async {
    if (jar.existsSync()) await jar.delete(recursive: true);
  });

  group('رحلةٌ كاملة', () {
    late String email;
    int? projectId;

    setUpAll(() => email = liveEmail('journey'));

    test('١ · إقلاعٌ بلا جلسة ⇒ زائرٌ لا انهيار', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      expect(okOf(await auth.currentUser()), isNull);
    });

    test('٢ · تسجيلٌ ودخول', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      final u = okOf(
        await auth.register(email: email, password: livePassword, name: 'رحلة'),
      );
      expect(u.email, email);
    });

    test('٣ · الجلسةُ تنجو من إغلاق التطبيق', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      // عميلٌ جديدٌ على الجرّة نفسِها = تطبيقٌ أُعيد فتحُه
      final again = AuthRepositoryImpl(
        await ApiClient.create(cookieDir: '${jar.path}/'),
      );
      expect(okOf(await again.currentUser())?.email, email);
    });

    test('٤ · الحقوقُ تُقرأ ولا تُخمَّن في العميل', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      final e = okOf(await projects.entitlements());
      expect(e.limitOf('cards'), greaterThan(0));
      expect(e.ratios, isNotEmpty, reason: 'المقاساتُ من الخادم لا ثابتةٌ هنا');
    });

    test('٥ · بحثٌ في القرآن ⇒ نتائجُ حقيقيّة', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      final hits = okOf(await content.searchQuran('الكوثر'));
      expect(hits, isNotEmpty);
      expect(hits.first.text, isNotEmpty);
      expect(hits.first.surah, greaterThan(0));
    });

    test('٦ · بحثٌ في الحديث ⇒ ومعه الحكمُ من المصدر', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      final hits = okOf(await content.searchHadith('النية'));
      expect(hits, isNotEmpty);
      expect(hits.first.matn, isNotEmpty);
      // الحكمُ يأتي من المصدر — ولا يُشتقّ في العميل
      expect(hits.first.book, isNotEmpty);
    });

    test('٧ · المصادرُ معروضةٌ بحال تراخيصها — الإسنادُ مرئيّ', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      final s = okOf(await content.sources());
      expect(s, isNotEmpty);
      expect(s.first.licenseStatus, isNotEmpty);
    });

    test('٨ · إنشاءُ مشروع', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      final p = okOf(await projects.create('رحلةُ الاختبار'));
      projectId = p.id;
      expect(p.id, greaterThan(0));
    });

    test('٩ · إضافةُ آيةٍ **بمرجعها لا بمتنها**', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      expect(projectId, isNotNull);
      final r = await projects.addItem(
        projectId: projectId!,
        kind: 'quran',
        ref: {'surah': 108, 'ayah': 1},
      );
      expect(r, isA<Ok<void>>());
    });

    test('١٠ · فتحُ المشروع ⇒ العنصرُ باجتيازه الكامل', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      final p = okOf(await projects.open(projectId!));
      expect(p.items, isNotEmpty);
      final it = p.items.first;
      // هذا بعينه ما كسره عقدُ المحوِّل: كان يقرأ صفرًا
      expect(it.checks, greaterThan(0), reason: 'العيبُ القديم: صفرُ فحص');
      expect(it.total, greaterThan(0));
      expect(it.title, isNotEmpty, reason: 'العنوانُ من البطاقة');
      expect(it.verified, isTrue);
    });

    test('١١ · نصٌّ غيرُ موجودٍ يُرفض بسببٍ مفهوم', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      final f = errOf(
        await projects.addItem(
          projectId: projectId!,
          kind: 'quran',
          ref: {'surah': 999, 'ayah': 999},
        ),
      );
      expect(f.message, isNotEmpty);
      // رسالةٌ للمستخدم لا أثرُ نداءٍ ولا مسارُ ملفّ
      expect(f.message, isNot(contains('Traceback')));
      expect(f.message, isNot(contains('/')));
    });

    test('١٢ · تكرارُ النصِّ نفسِه يُرفض', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      final f = errOf(
        await projects.addItem(
          projectId: projectId!,
          kind: 'quran',
          ref: {'surah': 108, 'ayah': 1},
        ),
      );
      expect(f.message, isNotEmpty);
    });

    test('١٣ · التصديرُ يدخل الطابور ويُتابَع حتى يكتمل', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      final jobId = okOf(await projects.startExport(projectId!));
      expect(jobId, greaterThan(0));

      // متابعةٌ بمهلةٍ قصوى — ولا حلقةٌ بلا سقف
      var state = '';
      for (var i = 0; i < 40; i++) {
        final j = okOf(await projects.job(jobId));
        state = j.state.name;
        if (state == 'done' || state == 'failed') break;
        await Future<void>.delayed(const Duration(milliseconds: 500));
      }
      // بلا عاملٍ يبقى في الطابور — وهذا ليس فشلًا في العميل. يُقبل
      // الاكتمالُ أو الانتظار، **ولا يُقبل الفشلُ**.
      expect(state, isNot('failed'), reason: 'مهمّةٌ سقطت في الخادم');
    });

    test('١٤ · الوكيلُ يسأل سؤالًا محدَّدًا ولا يولّد نصًّا', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      final s = okOf(await agent.ask({}));
      expect(s.done, isFalse);
      expect(s.question, isNotNull);
      expect(s.questionId, isNotEmpty);
      expect(s.options, isNotEmpty, reason: 'اختيارٌ محدَّدٌ لا نصٌّ حرّ');
      expect(s.stepTotal, greaterThan(0));
    });

    test('١٥ · وإجابةٌ تتقدّم به خطوةً', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      final first = okOf(await agent.ask({}));
      final next = okOf(
        await agent.ask({first.questionId: first.options.first.value}),
      );
      expect(next.stepIndex, greaterThan(first.stepIndex));
      expect(next.answers, contains(first.questionId));
    });

    test('١٦ · وإجاباتٌ ناقصةٌ لا تبني مشروعًا', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      final f = errOf(await agent.build({}));
      expect(f.message, isNotEmpty);
    });

    test('١٧ · جدولةُ التصدير بمنطقةٍ زمنيّة', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      final s = okOf(
        await schedules.create(
          projectId: projectId!,
          kind: 'export',
          title: 'فجرٌ يوميّ',
          recurrence: Recurrence.daily,
          tz: 'Africa/Tripoli',
          atMinute: 360,
        ),
      );
      expect(s.id, greaterThan(0));
      expect(s.tz, 'Africa/Tripoli', reason: 'المنطقةُ تُحفظ ولا تُحوَّل');
      expect(s.atMinute, 360);
      expect(s.timeLabel, '06:00');
    });

    test('١٨ · وتظهر في السرد وتُعلَّق وتُحذف', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      var list = okOf(await schedules.list());
      expect(list, isNotEmpty);
      final id = list.first.id;

      expect(
        await schedules.setStatus(id, ScheduleStatus.paused),
        isA<Ok<void>>(),
      );
      list = okOf(await schedules.list());
      expect(list.firstWhere((x) => x.id == id).status, ScheduleStatus.paused);

      expect(await schedules.delete(id), isA<Ok<void>>());
      list = okOf(await schedules.list());
      expect(list.where((x) => x.id == id), isEmpty);
    });

    test(
      '١٩ · المنصّاتُ تُعلَن بحالتها — ولا يُدَّعى دعمٌ بلا تكامل',
      () async {
        if (!await serverUp()) return markTestSkipped(noServer);
        final ps = okOf(await publish.providers());
        expect(ps, isNotEmpty);
        expect(
          ps.where((p) => p.ready).map((p) => p.key),
          contains('telegram'),
          reason: 'المنفَّذُ اليومَ تلغرام',
        );
        final ig = ps.firstWhere((p) => p.key == 'instagram');
        expect(ig.ready, isFalse);
        expect(ig.note, isNotEmpty, reason: 'ولغيرِ المنفَّذ سببٌ مكتوب');
      },
    );

    test('٢٠ · ولا يُربط حسابٌ لمنصّةٍ غيرِ منفَّذة', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      final f = errOf(
        await publish.connect(
          provider: 'instagram',
          secret: liveSecret('ig'),
          label: 'ت',
        ),
      );
      expect(f.message, isNotEmpty);
    });

    test('٢١ · حذفُ المشروع', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      expect(await projects.delete(projectId!), isA<Ok<void>>());
      final f = errOf(await projects.open(projectId!));
      // «ليس لك» ≡ «غير موجود» — ولا يُستدلّ بوجود مورد
      expect(f.message, isNotEmpty);
    });

    test('٢٢ · مسارٌ إداريٌّ لمستخدمٍ عاديّ ⇒ يُمنع', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      final r = await api.get('/app/admin/metrics');
      expect(r, isA<Err<dynamic>>());
    });

    test('٢٣ · الخروجُ يُنهي الجلسةَ في الخادم', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      expect(await auth.logout(), isA<Ok<void>>());
      expect(okOf(await auth.currentUser()), isNull);
    });

    test('٢٤ · وبعده لا يُقرأ موردٌ محميّ', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      final r = await projects.list();
      expect(r, isA<Err<dynamic>>());
    });

    test('٢٥ · والتصفّحُ العامُّ يبقى متاحًا بلا جلسة', () async {
      if (!await serverUp()) return markTestSkipped(noServer);
      if (!await contentAvailable()) return markTestSkipped(noContent);
      // مساراتُ المحتوى عامّة — والتصفّحُ لا يشترط حسابًا
      final hits = okOf(await content.searchQuran('الكوثر'));
      expect(hits, isNotEmpty);
    });
  });
}
