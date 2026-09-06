/// الإعدادات — السمةُ وحجمُ النصّ ومعلوماتُ النسخة.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config/env.dart';
import '../../core/theme/tokens.dart';
import 'theme_controller.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mode = ref.watch(themeModeProvider);
    final t = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('الإعدادات')),
      body: ListView(
        padding: const EdgeInsets.all(Space.lg),
        children: [
          Text('المظهر', style: t.textTheme.titleMedium),
          const SizedBox(height: Space.sm),
          SegmentedButton<ThemeMode>(
            segments: const [
              ButtonSegment(
                value: ThemeMode.system,
                label: Text('النظام'),
                icon: Icon(Icons.brightness_auto_outlined),
              ),
              ButtonSegment(
                value: ThemeMode.light,
                label: Text('فاتح'),
                icon: Icon(Icons.light_mode_outlined),
              ),
              ButtonSegment(
                value: ThemeMode.dark,
                label: Text('داكن'),
                icon: Icon(Icons.dark_mode_outlined),
              ),
            ],
            selected: {mode},
            onSelectionChanged: (s) =>
                ref.read(themeModeProvider.notifier).set(s.first),
          ),
          const SizedBox(height: Space.xl),
          const Divider(),
          const SizedBox(height: Space.md),
          Text('عن التطبيق', style: t.textTheme.titleMedium),
          const SizedBox(height: Space.sm),
          Text('فَلاح — نصٌّ موثَّقُ الإسناد', style: t.textTheme.bodyMedium),
          const SizedBox(height: Space.xs),
          Text(
            'لا يُولَّد نصٌّ شرعيٌّ بالذكاء الاصطناعيّ. '
            'كلُّ آيةٍ وحديثٍ يُقرأ من مصدرٍ موثَّقٍ ويمرّ بخمسةٍ وعشرين فحصًا '
            'قبل أن يظهر في بطاقة.',
            style: t.textTheme.bodySmall,
          ),
          if (!Env.isProd) ...[
            const SizedBox(height: Space.lg),
            Text(
              'الخادم: ${Env.apiBaseUrl}',
              style: t.textTheme.bodySmall,
              textDirection: TextDirection.ltr,
            ),
          ],
        ],
      ),
    );
  }
}
