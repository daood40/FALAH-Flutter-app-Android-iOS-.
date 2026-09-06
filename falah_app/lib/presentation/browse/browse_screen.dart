/// تصفّحُ القرآن والحديث — وإضافةُ نصٍّ إلى مشروعٍ **بمرجعه لا بمتنه**.
///
/// وأهمُّ ما في هذه الشاشة ليس البحث، بل ما تُظهره حول النصّ: من أين جاء،
/// وهل اجتاز الفحص، وما حكمُه إن كان حديثًا. فالإسنادُ وعدُ هذا المنتَج،
/// ولا يُوفى بوعدٍ لا يراه صاحبُه.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/failure.dart';
import '../../core/network/api_client.dart';
import '../../core/theme/tokens.dart';
import '../../domain/entities/content.dart';
import '../../shared/widgets/states.dart';
import '../providers.dart';
import 'browse_controller.dart';

class BrowseScreen extends ConsumerStatefulWidget {
  const BrowseScreen({super.key, this.projectId});

  /// حين يأتي المستخدمُ من مشروعٍ يظهر زرُّ الإضافة. وحين يتصفّح وحدَه
  /// يبقى القراءةُ فقط — ولا يُعرض زرٌّ لا وجهةَ له.
  final int? projectId;

  @override
  ConsumerState<BrowseScreen> createState() => _BrowseScreenState();
}

class _BrowseScreenState extends ConsumerState<BrowseScreen> {
  final _q = TextEditingController();
  BrowseKind _kind = BrowseKind.quran;
  final _adding = <String>{};

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  void _search() =>
      ref.read(browseControllerProvider.notifier).query(_q.text, _kind);

  Future<void> _add(
    String kind,
    Map<String, dynamic> itemRef,
    String key,
  ) async {
    final pid = widget.projectId;
    if (pid == null) return;
    setState(() => _adding.add(key));
    final r = await ref
        .read(projectRepositoryProvider)
        .addItem(projectId: pid, kind: kind, ref: itemRef);
    if (!mounted) return;
    setState(() => _adding.remove(key));
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text(switch (r) {
          Ok() => 'أُضيف إلى المشروع',
          // **رسالةُ الخادم بنصّها**: هو من يعرف أيَّ فحصٍ سقط، والعميلُ
          // لا يؤلّف سببًا من عنده («محجوب — لم يجتز الفحص: …»).
          Err(:final failure) => failure.message,
        }),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(browseControllerProvider);
    final t = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.projectId == null ? 'تصفّح' : 'إضافةٌ إلى المشروع'),
        actions: [
          IconButton(
            tooltip: 'المصادر',
            icon: const Icon(Icons.verified_outlined),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const SourcesScreen()),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(Space.md),
            child: Column(
              children: [
                SegmentedButton<BrowseKind>(
                  segments: const [
                    ButtonSegment(
                      value: BrowseKind.quran,
                      label: Text('القرآن'),
                    ),
                    ButtonSegment(
                      value: BrowseKind.hadith,
                      label: Text('الحديث'),
                    ),
                  ],
                  selected: {_kind},
                  onSelectionChanged: (s) {
                    setState(() => _kind = s.first);
                    _search();
                  },
                ),
                const SizedBox(height: Space.md),
                TextField(
                  controller: _q,
                  autofocus: true,
                  textDirection: TextDirection.rtl,
                  decoration: InputDecoration(
                    hintText: _kind == BrowseKind.quran
                        ? 'ابحث في القرآن…'
                        : 'ابحث في الحديث…',
                    prefixIcon: const Icon(Icons.search),
                    suffixIcon: _q.text.isEmpty
                        ? null
                        : IconButton(
                            icon: const Icon(Icons.close),
                            onPressed: () {
                              _q.clear();
                              ref
                                  .read(browseControllerProvider.notifier)
                                  .clear();
                              setState(() {});
                            },
                          ),
                  ),
                  onChanged: (_) {
                    setState(() {});
                    _search();
                  },
                ),
              ],
            ),
          ),
          Expanded(
            child: switch (state) {
              BrowseIdle() => const EmptyView(
                message:
                    'اكتب كلمةً للبحث.\nالنتائجُ من قاعدة المحتوى '
                    'الموثَّقة — ولا يُولَّد نصٌّ.',
              ),
              BrowseSearching() => const LoadingView(label: 'يبحث…'),
              BrowseFailed(:final failure) => ErrorView(
                failure: failure,
                onRetry: _search,
              ),
              BrowseResults r when r.isEmpty => const EmptyView(
                message: 'لا نتيجة. جرّب كلمةً أخرى.',
              ),
              BrowseResults r => ListView(
                padding: const EdgeInsets.fromLTRB(
                  Space.md,
                  0,
                  Space.md,
                  Space.xxl,
                ),
                children: [
                  ...r.ayat.map(
                    (a) => _AyahCard(
                      hit: a,
                      canAdd: widget.projectId != null,
                      busy: _adding.contains('q${a.surah}:${a.ayah}'),
                      onAdd: () =>
                          _add('quran', a.ref, 'q${a.surah}:${a.ayah}'),
                    ),
                  ),
                  ...r.hadiths.map(
                    (h) => _HadithCard(
                      hit: h,
                      canAdd: widget.projectId != null,
                      busy: _adding.contains('h${h.book}:${h.number}'),
                      onAdd: () =>
                          _add('hadith', h.ref, 'h${h.book}:${h.number}'),
                    ),
                  ),
                ],
              ),
            },
          ),
        ],
      ),
      bottomNavigationBar: state is BrowseResults && !state.isEmpty
          ? Material(
              color: t.colorScheme.surfaceContainerHighest,
              child: Padding(
                padding: const EdgeInsets.all(Space.sm),
                child: Text(
                  'النصوصُ من مصادرَ موثَّقةٍ — ولا يُولَّد نصٌّ شرعيٌّ بذكاءٍ '
                  'اصطناعيّ.',
                  textAlign: TextAlign.center,
                  style: t.textTheme.bodySmall,
                ),
              ),
            )
          : null,
    );
  }
}

