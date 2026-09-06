/// إنشاءُ الحساب. رمزُ الدعوة يُطلب حين يعلن الخادمُ أن التسجيل مغلق.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/failure.dart';
import '../../core/routing/app_router.dart';
import '../../core/theme/tokens.dart';
import 'auth_controller.dart';
import 'auth_form_fields.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  final _watermark = TextEditingController();
  final _invite = TextEditingController();
  bool _busy = false;
  Failure? _error;

  @override
  void dispose() {
    for (final c in [_email, _password, _name, _watermark, _invite]) {
      c.dispose();
    }
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
        .register(
          email: _email.text.trim(),
          password: _password.text,
          name: _name.text.trim(),
          watermark: _watermark.text.trim(),
          invite: _invite.text.trim(),
        );
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = f;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('حساب جديد')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(Space.lg),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    PlainField(
                      controller: _name,
                      label: 'اسمك',
                      required: true,
                      maxLength: 60,
                    ),
                    const SizedBox(height: Space.md),
                    EmailField(controller: _email),
                    const SizedBox(height: Space.md),
                    PasswordField(controller: _password),
                    const SizedBox(height: Space.md),
                    PlainField(
                      controller: _watermark,
                      label: 'علامتك على البطاقة',
                      hint: 'قناة نور الهدى',
                      maxLength: 40,
                    ),
                    const SizedBox(height: Space.md),
                    PlainField(
                      controller: _invite,
                      label: 'رمز الدعوة (إن وُجد)',
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: Space.md),
                      Text(
                        _error!.message,
                        textAlign: TextAlign.center,
                        style: t.textTheme.bodySmall?.copyWith(
                          color: Palette.dangerSoft,
                        ),
                      ),
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
                          : const Text('أنشئ الحساب'),
                    ),
                    const SizedBox(height: Space.sm),
                    TextButton(
                      onPressed: _busy ? null : () => context.go(Routes.login),
                      child: const Text('لديك حساب؟ ادخل'),
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
