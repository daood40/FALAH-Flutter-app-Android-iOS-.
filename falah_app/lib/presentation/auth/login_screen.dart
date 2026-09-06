/// شاشةُ الدخول — وتعرض سببَ انتهاء الجلسة إن كان الوصولُ إليها بسببه.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/failure.dart';
import '../../core/routing/app_router.dart';
import '../../core/theme/tokens.dart';
import 'auth_controller.dart';
import 'auth_form_fields.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  Failure? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || !(_form.currentState?.validate() ?? false)) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final f = await ref
        .read(authControllerProvider.notifier)
        .login(_email.text.trim(), _password.text);
    if (!mounted) return;
    // **الزرُّ يُحرَّر دائمًا** — نجحَ أو فشل. العيبُ الذي رصده التدقيق في
    // العميل القديم أن زرًّا عُطّل ولم يُحرَّر عند الفشل، فعلق أبدًا.
    setState(() {
      _busy = false;
      _error = f;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final auth = ref.watch(authControllerProvider);
    final expiredNotice = auth is AuthExpired ? auth.reason : null;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Space.lg),
            child: ConstrainedBox(
              // حدٌّ أعلى للعرض: على اللوح لا يمتدّ الحقلُ عبر الشاشة
              constraints: const BoxConstraints(maxWidth: 460),
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'فَلاح',
                      textAlign: TextAlign.center,
                      style: t.textTheme.displaySmall?.copyWith(
                        color: Palette.gold,
                      ),
                    ),
                    const SizedBox(height: Space.xs),
                    Text(
                      'ادخل إلى مساحتك',
                      textAlign: TextAlign.center,
                      style: t.textTheme.bodySmall,
                    ),
                    const SizedBox(height: Space.xl),

                    if (expiredNotice != null) ...[
                      _Notice(expiredNotice),
                      const SizedBox(height: Space.md),
                    ],

                    EmailField(controller: _email),
                    const SizedBox(height: Space.md),
                    PasswordField(
                      controller: _password,
                      onSubmit: _submit,
                      // الدخولُ لا يفرض قواعدَ التعقيد: كلمةٌ قديمةٌ صحيحةٌ
                      // يجب أن تمرّ ولو خالفت قواعدَ اليوم
                      validateStrength: false,
                    ),

                    if (_error != null) ...[
                      const SizedBox(height: Space.md),
                      _ErrorText(_error!),
                    ],

                    const SizedBox(height: Space.lg),
                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      child: _busy
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Palette.ink,
                              ),
                            )
                          : const Text('دخول'),
                    ),
                    const SizedBox(height: Space.sm),
                    TextButton(
                      onPressed: _busy
                          ? null
                          : () {
                              ref
                                  .read(authControllerProvider.notifier)
                                  .clearExpiryNotice();
                              context.go(Routes.register);
                            },
                      child: const Text('ليس لك حساب؟ أنشئ واحدًا'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(Space.md),
    decoration: BoxDecoration(
      color: Palette.warn.withValues(alpha: 0.12),
      borderRadius: Radii.card,
      border: Border.all(color: Palette.warn.withValues(alpha: 0.4)),
    ),
    child: Text(
      text,
      style: Theme.of(context).textTheme.bodySmall,
      textAlign: TextAlign.center,
    ),
  );
}

class _ErrorText extends StatelessWidget {
  const _ErrorText(this.failure);
  final Failure failure;

  @override
  Widget build(BuildContext context) => Text(
    failure.message,
    textAlign: TextAlign.center,
    style: Theme.of(
      context,
    ).textTheme.bodySmall?.copyWith(color: Palette.dangerSoft),
  );
}
