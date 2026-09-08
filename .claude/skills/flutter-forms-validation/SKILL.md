---
name: flutter-forms-validation
description: Build Flutter forms — TextFormField, validators, focus management, input formatters, Arabic/English phone and email validation, multi-step forms, and submit state. Use when creating login/signup/data-entry screens, or when the user says "نموذج", "تسجيل دخول", "تحقق من المدخلات", "form", "validation", "login screen".
---

# Flutter Forms & Validation

## Structure

```dart
class LoginForm extends StatefulWidget {
  const LoginForm({super.key});
  @override
  State<LoginForm> createState() => _LoginFormState();
}

class _LoginFormState extends State<LoginForm> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _passwordFocus = FocusNode();
  bool _obscure = true;
  bool _submitting = false;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    FocusScope.of(context).unfocus();
    setState(() => _submitting = true);
    try {
      await ref.read(authProvider).signIn(_email.text.trim(), _password.text);
    } on AuthException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      autovalidateMode: AutovalidateMode.onUserInteraction,
      child: Column(
        children: [
          TextFormField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            textInputAction: TextInputAction.next,
            autofillHints: const [AutofillHints.email],
            decoration: const InputDecoration(labelText: 'البريد الإلكتروني'),
            validator: Validators.email,
            onFieldSubmitted: (_) => _passwordFocus.requestFocus(),
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _password,
            focusNode: _passwordFocus,
            obscureText: _obscure,
            textInputAction: TextInputAction.done,
            autofillHints: const [AutofillHints.password],
            decoration: InputDecoration(
              labelText: 'كلمة المرور',
              suffixIcon: IconButton(
                icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                onPressed: () => setState(() => _obscure = !_obscure),
              ),
            ),
            validator: Validators.password,
            onFieldSubmitted: (_) => _submit(),
          ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _submitting ? null : _submit,
            child: _submitting
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('دخول'),
          ),
        ],
      ),
    );
  }
}
```

Key points: `autovalidateMode: onUserInteraction` (never `always` — it shows errors before the user types), disable the button while submitting, always `dispose()` controllers and focus nodes, always check `mounted` after an `await`.

## Validators

```dart
abstract class Validators {
  static String? required(String? v) =>
      (v == null || v.trim().isEmpty) ? 'هذا الحقل مطلوب' : null;

  static String? email(String? v) {
    if (v == null || v.trim().isEmpty) return 'البريد الإلكتروني مطلوب';
    final ok = RegExp(r'^[\w.+-]+@[\w-]+\.[\w.-]+$').hasMatch(v.trim());
    return ok ? null : 'صيغة البريد غير صحيحة';
  }

  static String? password(String? v) {
    if (v == null || v.isEmpty) return 'كلمة المرور مطلوبة';
    if (v.length < 8) return 'يجب ألا تقل عن 8 أحرف';
    return null;
  }

  static String? libyanPhone(String? v) {
    final digits = (v ?? '').replaceAll(RegExp(r'\D'), '');
    // 09XXXXXXXX  أو  +2189XXXXXXXX
    final ok = RegExp(r'^(?:218)?0?9[1-6]\d{7}$').hasMatch(digits);
    return ok ? null : 'رقم الهاتف غير صحيح';
  }

  static Validator compose(List<Validator> list) =>
      (v) { for (final f in list) { final e = f(v); if (e != null) return e; } return null; };
}

typedef Validator = String? Function(String?);
```

Return `null` for valid, a **localized** message for invalid. Pull messages from `AppLocalizations` in a real app rather than hardcoding Arabic.

## Arabic-digit input

Users may type Arabic-Indic digits (٠١٢٣). Normalize before validating and before sending to a server:

```dart
String normalizeDigits(String s) {
  const ar = '٠١٢٣٤٥٦٧٨٩';
  const fa = '۰۱۲۳۴۵۶۷۸۹';
  var out = s;
  for (var i = 0; i < 10; i++) {
    out = out.replaceAll(ar[i], '$i').replaceAll(fa[i], '$i');
  }
  return out;
}
```

## Input formatters

```dart
inputFormatters: [
  FilteringTextInputFormatter.digitsOnly,
  LengthLimitingTextInputFormatter(10),
]
```

For currency/masks use the `mask_text_input_formatter` package. Do **not** format inside `onChanged` + `setState` — it fights the cursor position.

## Server-side errors on a field

`validator` only sees local state. For "email already registered", keep a nullable field error and feed it into the validator:

```dart
String? _emailServerError;
validator: (v) => Validators.email(v) ?? _emailServerError,
// after the failed request:
setState(() => _emailServerError = 'البريد مسجل مسبقاً');
_formKey.currentState!.validate();
// clear it in onChanged so the user can fix it
onChanged: (_) { if (_emailServerError != null) setState(() => _emailServerError = null); },
```

## Multi-step forms

Use one `GlobalKey<FormState>` **per step** and validate only the current step before advancing. Keep the collected data in a single immutable model held by the controller/provider, not spread across widget state, so back-navigation preserves it.

## Checklist

- [ ] Keyboard type + `textInputAction` set on every field
- [ ] Focus moves to the next field on submit
- [ ] `autofillHints` set (enables password managers)
- [ ] Form scrolls; button not hidden by the keyboard
- [ ] Button disabled + spinner while submitting
- [ ] Errors are localized and specific
- [ ] Controllers disposed
