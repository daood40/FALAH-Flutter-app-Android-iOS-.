/// النشر — **وكلُّ منصّةٍ تُعرض بحالتها الصريحة.**
///
/// وهذه الشاشةُ تفعل ما يُستثقَل عادةً: تعرض ما ليس منفَّذًا، معطَّلًا، مع
/// سببه. لأنّ إخفاءَ غيرِ المنفَّذ يجعل المستخدمَ يبحث عن إنستغرام فلا يجده
/// فيظنّه عطبًا؛ وعرضَه جاهزًا كذبٌ يُكتشف عند أوّل محاولة.
///
/// وأمّا الاعتماد: يُدخَل مرّةً ويذهب إلى الخادم فيُعمَّى هناك. **ولا يُحفظ
/// في الجهاز، ولا يُسجَّل، ولا يعود من الخادم أبدًا** — وأقصى ما يُعرض بعده
/// آخرُ أربعةِ محارفَ ليعرف صاحبُه أيَّ حسابٍ ربط.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/failure.dart';
import '../../core/network/api_client.dart';
import '../../core/theme/tokens.dart';
import '../../domain/entities/schedule.dart';
import '../../shared/widgets/states.dart';
import '../providers.dart';

final providersProvider = FutureProvider.autoDispose<List<PublishProvider>>((
  ref,
) async {
  final r = await ref.watch(publishRepositoryProvider).providers();
  switch (r) {
    case Ok(:final value):
      return value;
    case Err(:final failure):
      throw failure;
  }
});

final accountsProvider = FutureProvider.autoDispose<List<PublishAccount>>((
  ref,
) async {
  final r = await ref.watch(publishRepositoryProvider).accounts();
  switch (r) {
    case Ok(:final value):
      return value;
    case Err(:final failure):
      throw failure;
  }
});

class PublishScreen extends ConsumerWidget {
  const PublishScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final provs = ref.watch(providersProvider);
    final accs = ref.watch(accountsProvider);
    final t = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('النشر')),
      body: provs.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
          failure: asFailure(e),
          onRetry: () => ref.invalidate(providersProvider),
        ),
        data: (providers) => RefreshIndicator(
          onRefresh: () async {
            ref
              ..invalidate(providersProvider)
              ..invalidate(accountsProvider);
          },
          child: ListView(
            padding: const EdgeInsets.all(Space.md),
            children: [
              Text('الحساباتُ المربوطة', style: t.textTheme.titleSmall),
              const SizedBox(height: Space.sm),
              accs.when(
                loading: () => const Padding(
                  padding: EdgeInsets.symmetric(vertical: Space.lg),
                  child: LoadingView(),
                ),
                error: (e, _) => ErrorView(
                  failure: asFailure(e),
                  onRetry: () => ref.invalidate(accountsProvider),
                ),
                data: (list) => list.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.symmetric(vertical: Space.md),
                        child: Text(
                          'لا حسابَ مربوط.',
                          style: t.textTheme.bodySmall,
                        ),
                      )
                    : Column(
                        children: list
                            .map((a) => _AccountTile(account: a))
                            .toList(),
                      ),
              ),
              const SizedBox(height: Space.lg),
              Text('المنصّات', style: t.textTheme.titleSmall),
              const SizedBox(height: Space.sm),
              ...providers.map((p) => _ProviderTile(provider: p)),
              const SizedBox(height: Space.lg),
              Container(
                padding: const EdgeInsets.all(Space.md),
                decoration: BoxDecoration(
                  borderRadius: Radii.card,
                  color: t.colorScheme.surfaceContainerHighest,
                ),
                child: Text(
                  'لا يُدَّعى دعمُ منصّةٍ بلا تكاملٍ حقيقيٍّ يعمل. وما لم '
                  'يُنفَّذ يُعرض معطَّلًا مع سببه بدل أن يُخفى.',
                  style: t.textTheme.bodySmall,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AccountTile extends ConsumerStatefulWidget {
  const _AccountTile({required this.account});
  final PublishAccount account;

  @override
  ConsumerState<_AccountTile> createState() => _AccountTileState();
}

class _AccountTileState extends ConsumerState<_AccountTile> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final a = widget.account;
    return Card(
      margin: const EdgeInsets.only(bottom: Space.sm),
      child: ListTile(
        leading: const Icon(Icons.link),
        title: Text(a.label),
        // **التلميحُ كلُّ ما يُعرض من السرّ.** ولا زرَّ لإظهاره: لا يملك
        // العميلُ ما يُظهره — السرُّ لم يعد من الخادم قطّ.
        subtitle: Text('${a.provider} · ${a.hint}'),
        trailing: _busy
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : IconButton(
                tooltip: 'فصل',
                icon: const Icon(Icons.link_off),
                onPressed: () => _disconnect(a.id),
              ),
      ),
    );
  }

  Future<void> _disconnect(int id) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('فصلُ الحساب؟'),
        content: const Text(
          'يُحذف الاعتمادُ من الخادم. ولإعادة الربط تحتاج الرمزَ من جديد.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: const Text('إلغاء'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(c, true),
            child: const Text('فصل'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _busy = true);
    final r = await ref.read(publishRepositoryProvider).disconnect(id);
    if (!mounted) return;
    setState(() => _busy = false);
    switch (r) {
      case Ok():
        ref.invalidate(accountsProvider);
      case Err(:final failure):
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(failure.message)));
    }
  }
}

