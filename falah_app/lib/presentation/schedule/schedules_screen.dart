/// الجدولة — مواعيدُ تصديرٍ يحسبها **الخادمُ** لا الجهاز.
///
/// والقاعدةُ التي تظهر في هذه الشاشة: الموعدُ يُحفظ بمنطقته الزمنيّة،
/// ويُحسب في تلك المنطقة ثم يُحوَّل — فتبقى «السادسةُ صباحًا» سادسةً عبر
/// التوقيت الصيفيّ. ولو حسبه الجهازُ لانزلق ساعةً مرّتين في السنة، ولاختلف
/// بين جهازين لصاحبٍ واحد.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/failure.dart';
import '../../core/network/api_client.dart';
import '../../core/theme/tokens.dart';
import '../../domain/entities/project.dart';
import '../../domain/entities/schedule.dart';
import '../../domain/repositories/content_repository.dart';
import '../../shared/widgets/states.dart';
import '../providers.dart';

final schedulesProvider = FutureProvider.autoDispose<List<Schedule>>((
  ref,
) async {
  final r = await ref.watch(scheduleRepositoryProvider).list();
  switch (r) {
    case Ok(:final value):
      return value;
    case Err(:final failure):
      throw failure;
  }
});

class SchedulesScreen extends ConsumerWidget {
  const SchedulesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(schedulesProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('الجدولة')),
      body: async.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
          failure: asFailure(e),
          onRetry: () => ref.invalidate(schedulesProvider),
        ),
        data: (list) => list.isEmpty
            ? const EmptyView(
                message: 'لا جدولَ بعد.\nافتح مشروعًا ثم اجدِل تصديرَه.',
              )
            : RefreshIndicator(
                onRefresh: () async => ref.invalidate(schedulesProvider),
                child: ListView.builder(
                  padding: const EdgeInsets.all(Space.md),
                  itemCount: list.length,
                  itemBuilder: (_, i) => _ScheduleCard(schedule: list[i]),
                ),
              ),
      ),
    );
  }
}

class _ScheduleCard extends ConsumerStatefulWidget {
  const _ScheduleCard({required this.schedule});
  final Schedule schedule;

  @override
  ConsumerState<_ScheduleCard> createState() => _ScheduleCardState();
}

class _ScheduleCardState extends ConsumerState<_ScheduleCard> {
  bool _busy = false;

