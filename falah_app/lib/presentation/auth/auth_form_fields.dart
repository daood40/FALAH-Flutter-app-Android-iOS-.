/// حقولُ نماذج المصادقة — تحقّقٌ محلّيٌّ **قبل** الشبكة، لا بدلًا عنها.
///
/// الفائدةُ تجربةُ استعمالٍ لا أمان: خطأٌ مطبعيٌّ في البريد يُقال فورًا بلا
/// انتظارِ دورةِ شبكة. والتحقّقُ الحقيقيُّ في الخادم — `falah/auth.py`
/// يفرض قواعدَه سواءٌ مرّ الطلبُ من هنا أو من `curl`.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// شرطُ الخادم لكلمة المرور، كما في `falah/auth.py`. مكتوبٌ هنا نصًّا
/// واحدًا كي لا يتفرّق في شاشتين فيختلفان.
const int kMinPasswordLength = 10;

class EmailField extends StatelessWidget {
  const EmailField({super.key, required this.controller, this.enabled = true});
  final TextEditingController controller;
  final bool enabled;

  @override
  Widget build(BuildContext context) => TextFormField(
    controller: controller,
    enabled: enabled,
    keyboardType: TextInputType.emailAddress,
    autofillHints: const [AutofillHints.email],
    textInputAction: TextInputAction.next,
    // البريدُ لاتينيٌّ دائمًا: يُجبَر الاتّجاهُ فلا ينقلب في واجهةٍ عربية
    textDirection: TextDirection.ltr,
    inputFormatters: [FilteringTextInputFormatter.deny(RegExp(r'\s'))],
    decoration: const InputDecoration(
      labelText: 'البريد',
      hintText: 'name@example.com',
    ),
    validator: (v) {
      final s = (v ?? '').trim();
      if (s.isEmpty) return 'البريد مطلوب';
      // فحصٌ بسيطٌ عمدًا: التعبيرُ المطابقُ للمعيار لا يُكتب، والخادمُ
      // يتحقّق بإرسالِ رسالةٍ فعليّة
      if (!s.contains('@') || !s.contains('.') || s.length < 6) {
        return 'بريدٌ غيرُ صالح';
      }
      return null;
    },
  );
}

class PasswordField extends StatefulWidget {
  const PasswordField({
    super.key,
    required this.controller,
    this.onSubmit,
    this.label = 'كلمة المرور',
    this.enabled = true,
    this.validateStrength = true,
  });

  final TextEditingController controller;
  final VoidCallback? onSubmit;
  final String label;
  final bool enabled;

  /// في التسجيل تُفرض القواعد؛ وفي الدخول لا — كلمةٌ قديمةٌ صحيحةٌ يجب
  /// أن تمرّ ولو خالفت قواعدَ اليوم.
  final bool validateStrength;

  @override
  State<PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<PasswordField> {
  bool _hidden = true;

  @override
  Widget build(BuildContext context) => TextFormField(
    controller: widget.controller,
    enabled: widget.enabled,
    obscureText: _hidden,
    textDirection: TextDirection.ltr,
    autofillHints: const [AutofillHints.password],
    textInputAction: TextInputAction.done,
    onFieldSubmitted: (_) => widget.onSubmit?.call(),
    decoration: InputDecoration(
      labelText: widget.label,
      suffixIcon: IconButton(
        onPressed: () => setState(() => _hidden = !_hidden),
        icon: Icon(
          _hidden ? Icons.visibility_outlined : Icons.visibility_off_outlined,
        ),
        tooltip: _hidden ? 'إظهار' : 'إخفاء',
      ),
    ),
    validator: (v) {
      final s = v ?? '';
      if (s.isEmpty) return 'كلمة المرور مطلوبة';
      if (widget.validateStrength && s.length < kMinPasswordLength) {
        return 'عشرةُ محارفَ فأكثر';
      }
      return null;
    },
  );
}

class PlainField extends StatelessWidget {
  const PlainField({
    super.key,
    required this.controller,
    required this.label,
    this.hint,
    this.required = false,
    this.enabled = true,
    this.maxLength,
  });

  final TextEditingController controller;
  final String label;
  final String? hint;
  final bool required;
  final bool enabled;
  final int? maxLength;

  @override
  Widget build(BuildContext context) => TextFormField(
    controller: controller,
    enabled: enabled,
    maxLength: maxLength,
    textInputAction: TextInputAction.next,
    decoration: InputDecoration(
      labelText: label,
      hintText: hint,
      counterText: '',
    ),
    validator: required
        ? (v) => (v ?? '').trim().isEmpty ? '$label مطلوب' : null
        : null,
  );
}
