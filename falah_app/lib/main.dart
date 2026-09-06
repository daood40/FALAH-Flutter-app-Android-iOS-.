/// نقطةُ الدخول — تهيئةٌ غيرُ متزامنةٍ ثم حقنُ ما بُني في الشجرة.
library;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';

import 'core/config/env.dart';
import 'core/logging/logger.dart';
import 'core/network/api_client.dart';
import 'core/routing/app_router.dart';
import 'core/theme/app_theme.dart';
import 'presentation/providers.dart';
import 'presentation/settings/theme_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // حارسٌ عند الإقلاع: بناءٌ للإنتاج على عنوانٍ غيرِ مشفّرٍ يُرمى هنا، لا
  // يُشحن تطبيقٌ يرسل الجلسةَ في العراء.
  Env.assertValid();
  if (Env.isProd) Log.minLevel = LogLevel.info;

  // جرّةُ الكعك على القرص: الجلسةُ تنجو من إغلاق التطبيق
  final dir = await getApplicationSupportDirectory();
  final api = await ApiClient.create(cookieDir: '${dir.path}/cookies/');

  runApp(
    ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(api)],
      child: const FalahApp(),
    ),
  );
}

class FalahApp extends ConsumerWidget {
  const FalahApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final mode = ref.watch(themeModeProvider);

    return MaterialApp.router(
      title: 'فَلاح',
      debugShowCheckedModeBanner: false,
      routerConfig: router,
      themeMode: mode,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      // العربيةُ أوّلًا واتّجاهُ الواجهة من اليمين — ولا يُترك لِلغة الجهاز
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar'), Locale('en')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      builder: (context, child) {
        // حدُّ تكبير النصّ: المستخدمُ يكبّره لحاجة، لكن ما فوق ١٫٦ يكسر
        // البطاقةَ والشريطَ العلويّ. حدٌّ لا منعٌ.
        final scale = MediaQuery.textScalerOf(
          context,
        ).clamp(maxScaleFactor: 1.6);
        return Directionality(
          textDirection: TextDirection.rtl,
          child: MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: scale),
            child: child ?? const SizedBox.shrink(),
          ),
        );
      },
    );
  }
}