/// بطاقةٌ مشتركةُ الشكل: النصُّ ثم شريطُ الإسناد ثم الفعل.
class _Card extends StatelessWidget {
  const _Card({
    required this.text,
    required this.title,
    required this.meta,
    required this.ok,
    required this.canAdd,
    required this.busy,
    required this.onAdd,
  });

  final String text;
  final String title;
  final List<Widget> meta;
  final bool ok;
  final bool canAdd;
  final bool busy;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: Space.md),
      child: Padding(
        padding: const EdgeInsets.all(Space.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              text,
              textDirection: TextDirection.rtl,
              style: t.textTheme.titleMedium?.copyWith(height: 2.0),
            ),
            const SizedBox(height: Space.md),
            Wrap(spacing: Space.sm, runSpacing: Space.xs, children: meta),
            if (!ok) ...[
              const SizedBox(height: Space.sm),
              Row(
                children: [
                  Icon(Icons.block, size: 16, color: t.colorScheme.error),
                  const SizedBox(width: Space.xs),
                  Expanded(
                    child: Text(
                      // **يُعرض المحجوبُ ولا يُخفى**: الإخفاءُ يُوهم أنّ النصَّ
                      // مفقودٌ من القاعدة، والصوابُ أنه موجودٌ ولم يجتز.
                      'لم يجتز فحوصَ البطاقة — لا يُضاف',
                      style: t.textTheme.bodySmall?.copyWith(
                        color: t.colorScheme.error,
                      ),
                    ),
                  ),
                ],
              ),
            ],
            if (canAdd) ...[
              const SizedBox(height: Space.sm),
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: FilledButton.tonalIcon(
                  onPressed: (!ok || busy) ? null : onAdd,
                  icon: busy
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.add, size: 18),
                  label: Text(busy ? 'يُضاف…' : 'أضِف'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _AyahCard extends StatelessWidget {
  const _AyahCard({
    required this.hit,
    required this.canAdd,
    required this.busy,
    required this.onAdd,
  });

  final AyahHit hit;
  final bool canAdd;
  final bool busy;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) => _Card(
    text: hit.text,
    title: hit.label,
    ok: hit.cardOk,
    canAdd: canAdd,
    busy: busy,
    onAdd: onAdd,
    meta: [
      _Chip(label: hit.surahName, icon: Icons.menu_book_outlined),
      _Chip(label: 'الآية ${hit.ayah}'),
      if (hit.page > 0) _Chip(label: 'صفحة ${hit.page}'),
    ],
  );
}

class _HadithCard extends StatelessWidget {
  const _HadithCard({
    required this.hit,
    required this.canAdd,
    required this.busy,
    required this.onAdd,
  });

  final HadithHit hit;
  final bool canAdd;
  final bool busy;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) => _Card(
    text: hit.matn,
    title: hit.label,
    ok: hit.cardOk,
    canAdd: canAdd,
    busy: busy,
    onAdd: onAdd,
    meta: [
      _Chip(label: hit.bookName, icon: Icons.library_books_outlined),
      _Chip(label: 'رقم ${hit.number}'),
      // **الحكمُ من المصدر أو لا يُعرض.** ولا يُكتب «غير معروف» في مكانه:
      // فراغُ الحكم معلومةٌ، وملؤه بتخمينٍ تحريف.
      if (hit.grade.isNotEmpty)
        _Chip(label: hit.grade, icon: Icons.verified_outlined, strong: true),
      if (hit.narrator != null && hit.narrator!.isNotEmpty)
        _Chip(label: hit.narrator!),
    ],
  );
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label, this.icon, this.strong = false});
  final String label;
  final IconData? icon;
  final bool strong;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Space.sm,
        vertical: Space.xs,
      ),
      decoration: BoxDecoration(
        borderRadius: Radii.pill,
        color: strong
            ? t.colorScheme.primaryContainer
            : t.colorScheme.surfaceContainerHighest,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 13),
            const SizedBox(width: Space.xs),
          ],
          Text(label, style: t.textTheme.labelSmall),
        ],
      ),
    );
  }
}

