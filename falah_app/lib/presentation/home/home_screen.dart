/// الرئيسية — المشاريعُ وما بقي من الحصّة.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/failure.dart';
import '../../core/routing/app_router.dart';
import '../../core/theme/tokens.dart';
import '../../core/utils/arabic.dart';
import '../../domain/entities/entitlements.dart';
import '../../domain/entities/project.dart';
import '../../shared/widgets/states.dart';
import '../auth/auth_controller.dart';
import '../providers.dart';
import 'home_controller.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final projects = ref.watch(projectsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('فَلاح'),
        actions: [
          IconButton(
            onPressed: () => context.push(Routes.browse),
            icon: const Icon(Icons.search),
            tooltip: 'تصفّح',
          ),
          IconButton(
            onPressed: () => context.push(Routes.schedules),
            icon: const Icon(Icons.schedule_outlined),
            tooltip: 'الجدولة',
          ),
          IconButton(
            onPressed: () => context.push(Routes.publish),
            icon: const Icon(Icons.send_outlined),
            tooltip: 'النشر',
          ),
          IconButton(
            onPressed: () => context.push(Routes.plans),
            icon: const Icon(Icons.workspace_premium_outlined),
            tooltip: 'الخطط',
          ),
          IconButton(
            onPressed: () => context.push(Routes.profile),
            icon: const Icon(Icons.person_outline),
            tooltip: 'الحساب',
          ),
          IconButton(
            onPressed: () => context.push(Routes.settings),
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'الإعدادات',
          ),
        ],
      ),
      floatingActionButton: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          // الوكيلُ أسرعُ طريقٍ إلى سلسلةٍ كاملة، فيُعرض بجوار الإنشاء
          // اليدويّ لا مدفونًا في قائمة.
          FloatingActionButton.small(
            heroTag: 'agent',
            onPressed: () => context.push(Routes.agent),
            tooltip: 'الوكيل',
            child: const Icon(Icons.auto_awesome),
          ),
          const SizedBox(height: Space.sm),
          FloatingActionButton.extended(
            heroTag: 'create',
            onPressed: () => _createProject(context, ref),
            icon: const Icon(Icons.add),
            label: const Text('مشروع جديد'),
            backgroundColor: Palette.gold,
            foregroundColor: Palette.ink,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(projectsProvider);
          ref.invalidate(entitlementsProvider);
          await ref.read(projectsProvider.future);
        },
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            Space.md,
            Space.md,
            Space.md,
            Space.xxl * 2,
          ),
          children: [
            if (user != null) _Greeting(name: user.name),
            const SizedBox(height: Space.md),
            const _QuotaCard(),
            const SizedBox(height: Space.lg),
            Text('مشاريعي', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: Space.sm),
            projects.when(
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: Space.xxl),
                child: LoadingView(),
              ),
              error: (e, _) => Padding(
                padding: const EdgeInsets.symmetric(vertical: Space.lg),
                child: ErrorView(
                  failure: e is Failure ? e : const UnknownFailure(),
                  onRetry: () => ref.invalidate(projectsProvider),
                ),
              ),
              data: (list) => list.isEmpty
                  ? const Padding(
                      padding: EdgeInsets.symmetric(vertical: Space.xl),
                      child: EmptyView(
                        message:
                            'لا مشاريع بعد.\nابدأ واحدًا وسيبني الوكيلُ معك أوّلَ بطاقة.',
                      ),
                    )
                  : Column(
                      children: [
                        for (final p in list) ...[
                          _ProjectTile(project: p),
                          const SizedBox(height: Space.sm),
                        ],
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _createProject(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController(text: 'سلسلة جديدة');
    final title = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('عنوان المشروع'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: 'مثال: من سورة الكوثر'),
          onSubmitted: (v) => Navigator.pop(c, v.trim()),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c),
            child: const Text('إلغاء'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(c, controller.text.trim()),
            child: const Text('أنشئ'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (title == null || title.isEmpty || !context.mounted) return;

    final r = await ref.read(projectRepositoryProvider).create(title);
    if (!context.mounted) return;
    // **كلُّ نداءٍ يُعالَج فشلُه.** لا نداءَ صامتٌ في هذا العميل.
    r.fold((f) => showFailure(context, f), (p) {
      ref.invalidate(projectsProvider);
      context.push(Routes.projectOf(p.id));
    });
  }
}

class _Greeting extends StatelessWidget {
  const _Greeting({required this.name});
  final String name;

  @override
  Widget build(BuildContext context) =>
      Text('أهلًا، $name', style: Theme.of(context).textTheme.headlineSmall);
}

class _QuotaCard extends ConsumerWidget {
  const _QuotaCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ent = ref.watch(entitlementsProvider);
    return ent.when(
      loading: () => const Card(
        child: Padding(
          padding: EdgeInsets.all(Space.lg),
          child: SizedBox(height: 44, child: LoadingView()),
        ),
      ),
      // فشلُ الحقوق لا يُفرغ الشاشة: المشاريعُ تبقى ظاهرةً وتُعرض ملاحظة
      error: (e, _) => Card(
        child: Padding(
          padding: const EdgeInsets.all(Space.md),
          child: Text(
            e is Failure ? e.message : 'تعذّر جلبُ حالة الخطّة',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      ),
      data: (e) => _QuotaBody(e),
    );
  }
}

class _QuotaBody extends StatelessWidget {
  const _QuotaBody(this.ent);
  final Entitlements ent;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(Space.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(ent.planName, style: t.textTheme.titleMedium),
                const SizedBox(width: Space.sm),
                if (!ent.isActive)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: Space.sm,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: Palette.danger.withValues(alpha: 0.15),
                      borderRadius: Radii.pill,
                    ),
                    child: Text('منتهية', style: t.textTheme.bodySmall),
                  ),
              ],
            ),
            const SizedBox(height: Space.md),
            for (final m in const ['cards', 'videos', 'projects'])
              if (ent.limitOf(m) > 0 || m == 'cards')
                Padding(
                  padding: const EdgeInsets.only(bottom: Space.sm),
                  child: _Meter(
                    label: _label(m),
                    left: ent.leftOf(m),
                    limit: ent.limitOf(m),
                  ),
                ),
          ],
        ),
      ),
    );
  }

  static String _label(String metric) => switch (metric) {
    'cards' => 'بطاقات',
    'videos' => 'مقاطع',
    'projects' => 'مشاريع',
    _ => metric,
  };
}

