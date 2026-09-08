/// متابعةُ مهمّة التصدير — استطلاعٌ متمهّلٌ **بحدٍّ أعلى** وإلغاءٌ حقيقيّ.
///
/// العميلُ القديم كان يستطلع في `for(;;)` بلا نهاية: مهمّةٌ تعلق في
/// `running` تُستطلَع أبدًا، ولا زرَّ إلغاءٍ في الواجهة رغم وجود المسار.
/// هنا ثلاثةُ حدود:
///
///   ١ · تمهّلٌ تصاعديّ ٤٠٠مل.ث → ٣ث — لا يُثقل الخادم
///   ٢ · **سقفٌ زمنيٌّ كلّيّ** — بعده يُقال «تأخّرت» ولا يُترك المستخدمُ معلّقًا
///   ٣ · إلغاءٌ يُنهي المهمّةَ في الخادم ويردّ الحصّة
library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/failure.dart';
import '../../core/logging/logger.dart';
import '../../domain/entities/project.dart';
import '../auth/auth_controller.dart';
import '../home/home_controller.dart';
import '../providers.dart';

sealed class ExportState {
  const ExportState();
}

final class ExportIdle extends ExportState {
  const ExportIdle();
}

final class ExportRunning extends ExportState {
  const ExportRunning(this.jobId, this.job);
  final int jobId;
  final Job job;
}

final class ExportDone extends ExportState {
  const ExportDone(this.files);
  final int files;
}

final class ExportFailed extends ExportState {
  const ExportFailed(this.failure);
  final Failure failure;
}

/// سقفُ الانتظار الكلّيّ. مقيسٌ من الخط الأساس: ٤ بطاقات = ١٢ث، وسلسلةٌ
/// طويلةٌ قد تبلغ دقيقتين — فخمسُ دقائقَ هامشٌ واسعٌ لا انتظارٌ أبديّ.
const Duration _maxWait = Duration(minutes: 5);

class ExportController extends Notifier<ExportState> {
  Timer? _timer;
  DateTime? _startedAt;
  int? _jobId;

  @override
  ExportState build() {
    ref.onDispose(_stopTimer);
    return const ExportIdle();
  }

  void _stopTimer() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> start(int projectId) async {
    _stopTimer();
    state = const ExportRunning(
      0,
      Job(id: 0, state: JobState.queued, progress: 0),
    );
    final r = await ref.read(projectRepositoryProvider).startExport(projectId);
    r.fold(
      (f) {
        _fail(f);
      },
      (id) {
        _jobId = id;
        _startedAt = DateTime.now();
        Log.info('export.start', {'job_id': id});
        _poll(400);
      },
    );
  }

  void _poll(int delayMs) {
    _timer = Timer(Duration(milliseconds: delayMs), () async {
      final id = _jobId;
      if (id == null) return;

      if (DateTime.now().difference(_startedAt!) > _maxWait) {
        Log.warn('export.timeout', {'job_id': id});
        _fail(
          const TimeoutFailure(
            'تأخّرت المهمّة أكثر من المتوقّع — يمكنك إلغاؤها والمحاولة ثانيةً',
          ),
        );
        return;
      }

      final r = await ref.read(projectRepositoryProvider).job(id);
      r.fold(_fail, (j) {
        switch (j.state) {
          case JobState.done:
            _stopTimer();
            final n =
                (j.result?['files'] as List?)?.length ??
                (j.result?['count'] as int?) ??
                0;
            Log.info('export.done', {'job_id': id, 'files': n});
            // الحصّةُ نقصت: تُعاد قراءتُها فيرى المستخدمُ الرقمَ الصحيح
            ref.invalidate(entitlementsProvider);
            state = ExportDone(n);
          case JobState.failed:
            _stopTimer();
            _fail(ServerFailure(j.error ?? 'فشل التصدير'));
          case JobState.canceled:
            _stopTimer();
            state = const ExportIdle();
          case JobState.queued:
          case JobState.running:
            state = ExportRunning(id, j);
            // تمهّلٌ تصاعديٌّ بسقف ٣ث — كما كان في العميل القديم، وهو صحيح
            _poll((delayMs * 1.3).round().clamp(400, 3000));
        }
      });
    });
  }

  Future<void> cancel() async {
    final id = _jobId;
    _stopTimer();
    if (id == null || id == 0) {
      state = const ExportIdle();
      return;
    }
    final r = await ref.read(projectRepositoryProvider).cancelJob(id);
    r.fold(_fail, (_) {
      Log.info('export.cancel', {'job_id': id});
      ref.invalidate(entitlementsProvider);
      state = const ExportIdle();
    });
  }

  void reset() {
    _stopTimer();
    _jobId = null;
    state = const ExportIdle();
  }

  void _fail(Failure f) {
    _stopTimer();
    if (f is UnauthorizedFailure) {
      ref.read(authControllerProvider.notifier).expire(f.message);
    }
    state = ExportFailed(f);
  }
}

final exportControllerProvider =
    NotifierProvider<ExportController, ExportState>(ExportController.new);