class _ProviderTile extends ConsumerWidget {
  const _ProviderTile({required this.provider});
  final PublishProvider provider;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final ready = provider.ready;
    return Card(
      margin: const EdgeInsets.only(bottom: Space.sm),
      child: Opacity(
        // المعطَّلُ يبقى مقروءًا: الشفافيّةُ إشارةٌ لا إخفاء
        opacity: ready ? 1 : 0.62,
        child: ListTile(
          leading: Icon(
            ready ? Icons.check_circle_outline : Icons.hourglass_empty,
            color: ready ? t.colorScheme.primary : null,
          ),
          title: Text(provider.name),
          subtitle: Text(provider.note, style: t.textTheme.bodySmall),
          trailing: ready
              ? FilledButton.tonal(
                  onPressed: () => _connect(context, ref),
                  child: const Text('ربط'),
                )
              : Text(provider.status.label, style: t.textTheme.labelSmall),
        ),
      ),
    );
  }

  Future<void> _connect(BuildContext context, WidgetRef ref) async {
    final done = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _ConnectSheet(provider: provider),
    );
    if (done == true) ref.invalidate(accountsProvider);
  }
}

class _ConnectSheet extends ConsumerStatefulWidget {
  const _ConnectSheet({required this.provider});
  final PublishProvider provider;

  @override
  ConsumerState<_ConnectSheet> createState() => _ConnectSheetState();
}

class _ConnectSheetState extends ConsumerState<_ConnectSheet> {
  final _secret = TextEditingController();
  final _label = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    // الحقلُ يُفرَّغ صراحةً عند الإغلاق. `TextEditingController` يحتفظ
    // بالنصّ في الذاكرة، والسرُّ لا يبقى بعد إرساله.
    _secret.clear();
    _secret.dispose();
    _label.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _busy = true);
    final r = await ref
        .read(publishRepositoryProvider)
        .connect(
          provider: widget.provider.key,
          secret: _secret.text.trim(),
          label: _label.text.trim(),
        );
    if (!mounted) return;
    setState(() => _busy = false);
    switch (r) {
      case Ok():
        _secret.clear();
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
          Text('ربطُ ${widget.provider.name}', style: t.textTheme.titleMedium),
          const SizedBox(height: Space.sm),
          Text(widget.provider.note, style: t.textTheme.bodySmall),
          const SizedBox(height: Space.lg),
          TextField(
            controller: _label,
            decoration: const InputDecoration(
              labelText: 'اسمٌ تعرفه به',
              hintText: 'قناتي',
            ),
          ),
          const SizedBox(height: Space.md),
          TextField(
            controller: _secret,
            // السرُّ لا يُعرض على الشاشة، ولا يدخل قاموسَ لوحة المفاتيح،
            // ولا تقترحه أدواتُ الإكمال التلقائيّ
            obscureText: true,
            autocorrect: false,
            enableSuggestions: false,
            decoration: const InputDecoration(
              labelText: 'رمزُ البوت',
              helperText: 'يُرسَل مرّةً ويُعمَّى في الخادم — ولا يعود',
            ),
          ),
          const SizedBox(height: Space.lg),
          FilledButton(
            onPressed: _busy || _secret.text.trim().length < 8 ? null : _save,
            child: Text(_busy ? 'يُربط…' : 'ربط'),
          ),
          const SizedBox(height: Space.sm),
          Text(
            'لا يُحفظ الرمزُ في هذا الجهاز، ولا يُسجَّل، ولا يُعاد إليك بعد '
            'الربط — يظهر منه آخرُ أربعةِ محارفَ فقط.',
            style: t.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
