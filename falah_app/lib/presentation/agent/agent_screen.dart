/// وكيلُ فَلاح — سؤالٌ واحدٌ في كلِّ مرّة.
///
/// **وهو ليس نموذجًا لغويًّا، ولا يولّد نصًّا شرعيًّا.** أسئلتُه تُحدِّد
/// *الاختيار* لا *النصّ*: أيُّ سورة، أيُّ رقم، أيُّ تصميم. ثم يأخذ من قاعدة
/// المحتوى ما اجتاز الفحوصَ الخمسةَ والعشرين. وما لم يجتز يُترك ولا
/// يُستبدَل بشيء.
///
/// ولا يخرج شيءٌ من اختيارات المستخدم إلى أيِّ مزوّدٍ خارجيّ — المنطقُ كلُّه
/// في الخادم على قاعدةٍ محلّيّة.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/failure.dart';
import '../../core/network/api_client.dart';
import '../../core/routing/app_router.dart';
import '../../core/theme/tokens.dart';
import '../../domain/repositories/content_repository.dart';
import '../../shared/widgets/states.dart';
import '../providers.dart';

class AgentScreen extends ConsumerStatefulWidget {
  const AgentScreen({super.key});

  @override
  ConsumerState<AgentScreen> createState() => _AgentScreenState();
}

class _AgentScreenState extends ConsumerState<AgentScreen> {
  /// الإجاباتُ حالةُ هذه الشاشة، ويعيدها الخادمُ في كلِّ ردّ. ونُبقي نسختنا
  /// هي المصدر: الرجوعُ خطوةً حذفٌ من هذه الخريطة، وإعادةُ السؤال.
  Map<String, dynamic> _answers = {};
  final _history = <Map<String, dynamic>>[];

  AgentStep? _step;
  Failure? _error;
  bool _busy = true;
  bool _building = false;

  @override
  void initState() {
    super.initState();
    _ask();
  }

