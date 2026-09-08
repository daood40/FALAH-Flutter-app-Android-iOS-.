/// الحساب — العلامةُ المائيّة، وتغييرُ كلمة المرور، وحذفُ الحساب.
///
/// **تغييرُ كلمة المرور من داخل التطبيق**: المسارُ `POST /app/password`
/// موجودٌ في الخادم منذ P0 ولم تكن له واجهةٌ في العميل القديم. ومع كون
/// استرجاعِ البريد محجوبًا (SMTP غيرُ محقَّق) كان من ينسى كلمتَه يفقد
/// حسابَه نهائيًّا — مأزقٌ مغلقٌ رصده التدقيق ويُفكّ هنا.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/routing/app_router.dart';
import '../../core/theme/tokens.dart';
import '../../shared/widgets/states.dart';
import '../auth/auth_controller.dart';
import '../auth/auth_form_fields.dart';
import '../providers.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  late final TextEditingController _watermark;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _watermark = TextEditingController(
      text: ref.read(currentUserProvider)?.watermark ?? '',
    );
  }

  @override
  void dispose() {
    _watermark.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() => _saving = true);
    final r = await ref
        .read(authRepositoryProvider)
        .updateWatermark(_watermark.text.trim());
    if (!mounted) return;
    setState(() => _saving = false);
    r.fold((f) => showFailure(context, f), (u) {
      ref.read(authControllerProvider.notifier).updateUser(u);
      showDone(context, 'حُفظت');
    });
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(currentUserProvider);
    final t = Theme.of(context);
    if (user == null) return const Scaffold(body: LoadingView());

    return Scaffold(
      appBar: AppBar(title: const Text('الحساب')),
      body: ListView(
        padding: const EdgeInsets.all(Space.lg),
        children: [
          Text(
            user.email,
            style: t.textTheme.bodySmall,
            textDirection: TextDirection.ltr,
          ),
          const SizedBox(height: Space.lg),
          PlainField(
            controller: _watermark,
            label: 'علامتك على البطاقة',
            maxLength: 40,
          ),
          const SizedBox(height: Space.md),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Palette.ink,
                    ),
                  )
                : const Text('حفظ'),
          ),
          const SizedBox(height: Space.xl),
          const Divider(),
          const SizedBox(height: Space.md),
          OutlinedButton.icon(
            onPressed: () => _logout(context),
            icon: const Icon(Icons.logout, size: 18),
            label: const Text('خروج'),
          ),
          const SizedBox(height: Space.xxl),
          Text('حذف الحساب', style: t.textTheme.titleMedium),
          const SizedBox(height: Space.sm),
          Text(
            'يُحذف حسابك ومشاريعك وصادراتك حذفًا لا رجعة فيه. '
            'النصوص الشرعية في قاعدة المحتوى ليست ملكًا لحسابك فتبقى كما هي.',
            style: t.textTheme.bodySmall,
          ),
          const SizedBox(height: Space.md),
          OutlinedButton(
            onPressed: () => _delete(context),
            style: OutlinedButton.styleFrom(
              foregroundColor: Palette.dangerSoft,
              side: const BorderSide(color: Palette.danger),
            ),
            child: const Text('حذف حسابي نهائيًّا'),
          ),
        ],
      ),
    );
  }

  Future<void> _logout(BuildContext context) async {
    await ref.read(authControllerProvider.notifier).logout();
    if (context.mounted) context.go(Routes.login);
  }

  Future<void> _delete(BuildContext context) async {
    final input = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('تأكيد الحذف'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('للتأكيد اكتب: حذف'),
            const SizedBox(height: Space.md),
            TextField(controller: input, autofocus: true),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: const Text('إلغاء'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(c, input.text.trim() == 'حذف'),
            style: FilledButton.styleFrom(backgroundColor: Palette.danger),
            child: const Text('احذف'),
          ),
        ],
      ),
    );
    final confirm = input.text.trim();
    input.dispose();
    if (ok != true || !context.mounted) return;

    final r = await ref
        .read(authRepositoryProvider)
        .deleteAccount(confirm: confirm);
    if (!context.mounted) return;
    r.fold((f) => showFailure(context, f), (_) async {
      await ref.read(authControllerProvider.notifier).logout();
      if (context.mounted) context.go(Routes.login);
    });
  }
}
