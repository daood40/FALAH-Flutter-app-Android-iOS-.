/// المشروع — عناصرُه وهيئتُه وتصديرُه، مع متابعةِ الطابور وإمكانِ الإلغاء.
///
/// وفيه تُغلق ثلاثُ فجواتٍ رصدها التدقيق في العميل القديم:
///   ١ · **زرُّ إلغاء المهمّة** — المسارُ موجودٌ ولم تكن له واجهة، فمهمّةٌ
///       عالقةٌ كانت تحبس المستخدم.
///   ٢ · **حدٌّ أعلى للاستطلاع** — كان `for(;;)` بلا نهاية.
///   ٣ · **معالجةُ فشلِ كلِّ نداء** — لا نداءَ صامتٌ هنا.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/failure.dart';
import '../../core/routing/app_router.dart';
import '../../core/theme/tokens.dart';
import '../../core/utils/arabic.dart';
import '../../domain/entities/project.dart';
import '../../shared/widgets/states.dart';
import '../home/home_controller.dart';
import '../providers.dart';
import '../schedule/schedules_screen.dart';
import 'export_controller.dart';

class ProjectScreen extends ConsumerWidget {
  const ProjectScreen({super.key, required this.projectId});
  final int projectId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(projectDetailProvider(projectId));

    return Scaffold(
      appBar: AppBar(
        title: Text(detail.value?.title ?? 'المشروع'),
        actions: [
          IconButton(
            tooltip: 'أضِف نصًّا',
            icon: const Icon(Icons.add),
            onPressed: () async {
              await context.push(Routes.browseFor(projectId));
              // العودةُ من التصفّح تعني احتمالَ إضافةٍ — يُعاد التحميل
              // بلا أن تحمل الشاشتان حالةً مشتركة
              ref.invalidate(projectDetailProvider(projectId));
            },
          ),
          IconButton(
            tooltip: 'جدولةُ التصدير',
            icon: const Icon(Icons.schedule_outlined),
            onPressed: detail.value == null
                ? null
                : () async {
                    final ok = await showModalBottomSheet<bool>(
                      context: context,
                      isScrollControlled: true,
                      builder: (_) =>
                          ScheduleCreateSheet(project: detail.value!),
                    );
                    if (ok == true && context.mounted) {
                      ScaffoldMessenger.of(context)
                        ..hideCurrentSnackBar()
                        ..showSnackBar(
                          const SnackBar(content: Text('أُنشئ الجدول')),
                        );
                    }
                  },
          ),
        ],
      ),
      body: detail.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
          failure: e is Failure ? e : const UnknownFailure(),
          onRetry: () => ref.invalidate(projectDetailProvider(projectId)),
        ),
        data: (p) => _Body(project: p),
      ),
    );
  }
}

class _Body extends ConsumerWidget {
  const _Body({required this.project});
  final Project project;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final export = ref.watch(exportControllerProvider);