class _Meter extends StatelessWidget {
  const _Meter({required this.label, required this.left, required this.limit});
  final String label;
  final int left;
  final int limit;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final ratio = limit == 0 ? 0.0 : (left / limit).clamp(0.0, 1.0);
    return Row(
      children: [
        SizedBox(width: 62, child: Text(label, style: t.textTheme.bodySmall)),
        Expanded(
          child: ClipRRect(
            borderRadius: Radii.pill,
            child: LinearProgressIndicator(
              value: ratio,
              minHeight: 7,
              backgroundColor: t.colorScheme.outline,
              color: ratio < 0.15 ? Palette.danger : Palette.gold,
            ),
          ),
        ),
        const SizedBox(width: Space.sm),
        Text(
          '${arabicNum(left)} / ${arabicNum(limit)}',
          style: t.textTheme.bodySmall,
        ),
      ],
    );
  }
}

class _ProjectTile extends StatelessWidget {
  const _ProjectTile({required this.project});
  final Project project;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Card(
      child: InkWell(
        borderRadius: Radii.card,
        onTap: () => context.push(Routes.projectOf(project.id)),
        child: Padding(
          padding: const EdgeInsets.all(Space.md),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      project.title,
                      style: t.textTheme.titleMedium,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: Space.xs),
                    Text(
                      '${arabicNum(project.itemCount)} عناصر · '
                      '${ratioLabel(project.ratio)} · ${skinLabel(project.skin)}',
                      style: t.textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_left, size: 22),
            ],
          ),
        ),
      ),
    );
  }
}
