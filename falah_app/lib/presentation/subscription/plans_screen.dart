/// الخطط — عرضٌ لما تتيحه كلُّ خطّة. **الشراءُ يُتحقَّق في الخادم.**
///
/// لا يُبنى في العميل قرارُ استحقاق: الخادمُ يتحقّق من إيصال المتجر
/// بتوقيعه (ES256 لآبل، RS256 لجوجل) قبل أن يُمنح حقّ.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/failure.dart';
import '../../core/theme/tokens.dart';
import '../../core/utils/arabic.dart';
import '../../shared/widgets/states.dart';
import '../home/home_controller.dart';

class PlansScreen extends ConsumerWidget {
  const PlansScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ent = ref.watch(entitlementsProvider);
    final t = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('الخطط')),
      body: ent.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
          failure: e is Failure ? e : const UnknownFailure(),
          onRetry: () => ref.invalidate(entitlementsProvider),
        ),
        data: (e) => ListView(
          padding: const EdgeInsets.all(Space.lg),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(Space.md),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('خطّتك الحالية', style: t.textTheme.bodySmall),
                    const SizedBox(height: Space.xs),
                    Text(e.planName, style: t.textTheme.headlineSmall),
                    const SizedBox(height: Space.md),
                    for (final entry in e.limits.entries)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Text(
                          '${_metric(entry.key)}: '
                          '${arabicNum(e.used[entry.key] ?? 0)} '
                          'من ${arabicNum(entry.value)}',
                          style: t.textTheme.bodyMedium,
                        ),
                      ),
                    if (e.expiresAt != null) ...[
                      const SizedBox(height: Space.sm),
                      Text(
                        'تنتهي في ${shortDate(e.expiresAt!)}',
                        style: t.textTheme.bodySmall,
                      ),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: Space.lg),
            Text('ما تتيحه خطّتك', style: t.textTheme.titleMedium),
            const SizedBox(height: Space.sm),
            Wrap(
              spacing: Space.sm,
              runSpacing: Space.sm,
              children: [
                for (final r in e.ratios) _Chip(ratioLabel(r)),
                for (final d in e.designs) _Chip(skinLabel(d)),
                _Chip('سلسلة حتى ${arabicNum(e.seriesMax)}'),
              ],
            ),
            const SizedBox(height: Space.xl),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(Space.md),
                child: Text(
                  'الشراء داخل التطبيق يُفعَّل عند نشر التطبيق في المتجر. '
                  'ويُتحقَّق من كلّ إيصالٍ في الخادم بتوقيعه قبل منح أيّ حقّ.',
                  style: t.textTheme.bodySmall,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static String _metric(String m) => switch (m) {
    'cards' => 'البطاقات',
    'videos' => 'المقاطع',
    'projects' => 'المشاريع',
    _ => m,
  };
}

class _Chip extends StatelessWidget {
  const _Chip(this.label);
  final String label;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(
      horizontal: Space.md,
      vertical: Space.sm,
    ),
    decoration: BoxDecoration(
      borderRadius: Radii.pill,
      border: Border.all(color: Theme.of(context).colorScheme.outline),
    ),
    child: Text(label, style: Theme.of(context).textTheme.bodySmall),
  );
}
