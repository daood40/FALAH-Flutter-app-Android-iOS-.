/// حالاتُ الشاشة الأربع — تحميلٌ وفراغٌ وخطأٌ ونجاح.
///
/// وُضعت في مكانٍ واحدٍ لأن التدقيق وجد في العميل القديم **عشرَ نداءاتٍ
/// بلا معالجة خطأ**: يفشل النداءُ فلا يظهر شيء، وأسوأُها زرٌّ يُعطَّل على
/// «يُبنى…» إلى إعادة التحميل. ووجودُ ودجةٍ جاهزةٍ يجعل المعالجةَ أسهلَ
/// من إغفالها.
library;

import 'package:flutter/material.dart';

import '../../core/errors/failure.dart';
import '../../core/theme/tokens.dart';

class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.label});
  final String? label;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const CircularProgressIndicator(strokeWidth: 2.2),
        if (label != null) ...[
          const SizedBox(height: Space.md),
          Text(label!, style: Theme.of(context).textTheme.bodySmall),
        ],
      ],
    ),
  );
}

class EmptyView extends StatelessWidget {
  const EmptyView({super.key, required this.message, this.action});
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(Space.xl),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            message,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          if (action != null) ...[const SizedBox(height: Space.lg), action!],
        ],
      ),
    ),
  );
}

/// عرضُ الخطأ. **زرُّ الإعادة يظهر حين تكون الإعادةُ مجديةً فقط** —
/// فلا يُعرض للحصّة (علاجُها ترقيةٌ) ولا للتفويض (علاجُه ليس تكرارًا).
class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.failure, this.onRetry});
  final Failure failure;
  final VoidCallback? onRetry;

  static bool retryable(Failure f) => switch (f) {
    NetworkFailure() ||
    TimeoutFailure() ||
    ServerFailure() ||
    UnknownFailure() => true,
    RateLimitFailure() => true,
    _ => false,
  };

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final canRetry = onRetry != null && retryable(failure);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(Space.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(_icon, size: 40, color: Palette.dangerSoft),
            const SizedBox(height: Space.md),
            Text(
              failure.message,
              textAlign: TextAlign.center,
              style: t.textTheme.bodyMedium,
            ),
            if (failure is QuotaFailure) ...[
              const SizedBox(height: Space.sm),
              Text(
                'ترقيةُ الخطّة تفكّ هذا الحدّ.',
                style: t.textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
            ],
            if (failure.requestId != null) ...[
              const SizedBox(height: Space.sm),
              // يُعرض ليُقتبس عند الإبلاغ — ليس سرًّا ولا يخصّ المستخدم
              SelectableText(
                'معرّف الطلب: ${failure.requestId}',
                style: t.textTheme.bodySmall,
              ),
            ],
            if (canRetry) ...[
              const SizedBox(height: Space.lg),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('أعد المحاولة'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  IconData get _icon => switch (failure) {
    NetworkFailure() => Icons.wifi_off_outlined,
    TimeoutFailure() => Icons.hourglass_disabled_outlined,
    QuotaFailure() => Icons.lock_outline,
    ForbiddenFailure() => Icons.block_outlined,
    RateLimitFailure() => Icons.timer_outlined,
    _ => Icons.error_outline,
  };
}

/// شريطٌ يُظهر رسالةَ الخطأ فوق شاشةٍ فيها محتوًى — لا يُفرغها.
void showFailure(BuildContext context, Failure f) {
  ScaffoldMessenger.of(context)
    ..clearSnackBars()
    ..showSnackBar(
      SnackBar(content: Text(f.message), duration: const Duration(seconds: 4)),
    );
}

void showDone(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..clearSnackBars()
    ..showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 2)),
    );
}
