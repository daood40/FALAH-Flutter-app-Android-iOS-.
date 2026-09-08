/// حالةُ تصفّح المحتوى — بحثٌ في القرآن والحديث وإضافةٌ إلى مشروع.
library;

import 'dart:async';

import 'package:dio/dio.dart' show CancelToken;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/failure.dart';
import '../../core/network/api_client.dart';
import '../../domain/entities/content.dart';
import '../providers.dart';

enum BrowseKind { quran, hadith }

sealed class BrowseState {
  const BrowseState();
}

class BrowseIdle extends BrowseState {
  const BrowseIdle();
}

class BrowseSearching extends BrowseState {
  const BrowseSearching();
}

class BrowseResults extends BrowseState {
  const BrowseResults(this.ayat, this.hadiths);
  final List<AyahHit> ayat;
  final List<HadithHit> hadiths;

  bool get isEmpty => ayat.isEmpty && hadiths.isEmpty;
}

class BrowseFailed extends BrowseState {
  const BrowseFailed(this.failure);
  final Failure failure;
}

class BrowseController extends Notifier<BrowseState> {
  Timer? _debounce;

  /// يُلغى الطلبُ السابقُ عند كتابة حرفٍ جديد. وبلا هذا يصل ردُّ بحثٍ قديمٍ
  /// بعد الجديد فيحلّ محلَّه — والمستخدمُ يرى نتائجَ كلمةٍ لم يعد يكتبها.
  CancelToken? _inflight;

  @override
  BrowseState build() {
    ref.onDispose(() {
      _debounce?.cancel();
      _inflight?.cancel();
    });
    return const BrowseIdle();
  }

  /// تأخيرٌ قصيرٌ قبل الطلب: من يكتب «الكوثر» يطبع سبعةَ أحرف، وبلا تأخيرٍ
  /// تصير سبعةَ طلبات. ٣٥٠ملّي كافيةٌ لتمرّ الكلمةُ ولا تُشعر بالبطء.
  void query(String q, BrowseKind kind) {
    _debounce?.cancel();
    final term = q.trim();
    if (term.length < 2) {
      _inflight?.cancel();
      state = const BrowseIdle();
      return;
    }
    _debounce = Timer(
      const Duration(milliseconds: 350),
      () => _run(term, kind),
    );
  }

  Future<void> _run(String q, BrowseKind kind) async {
    _inflight?.cancel();
    final token = CancelToken();
    _inflight = token;
    state = const BrowseSearching();
    final repo = ref.read(contentRepositoryProvider);

    final r = kind == BrowseKind.quran
        ? await repo.searchQuran(q)
        : await repo.searchHadith(q);

    // الردُّ الذي وصل بعد إلغائه يُهمَل — ولا يكتب فوق نتيجةٍ أحدثَ منه
    if (token.isCancelled || !ref.mounted) return;
    switch (r) {
      case Ok(:final value):
        state = kind == BrowseKind.quran
            ? BrowseResults(value.cast<AyahHit>(), const [])
            : BrowseResults(const [], value.cast<HadithHit>());
      case Err(:final failure):
        state = BrowseFailed(failure);
    }
  }

  void clear() {
    _debounce?.cancel();
    _inflight?.cancel();
    state = const BrowseIdle();
  }
}

final browseControllerProvider =
    NotifierProvider<BrowseController, BrowseState>(BrowseController.new);

/// المصادرُ وحالُ تراخيصها — تُقرأ مرّةً وتُعاد عند الطلب.
final sourcesProvider = FutureProvider.autoDispose<List<ContentSource>>((
  ref,
) async {
  final r = await ref.watch(contentRepositoryProvider).sources();
  switch (r) {
    case Ok(:final value):
      return value;
    case Err(:final failure):
      // يُرمى الصنفُ نفسُه لا نصُّه: الشاشةُ تعرض `Failure` مصنَّفًا،
      // وزرُّ الإعادة يظهر حين تكون الإعادةُ مجديةً فقط
      throw failure;
  }
});
