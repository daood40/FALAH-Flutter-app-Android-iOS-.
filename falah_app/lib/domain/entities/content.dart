/// كياناتُ المحتوى الشرعيّ — **مراجعُ لا متون.**
///
/// القاعدةُ الحاكمة (`SOURCE_LOCK`): العميلُ يعرض ما يرسله الخادمُ ويحمل
/// **مرجعَه** حين يضيفه إلى مشروع — سورةً وآيةً، أو كتابًا ورقمًا. ولا يرسل
/// متنًا قطّ. فلو أرسل لأمكن أن يصل إلى بطاقةٍ نصٌّ لم يمرّ بفحوص الخادم،
/// وهو بعينه ما يمنعه المشروعُ من أوّل سطر.
///
/// ولهذا `text` هنا **للعرض وحدَه**، ولا يُعاد إلى الخادم في أيِّ طلب.
library;

/// نتيجةُ بحثٍ في القرآن — `/quran/search`
class AyahHit {
  const AyahHit({
    required this.surah,
    required this.ayah,
    required this.text,
    required this.surahName,
    required this.page,
    required this.cardOk,
  });

  final int surah;
  final int ayah;
  final String text;
  final String surahName;
  final int page;

  /// هل يجتاز فحوصَ البطاقة؟ يرسلها الخادمُ `card_ok`، فيُعرض غيرُ المجتاز
  /// **معطَّلًا مع سببه** بدل أن يُخفى — الإخفاءُ يجعل المستخدمَ يظنّ النصَّ
  /// مفقودًا، والتعطيلُ يقول له إنه موجودٌ ولم يجتز.
  final bool cardOk;

  /// المرجعُ الذي يُرسَل إلى `/app/items/add` — لا المتن.
  Map<String, dynamic> get ref => {'surah': surah, 'ayah': ayah};

  String get label => '$surahName · الآية $ayah';
}

/// نتيجةُ بحثٍ في الحديث — `/hadith/search`
class HadithHit {
  const HadithHit({
    required this.book,
    required this.bookName,
    required this.number,
    required this.matn,
    required this.grade,
    required this.cardOk,
    this.narrator,
  });

  final String book;
  final String bookName;
  final int number;
  final String matn;

  /// **الحكمُ يُعرض كما ورد من المصدر ولا يُشتقّ في العميل.** حديثٌ بلا حكمٍ
  /// يبقى بلا حكم — ولا يُملأ الفراغُ بتخمين.
  final String grade;
  final String? narrator;
  final bool cardOk;

  Map<String, dynamic> get ref => {'book': book, 'no': number};

  String get label => '$bookName · $number';
}

/// كتابٌ من كتب الحديث ضمن التصفّح
class HadithChapter {
  const HadithChapter({
    required this.id,
    required this.nameAr,
    required this.count,
  });

  final int id;
  final String nameAr;
  final int count;
}

/// مصدرٌ في قاعدة المحتوى — `/sources`
///
/// وهذه الشاشةُ ليست زينة: **الإسنادُ وعدُ المنتَج**، فمن حقِّ المستخدم أن
/// يرى من أين جاء النصُّ وما حالُ ترخيصه قبل أن ينشره باسمه.
class ContentSource {
  const ContentSource({
    required this.code,
    required this.name,
    required this.kind,
    required this.origin,
    required this.licenseStatus,
    required this.enabled,
  });

  final String code;
  final String name;
  final String kind;
  final String origin;
  final String licenseStatus;
  final bool enabled;

  /// ترخيصٌ لم يُحسم يُعرض بعلامةٍ ظاهرة — لا يُطوى في سطرٍ رماديّ.
  bool get licenseUnsettled =>
      licenseStatus.contains('يحتاج') || licenseStatus.contains('مراجعة');
}
