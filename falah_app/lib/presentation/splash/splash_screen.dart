/// الإقلاع — يسأل الخادمَ عن الجلسة مرّةً، ثم يترك الموجّهَ يقرّر.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import '../auth/auth_controller.dart';

class SplashScreen extends ConsumerStatefulWidget {
  const SplashScreen({super.key});

  @override
  ConsumerState<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<SplashScreen> {
  @override
  void initState() {
    super.initState();
    // بعد أوّل إطار: `restore` يغيّر الحالة، وتغييرُها أثناء البناء ممنوع
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(authControllerProvider.notifier).restore();
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'فَلاح',
              style: t.textTheme.displaySmall?.copyWith(
                color: Palette.gold,
                fontSize: 40,
              ),
            ),
            const SizedBox(height: Space.xs),
            Text('نصٌّ موثَّقُ الإسناد', style: t.textTheme.bodySmall),
            const SizedBox(height: Space.xxl),
            const SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ],
        ),
      ),
    );
  }
}