/// شاشةُ المصادر — **الإسنادُ معروضًا لا موعودًا.**
class SourcesScreen extends ConsumerWidget {
  const SourcesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(sourcesProvider);
    final t = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('المصادر')),
      body: async.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
          failure: asFailure(e),
          onRetry: () => ref.invalidate(sourcesProvider),
        ),
        data: (list) => list.isEmpty
            ? const EmptyView(message: 'لا مصادرَ معلَنة.')
            : ListView.separated(
                padding: const EdgeInsets.all(Space.md),
                itemCount: list.length + 1,
                separatorBuilder: (_, _) => const SizedBox(height: Space.sm),
                itemBuilder: (context, i) {
                  if (i == 0) {
                    return Padding(
                      padding: const EdgeInsets.only(bottom: Space.sm),
                      child: Text(
                        'كلُّ نصٍّ في فَلاح منقولٌ من مصدرٍ من هذه القائمة. '
                        'وما لم يُمكن التحقّقُ منه يُحجَب مع ذكر السبب، ولا '
                        'يُستبدَل بشيءٍ من عند التطبيق.',
                        style: t.textTheme.bodySmall,
                      ),
                    );
                  }
                  final s = list[i - 1];
                  return Card(
                    child: ListTile(
                      title: Text(s.name),
                      subtitle: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const SizedBox(height: Space.xs),
                          Text(s.origin, style: t.textTheme.bodySmall),
                          const SizedBox(height: Space.xs),
                          Row(
                            children: [
                              Icon(
                                s.licenseUnsettled
                                    ? Icons.warning_amber_rounded
                                    : Icons.check_circle_outline,
                                size: 15,
                                color: s.licenseUnsettled
                                    ? t.colorScheme.error
                                    : t.colorScheme.primary,
                              ),
                              const SizedBox(width: Space.xs),
                              Expanded(
                                child: Text(
                                  s.licenseStatus,
                                  style: t.textTheme.labelSmall?.copyWith(
                                    color: s.licenseUnsettled
                                        ? t.colorScheme.error
                                        : null,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                      trailing: s.enabled
                          ? null
                          : const Icon(Icons.pause_circle_outline),
                    ),
                  );
                },
              ),
      ),
    );
  }
}
