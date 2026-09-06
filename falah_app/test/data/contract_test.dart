/// عقدُ العميل ↔ الخادم — بأشكالِ الردود **الحقيقيّة** لا بما نتوقّعه.
///
/// سببُ وجود هذا الملفّ عيبٌ وقع فعلًا: كان المحوّلُ يقرأ `checks` و`title`
/// و`drifted`، والخادمُ يرسل `checks_now` («٢٥/٢٥» نصًّا) و`card.title`
/// و`state`. فكان كلُّ عنصرٍ يظهر بصفر فحصٍ وبلا عنوان — ولم يظهر ذلك في
/// اختبارٍ بمضاعفاتٍ **نكتب نحن شكلَها**، إنما أمسكته رحلةُ مستخدمٍ على
/// خادمٍ حيّ.
///
/// فالقاعدة: **الأشكالُ هنا منسوخةٌ من ردٍّ حقيقيّ** لا مؤلَّفة. ومن غيّر
/// شكلَ ردٍّ في الخادم أسقط هذا الملفَّ، فيُحدَّث معًا.
library;

import 'package:falah_app/data/dto/mappers.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('عنصرُ المشروع — الشكلُ الحقيقيّ من /app/projects/:id', () {
    // منسوخٌ من ردٍّ فعليّ: المفاتيحُ هي
    // added_at · card · checks_now · checks_then · id · kind · pos · ref · state
    final okItem = <String, dynamic>{
      'id': 12,
      'pos': 0,
      'kind': 'quran',
      'ref': {'surah': 108, 'ayah': 1},
      'checks_then': 25,
      'checks_now': '25/25',
      'added_at': 1788600000,
      'state': 'ok',
      'card': {
        'title': 'سُورَةُ ٱلْكَوْثَرِ ١',
        'text': 'إِنَّآ أَعْطَيْنَٰكَ ٱلْكَوْثَرَ',
      },
    };

    test('«٢٥/٢٥» نصًّا تُقرأ عددًا لا صفرًا', () {
      final it = Mappers.item(okItem);
      expect(it.checks, 25, reason: 'العيبُ القديم: كانت تُقرأ صفرًا');
      expect(it.total, 25);
      expect(it.verified, isTrue);
    });

    test('والمجموعُ يُقرأ من الخادم لا يُثبَّت في العميل', () {
      final it = Mappers.item({...okItem, 'checks_now': '30/32'});
      expect(it.checks, 30);
      expect(it.total, 32, reason: 'لو زاد الخادمُ فحصًا بقي العميلُ صادقًا');
      expect(it.verified, isFalse);
    });

    test('والعنوانُ من البطاقة — لا حقلَ `title` في الردّ', () {
      expect(Mappers.item(okItem).title, 'سُورَةُ ٱلْكَوْثَرِ ١');
    });

    test('وبلا عنوانٍ في البطاقة يُؤخذ نصُّها', () {
      final it = Mappers.item({
        ...okItem,
        'card': {'text': 'نصٌّ بلا عنوان'},
      });
      expect(it.title, 'نصٌّ بلا عنوان');
    });
  });

  group('حالاتُ العنصر الأربع كما يعلنها الخادم', () {
    Map<String, dynamic> withState(String s, {String? why}) {
      final m = <String, dynamic>{
        'id': 1,
        'kind': 'quran',
        'checks_now': '25/25',
        'state': s,
        'card': {'title': 'ت'},
      };
      // `why` يغيب حين لا سببَ — كما يفعل الخادمُ تمامًا
      if (why != null) m['why'] = why;
      return m;
    }

    test('ok ⇒ سليمٌ غيرُ محجوب', () {
      final it = Mappers.item(withState('ok'));
      expect(it.verified, isTrue);
      expect(it.blocked, isFalse);
      expect(it.drifted, isFalse);
    });

    test('drift ⇒ منجرفٌ ومحجوب', () {
      final it = Mappers.item(withState('drift', why: 'تغيّر نصّ المصدر'));
      expect(it.drifted, isTrue);
      expect(it.blocked, isTrue);
      expect(
        it.verified,
        isFalse,
        reason: 'المنجرفُ لا يُنشر ولو اجتاز الفحوص',
      );
      expect(it.why, 'تغيّر نصّ المصدر');
    });

    test('blocked ⇒ محجوبٌ غيرُ منجرف', () {
      final it = Mappers.item(withState('blocked', why: 'حكمٌ ضعيف'));
      expect(it.blocked, isTrue);
      expect(it.drifted, isFalse);
      expect(it.why, 'حكمٌ ضعيف');
    });

    test('missing ⇒ محجوب', () {
      expect(Mappers.item(withState('missing')).blocked, isTrue);
    });
  });

  group('المشروعُ المفتوح', () {
    // الردُّ الحقيقيّ: {project: {...}, items: [...], drift: [], blocked: [], exportable: bool}
    final detail = <String, dynamic>{
      'project': {
        'id': 7,
        'user_id': 3,
        'title': 'سلسلةُ الفجر',
        'skin': 'parch',
        'ratio': 'square',
        'archived': 0,
        'created_at': 1788600000,
        'updated_at': 1788600100,
      },
      'items': [
        {
          'id': 1,
          'kind': 'quran',
          'checks_now': '25/25',
          'state': 'ok',
          'card': {'title': 'أ'},
        },
        {
          'id': 2,
          'kind': 'hadith',
          'checks_now': '24/25',
          'state': 'blocked',
          'why': 'س',
          'card': {'title': 'ب'},
        },
      ],
      'drift': <int>[],
      'blocked': [2],
      'exportable': false,
    };

    test('المشروعُ يُقرأ من المفتاح المتداخل', () {
      final p = Mappers.projectDetail(detail);
      expect(p.id, 7);
      expect(p.title, 'سلسلةُ الفجر');
      expect(p.skin, 'parch');
      expect(p.ratio, 'square');
    });

    test('والعناصرُ تُقرأ من الجذر لا من داخل المشروع', () {
      final p = Mappers.projectDetail(detail);
      expect(p.items.length, 2);
      expect(p.itemCount, 2);
      expect(p.items.first.verified, isTrue);
      expect(p.items.last.blocked, isTrue);
    });
  });

  group('سردُ المشاريع — /app/projects', () {
    test('`items` عددٌ في السرد لا قائمة', () {
      // الخادمُ يعيد تسميةَ العدّ: `d["items"] = d.pop("n")`
      final p = Mappers.project({
        'id': 3,
        'title': 'م',
        'skin': 'night',
        'ratio': 'story',
        'items': 4,
        'updated_at': 1788600000,
      });
      expect(p.itemCount, 4);
      expect(p.items, isEmpty, reason: 'السردُ لا يحمل العناصرَ نفسَها');
    });
  });

  group('الحقوق — /app/entitlements', () {
    final ent = <String, dynamic>{
      'plan': 'free',
      'plan_name': 'مجّاني',
      'status': 'active',
      'provider': null,
      'expires_at': null,
      'renews': false,
      'limits': {'cards': 15, 'videos': 0, 'projects': 2},
      'used': {'cards': 3, 'videos': 0, 'projects': 1},
      'left': {'cards': 12, 'videos': 0, 'projects': 1},
      'features': {
        'ratios': ['square'],
        'designs': ['parch'],
        'series_max': 3,
      },
      'period': '2026-09',
    };

    test('الحدودُ والمستهلَكُ والباقي تُقرأ', () {
      final e = Mappers.entitlements(ent);
      expect(e.limitOf('cards'), 15);
      expect(e.leftOf('cards'), 12);
      expect(e.isFree, isTrue);
      expect(e.isActive, isTrue);
    });

    test('و`expires_at: null` تعني بلا انتهاء لا صفرًا', () {
      expect(Mappers.entitlements(ent).expiresAt, isNull);
    });

    test('والميزاتُ تُقرأ من الخادم لا تُخمَّن', () {
      final e = Mappers.entitlements(ent);
      expect(e.ratios, ['square']);
      expect(e.designs, ['parch']);
      expect(e.seriesMax, 3);
    });
  });

  group('المهمّة — /app/jobs/:id', () {
    test('الحالاتُ الخمسُ تُقرأ', () {
      for (final s in ['queued', 'running', 'done', 'failed', 'canceled']) {
        final j = Mappers.job({
          'job': {'id': 1, 'state': s, 'progress': 50},
        });
        expect(j.state.name, s);
      }
    });

    test('وحالةٌ مجهولةٌ تُقرأ «في الطابور» لا تُسقط', () {
      final j = Mappers.job({
        'job': {'id': 1, 'state': 'teleporting', 'progress': 0},
      });
      expect(j.state.name, 'queued');
    });

    test('والتقدّمُ يُحصر ٠–١٠٠ ولو أرسل الخادمُ غيرَه', () {
      expect(
        Mappers.job({
          'job': {'id': 1, 'state': 'running', 'progress': 250},
        }).progress,
        100,
      );
      expect(
        Mappers.job({
          'job': {'id': 1, 'state': 'running', 'progress': -5},
        }).progress,
        0,
      );
    });
  });

  group('المستخدم — /app/me', () {
    test('الدورُ يُقرأ ولا يُبنى عليه منع', () {
      final u = Mappers.user({
        'id': 5,
        'email': 'a@b.c',
        'name': 'د',
        'watermark': 'ق',
        'created_at': 1788600000,
        'role': 'admin',
      });
      expect(u.role, 'admin');
    });

    test('ودورٌ غائبٌ يُقرأ `user` — أضعفُ الأدوار لا أقواها', () {
      final u = Mappers.user({
        'id': 5,
        'email': 'a@b.c',
        'name': 'د',
        'watermark': '',
        'created_at': 1788600000,
      });
      expect(u.role, 'user');
    });

    test('ومستخدمٌ بلا معرّفٍ يُرمى لا يُقبل صامتًا', () {
      expect(() => Mappers.user({'email': 'a@b.c'}), throwsFormatException);
    });
  });
}