    return ListView(
      padding: const EdgeInsets.all(Space.md),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(Space.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('الهيئة', style: t.textTheme.bodySmall),
                const SizedBox(height: Space.sm),
                Wrap(
                  spacing: Space.sm,
                  children: [
                    for (final s in const ['parch', 'night', 'clean'])
                      ChoiceChip(
                        label: Text(skinLabel(s)),
                        selected: project.skin == s,
                        onSelected: (_) => _update(context, ref, skin: s),
                      ),
                  ],
                ),
                const SizedBox(height: Space.md),
                Text('المقاس', style: t.textTheme.bodySmall),
                const SizedBox(height: Space.sm),
                Wrap(
                  spacing: Space.sm,
                  children: [
                    for (final r in const ['square', 'story', 'wide'])
                      ChoiceChip(
                        label: Text(ratioLabel(r)),
                        selected: project.ratio == r,
                        onSelected: (_) => _update(context, ref, ratio: r),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: Space.md),
        Text(
          'العناصر (${arabicNum(project.items.length)})',
          style: t.textTheme.titleMedium,
        ),
        const SizedBox(height: Space.sm),
        if (project.items.isEmpty)
          const EmptyView(message: 'لا عناصر بعد في هذا المشروع.')
        else
          for (final it in project.items) ...[
            _ItemTile(item: it, projectId: project.id),
            const SizedBox(height: Space.sm),
          ],
        const SizedBox(height: Space.lg),
        _ExportPanel(state: export, projectId: project.id),
      ],
    );
  }

  Future<void> _update(
    BuildContext context,
    WidgetRef ref, {
    String? skin,
    String? ratio,
  }) async {
    final r = await ref
        .read(projectRepositoryProvider)
        .update(project.id, skin: skin, ratio: ratio);
    if (!context.mounted) return;
    r.fold(
      // الفشلُ يُقال — والحصّةُ منه: مقاسٌ خارجَ الخطّة يردّه الخادم
      (f) => showFailure(context, f),
      (_) => ref.invalidate(projectDetailProvider(project.id)),
    );
  }
}

class _ItemTile extends ConsumerWidget {
  const _ItemTile({required this.item, required this.projectId});
  final ProjectItem item;
  final int projectId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(Space.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(item.title, style: t.textTheme.bodyLarge, maxLines: 3),
            const SizedBox(height: Space.sm),
            Row(
              children: [
                _Badge('${arabicNum(item.checks)}/٢٥ فحصًا', ok: item.verified),
                const SizedBox(width: Space.sm),
                _Badge(kindLabel(item.kind)),
                const Spacer(),
                IconButton(
                  tooltip: 'إزالة',
                  onPressed: () => _remove(context, ref),
                  icon: const Icon(Icons.delete_outline, size: 20),
                ),
              ],
            ),
            // سببُ الحجب يأتي من الخادم بالعربية — يُعرض كما هو ولا
            // يُعاد صوغُه في العميل، فمصدرُ الحكم واحد.
            if (item.blocked && item.why != null) ...[
              const SizedBox(height: Space.sm),
              Text(
                item.why!,
                style: t.textTheme.bodySmall?.copyWith(
                  color: item.drifted ? Palette.warn : Palette.dangerSoft,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _remove(BuildContext context, WidgetRef ref) async {
    final r = await ref
        .read(projectRepositoryProvider)
        .removeItem(projectId: projectId, itemId: item.id);
    if (!context.mounted) return;
    r.fold(
      (f) => showFailure(context, f),
      (_) => ref.invalidate(projectDetailProvider(projectId)),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge(this.label, {this.ok});
  final String label;
  final bool? ok;

  @override
  Widget build(BuildContext context) {
    final color = ok == null
        ? Theme.of(context).colorScheme.outline
        : (ok! ? Palette.success : Palette.warn);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.sm, vertical: 3),
      decoration: BoxDecoration(
        borderRadius: Radii.pill,
        border: Border.all(color: color),
      ),
      child: Text(label, style: Theme.of(context).textTheme.bodySmall),
    );
  }
}

class _ExportPanel extends ConsumerWidget {
  const _ExportPanel({required this.state, required this.projectId});
  final ExportState state;
  final int projectId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ctl = ref.read(exportControllerProvider.notifier);
    final t = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(Space.md),
        child: switch (state) {
          ExportIdle() => FilledButton.icon(
            onPressed: () => ctl.start(projectId),
            icon: const Icon(Icons.download_outlined),
            label: const Text('صدِّر السلسلة'),
          ),
          ExportRunning(:final job) => Column(
            children: [
              Row(
                children: [
                  const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  const SizedBox(width: Space.md),
                  Expanded(
                    child: Text(
                      '${job.step ?? job.state.label} '
                      '${arabicNum(job.progress)}٪',
                      style: t.textTheme.bodyMedium,
                    ),
                  ),
                  // الفجوةُ المغلقة: إلغاءٌ حقيقيٌّ لمهمّةٍ جارية
                  TextButton(onPressed: ctl.cancel, child: const Text('إلغاء')),
                ],
              ),
              const SizedBox(height: Space.sm),
              ClipRRect(
                borderRadius: Radii.pill,
                child: LinearProgressIndicator(
                  value: job.progress / 100,
                  minHeight: 6,
                ),
              ),
            ],
          ),
          ExportDone(:final files) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'اكتمل التصدير — ${arabicNum(files)} ملفًّا',
                style: t.textTheme.bodyMedium,
              ),
              const SizedBox(height: Space.sm),
              OutlinedButton(
                onPressed: ctl.reset,
                child: const Text('تصديرٌ جديد'),
              ),
            ],
          ),
          ExportFailed(:final failure) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                failure.message,
                style: t.textTheme.bodyMedium?.copyWith(
                  color: Palette.dangerSoft,
                ),
              ),
              const SizedBox(height: Space.md),
              OutlinedButton(
                onPressed: () => ctl.start(projectId),
                child: const Text('أعد المحاولة'),
              ),
            ],
          ),
        },
      ),
    );
  }
}