  Future<void> _ask() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final r = await ref.read(agentRepositoryProvider).ask(_answers);
    if (!mounted) return;
    switch (r) {
      case Ok(:final value):
        setState(() {
          _step = value;
          // الخادمُ ينقّي الإجاباتِ (`sanitize`) — فتُؤخذ نسختُه لا نسختُنا.
          // ولو أبقينا نسختَنا لبقيت فيها قيمةٌ رفضها الخادمُ صامتةً.
          _answers = Map<String, dynamic>.from(value.answers);
          _busy = false;
        });
      case Err(:final failure):
        setState(() {
          _error = failure;
          _busy = false;
        });
    }
  }

  void _answer(String key, String value) {
    _history.add(Map<String, dynamic>.from(_answers));
    _answers[key] = value;
    _ask();
  }

  void _back() {
    if (_history.isEmpty) return;
    _answers = _history.removeLast();
    _ask();
  }

  Future<void> _build() async {
    setState(() => _building = true);
    final r = await ref.read(agentRepositoryProvider).build(_answers);
    if (!mounted) return;
    setState(() => _building = false);
    switch (r) {
      case Ok(:final value):
        final planned = (_step?.plan?['cards'] as List?)?.length;
        if (!mounted) return;
        // **يُقال العددان حين يفترقان.** ما لم يجتز الفحصَ لحظةَ الإضافة
        // يُترك، فادّعاءُ الاكتمال هنا كذبٌ صغيرٌ يكتشفه المستخدمُ بنفسه.
        final msg = (planned != null && planned != value.added)
            ? 'أُنشئ المشروع · أُضيف ${value.added} من $planned '
                  '(البقيّةُ لم تجتز الفحص)'
            : 'أُنشئ المشروع · ${value.added} عنصرًا';
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(msg)));
        Routes.goProject(context, value.projectId);
      case Err(:final failure):
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(failure.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final s = _step;

    return Scaffold(
      appBar: AppBar(
        title: const Text('الوكيل'),
        leading: _history.isEmpty
            ? null
            : IconButton(
                icon: const Icon(Icons.arrow_forward),
                tooltip: 'رجوعٌ خطوة',
                onPressed: _busy ? null : _back,
              ),
        bottom: s == null
            ? null
            : PreferredSize(
                preferredSize: const Size.fromHeight(4),
                child: LinearProgressIndicator(value: s.progress, minHeight: 4),
              ),
      ),
      body: _error != null
          ? ErrorView(failure: _error!, onRetry: _ask)
          : _busy && s == null
          ? const LoadingView()
          : s == null
          ? const EmptyView(message: 'لا سؤال.')
          : ListView(
              padding: const EdgeInsets.all(Space.lg),
              children: [
                Text(
                  'الخطوة ${s.stepIndex + 1} من ${s.stepTotal}',
                  style: t.textTheme.labelSmall,
                ),
                const SizedBox(height: Space.sm),
                if (s.done) ..._plan(t, s) else ..._question(t, s),
              ],
            ),
      bottomNavigationBar: (s != null && s.done)
          ? SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(Space.md),
                child: FilledButton.icon(
                  onPressed: _building ? null : _build,
                  icon: _building
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.auto_awesome),
                  label: Text(_building ? 'يُنشئ…' : 'أنشئ المشروع'),
                ),
              ),
            )
          : null,
    );
  }

  List<Widget> _question(ThemeData t, AgentStep s) => [
    Text(s.question ?? '', style: t.textTheme.headlineSmall),
    if (s.why != null && s.why!.isNotEmpty) ...[
      const SizedBox(height: Space.sm),
      // **سببُ السؤال بنصّه من الخادم.** سؤالٌ بلا سببٍ يبدو تعنّتًا،
      // وسببٌ يؤلّفه العميلُ يفترق عن منطق الخادم يومًا.
      Container(
        padding: const EdgeInsets.all(Space.md),
        decoration: BoxDecoration(
          borderRadius: Radii.card,
          color: t.colorScheme.surfaceContainerHighest,
        ),
        child: Text(s.why!, style: t.textTheme.bodySmall),
      ),
    ],
    const SizedBox(height: Space.lg),
    if (_busy)
      const Padding(
        padding: EdgeInsets.symmetric(vertical: Space.xl),
        child: LoadingView(),
      )
    else
      ...s.options.map(
        (o) => Padding(
          padding: const EdgeInsets.only(bottom: Space.sm),
          child: Material(
            color: t.colorScheme.surfaceContainerLow,
            borderRadius: Radii.card,
            child: InkWell(
              borderRadius: Radii.card,
              onTap: () => _answer(s.questionId, o.value),
              child: Padding(
                padding: const EdgeInsets.all(Space.md),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(o.label, style: t.textTheme.titleSmall),
                          if (o.hint != null && o.hint!.isNotEmpty) ...[
                            const SizedBox(height: Space.xs),
                            Text(o.hint!, style: t.textTheme.bodySmall),
                          ],
                        ],
                      ),
                    ),
                    const Icon(Icons.chevron_left, size: 20),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    if (s.preview != null) ...[
      const SizedBox(height: Space.lg),
      _Preview(preview: s.preview!),
    ],
  ];

  List<Widget> _plan(ThemeData t, AgentStep s) {
    final cards = (s.plan?['cards'] as List?) ?? const [];
    return [
      Text('الخطّة جاهزة', style: t.textTheme.headlineSmall),
      const SizedBox(height: Space.sm),
      Text(
        '${cards.length} عنصرًا. وما لا يجتاز الفحصَ لحظةَ الإضافة يُترك '
        'ولا يُستبدَل — فقد يقلّ العددُ النهائيُّ عن هذا.',
        style: t.textTheme.bodySmall,
      ),
      const SizedBox(height: Space.lg),
      ...cards.whereType<Map>().take(20).map((c) {
        final ref_ = c['ref'];
        return Card(
          margin: const EdgeInsets.only(bottom: Space.sm),
          child: ListTile(
            dense: true,
            leading: Icon(
              c['kind'] == 'quran'
                  ? Icons.menu_book_outlined
                  : Icons.library_books_outlined,
              size: 18,
            ),
            title: Text(
              c['kind'] == 'quran'
                  ? 'سورة ${ref_ is Map ? ref_['surah'] : '؟'} · '
                        'الآية ${ref_ is Map ? ref_['ayah'] : '؟'}'
                  : '${ref_ is Map ? ref_['book'] : '؟'} · '
                        '${ref_ is Map ? ref_['no'] : '؟'}',
              style: t.textTheme.bodyMedium,
            ),
          ),
        );
      }),
      if (cards.length > 20)
        Padding(
          padding: const EdgeInsets.only(top: Space.sm),
          child: Text(
            'و${cards.length - 20} غيرها…',
            style: t.textTheme.bodySmall,
          ),
        ),
    ];
  }
}

/// المعاينة — تتغيّر مع كلِّ إجابة، وتعرض **النصَّ الذي اختاره الخادم**
/// لا نصًّا يبنيه العميل.
class _Preview extends StatelessWidget {
  const _Preview({required this.preview});
  final Map<String, dynamic> preview;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final cards = (preview['cards'] as List?) ?? const [];
    final first = cards.isEmpty ? null : cards.first;
    final title = preview['title'];
    return Container(
      padding: const EdgeInsets.all(Space.md),
      decoration: BoxDecoration(
        borderRadius: Radii.card,
        border: Border.all(color: t.colorScheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.visibility_outlined, size: 15),
              const SizedBox(width: Space.xs),
              Text('معاينة', style: t.textTheme.labelSmall),
            ],
          ),
          const SizedBox(height: Space.sm),
          if (title != null)
            Text('$title', style: t.textTheme.titleSmall)
          else if (first != null)
            Text('$first', maxLines: 3, style: t.textTheme.bodySmall)
          else
            Text('لا معاينةَ بعد.', style: t.textTheme.bodySmall),
        ],
      ),
    );
  }
}