  Future<void> _run(Future<Result<void>> Function() op) async {
    setState(() => _busy = true);
    final r = await op();
    if (!mounted) return;
    setState(() => _busy = false);
    switch (r) {
      case Ok():
        ref.invalidate(schedulesProvider);
      case Err(:final failure):
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(failure.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.schedule;
    final t = Theme.of(context);
    final repo = ref.read(scheduleRepositoryProvider);

    return Card(
      margin: const EdgeInsets.only(bottom: Space.md),
      child: Padding(
        padding: const EdgeInsets.all(Space.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(child: Text(s.title, style: t.textTheme.titleSmall)),
                _StatusPill(status: s.status),
              ],
            ),
            const SizedBox(height: Space.sm),
            Wrap(
              spacing: Space.md,
              runSpacing: Space.xs,
              children: [
                _Meta(icon: Icons.schedule, text: s.timeLabel),
                _Meta(icon: Icons.repeat, text: s.recurrence.label),
                // **المنطقةُ تُعرض دائمًا.** بدونها يظنّ المسافرُ أنّ الموعدَ
                // انزلق، وهو ثابتٌ في منطقته التي اختارها.
                _Meta(icon: Icons.public, text: s.tz),
                if (s.runs > 0)
                  _Meta(icon: Icons.done_all, text: '${s.runs} تشغيلة'),
              ],
            ),
            if (s.nextRunAt != null) ...[
              const SizedBox(height: Space.sm),
              Text(
                'التالي: ${_fmt(s.nextRunAt!)}',
                style: t.textTheme.bodySmall,
              ),
            ],
            if (s.failures > 0) ...[
              const SizedBox(height: Space.sm),
              Row(
                children: [
                  Icon(
                    Icons.error_outline,
                    size: 15,
                    color: t.colorScheme.error,
                  ),
                  const SizedBox(width: Space.xs),
                  Text(
                    // فشلٌ يُعرض بعددِه: جدولٌ «نشطٌ» يفشل كلَّ مرّةٍ ليس نشطًا
                    '${s.failures} محاولةً فاشلة',
                    style: t.textTheme.bodySmall?.copyWith(
                      color: t.colorScheme.error,
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: Space.sm),
            Row(
              children: [
                if (s.status != ScheduleStatus.done)
                  TextButton.icon(
                    onPressed: _busy
                        ? null
                        : () => _run(
                            () => repo.setStatus(
                              s.id,
                              s.status == ScheduleStatus.active
                                  ? ScheduleStatus.paused
                                  : ScheduleStatus.active,
                            ),
                          ),
                    icon: Icon(
                      s.status == ScheduleStatus.active
                          ? Icons.pause
                          : Icons.play_arrow,
                      size: 18,
                    ),
                    label: Text(
                      s.status == ScheduleStatus.active ? 'تعليق' : 'تشغيل',
                    ),
                  ),
                const Spacer(),
                TextButton.icon(
                  onPressed: _busy ? null : () => _confirmDelete(repo, s.id),
                  icon: const Icon(Icons.delete_outline, size: 18),
                  label: const Text('حذف'),
                  style: TextButton.styleFrom(
                    foregroundColor: t.colorScheme.error,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// الحذفُ لا رجعةَ فيه فيُستأذَن — ولا يُحذف بضغطةٍ واحدةٍ عرَضيّة.
  Future<void> _confirmDelete(ScheduleRepository repo, int id) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('حذفُ الجدول؟'),
        content: const Text('لا رجعةَ فيه. والمشروعُ نفسُه لا يُحذف.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: const Text('إلغاء'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(c, true),
            child: const Text('حذف'),
          ),
        ],
      ),
    );
    if (ok == true) await _run(() => repo.delete(id));
  }

  static String _fmt(DateTime d) =>
      '${d.year}/${d.month.toString().padLeft(2, '0')}/'
      '${d.day.toString().padLeft(2, '0')} '
      '${d.hour.toString().padLeft(2, '0')}:'
      '${d.minute.toString().padLeft(2, '0')}';
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.status});
  final ScheduleStatus status;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final c = switch (status) {
      ScheduleStatus.active => t.colorScheme.primaryContainer,
      ScheduleStatus.paused => t.colorScheme.surfaceContainerHighest,
      ScheduleStatus.done => t.colorScheme.secondaryContainer,
    };
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Space.sm,
        vertical: Space.xs,
      ),
      decoration: BoxDecoration(borderRadius: Radii.pill, color: c),
      child: Text(status.label, style: t.textTheme.labelSmall),
    );
  }
}

class _Meta extends StatelessWidget {
  const _Meta({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: 14),
      const SizedBox(width: Space.xs),
      Text(text, style: Theme.of(context).textTheme.labelSmall),
    ],
  );
}

/// حوارُ إنشاء جدولٍ لمشروع — يُفتح من شاشة المشروع.
class ScheduleCreateSheet extends ConsumerStatefulWidget {
  const ScheduleCreateSheet({super.key, required this.project});
  final Project project;

  @override
  ConsumerState<ScheduleCreateSheet> createState() =>
      _ScheduleCreateSheetState();
}

class _ScheduleCreateSheetState extends ConsumerState<ScheduleCreateSheet> {
  Recurrence _recurrence = Recurrence.daily;
  TimeOfDay _time = const TimeOfDay(hour: 6, minute: 0);
  bool _busy = false;

  /// المنطقةُ من الجهاز **اقتراحًا لا حكمًا**: تُرسَل مع الطلب فيحفظها
  /// الخادمُ ويحسب بها. ولا يُحوَّل الوقتُ هنا إلى UTC — ذاك ما يكسر
  /// التوقيتَ الصيفيّ.
  String get _tz => DateTime.now().timeZoneName;

  Future<void> _save() async {
    setState(() => _busy = true);
    final r = await ref
        .read(scheduleRepositoryProvider)
        .create(
          projectId: widget.project.id,
          kind: 'export',
          title: widget.project.title,
          recurrence: _recurrence,
          tz: _tz,
          atMinute: _time.hour * 60 + _time.minute,
        );
    if (!mounted) return;
    setState(() => _busy = false);
    switch (r) {
      case Ok():
        Navigator.pop(context, true);
      case Err(:final failure):
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(failure.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Padding(
      padding: EdgeInsets.only(
        left: Space.lg,
        right: Space.lg,
        top: Space.lg,
        bottom: MediaQuery.of(context).viewInsets.bottom + Space.lg,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('جدولةُ التصدير', style: t.textTheme.titleMedium),
          const SizedBox(height: Space.lg),
          SegmentedButton<Recurrence>(
            segments: Recurrence.values
                .map((r) => ButtonSegment(value: r, label: Text(r.label)))
                .toList(),
            selected: {_recurrence},
            onSelectionChanged: (s) => setState(() => _recurrence = s.first),
          ),
          const SizedBox(height: Space.md),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.schedule),
            title: Text(
              '${_time.hour.toString().padLeft(2, '0')}:'
              '${_time.minute.toString().padLeft(2, '0')}',
            ),
            subtitle: Text('بتوقيت $_tz'),
            trailing: const Icon(Icons.edit_outlined, size: 18),
            onTap: () async {
              final picked = await showTimePicker(
                context: context,
                initialTime: _time,
              );
              if (picked != null) setState(() => _time = picked);
            },
          ),
          const SizedBox(height: Space.md),
          Text(
            'يُحسب الموعدُ في الخادم بمنطقتك — فيبقى ثابتًا عبر التوقيت '
            'الصيفيّ، ويعمل والتطبيقُ مغلق.',
            style: t.textTheme.bodySmall,
          ),
          const SizedBox(height: Space.lg),
          FilledButton(
            onPressed: _busy ? null : _save,
            child: Text(_busy ? 'يُحفظ…' : 'اجدِل'),
          ),
        ],
      ),
    );
  }
}
