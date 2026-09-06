/// الموجّه — ومعه حرّاسٌ حقيقيّون لا شرطٌ داخل ودجة.
///
/// `redirect` يعمل **قبل** بناء الشاشة، فلا تُبنى شاشةٌ محميّةٌ لحظةً ثم
/// تُطرد — ولا يُرى وميضُ محتوًى لا يخصّ الزائر. وهذا هو الفرقُ بين حارسٍ
/// وشرطٍ في `build`.
///
/// ويعيد `refreshListenable` تقييمَ الوجهة كلّما تغيّرت حالةُ المصادقة:
/// فانتهاءُ الجلسة في أثناء الاستعمال يُخرج المستخدمَ من حيث هو.
///
/// **ولا يُعتمد على هذا في الأمان.** الحارسُ راحةُ استعمال؛ ومن بلغ شاشةً
/// بحيلةٍ لا يجد فيها شيئًا لأن كلَّ نداءٍ يُفحص في الخادم.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../presentation/auth/auth_controller.dart';
import '../../presentation/auth/login_screen.dart';
import '../../presentation/auth/register_screen.dart';
import '../../presentation/home/home_screen.dart';
import '../../presentation/profile/profile_screen.dart';
import '../../presentation/project/project_screen.dart';
import '../../presentation/settings/settings_screen.dart';
import '../../presentation/splash/splash_screen.dart';
import '../../presentation/subscription/plans_screen.dart';

final class Routes {
  const Routes._();
  static const splash = '/';
  static const login = '/login';
  static const register = '/register';
  static const home = '/home';
  static const project = '/project/:id';
  static const profile = '/profile';
  static const plans = '/plans';
  static const settings = '/settings';

  static String projectOf(int id) => '/project/$id';
}

/// المساراتُ التي لا تحتاج جلسة. ما عداها محميّ — **والمنعُ أصلٌ**:
/// مسارٌ جديدٌ يُضاف يصير محميًّا تلقائيًّا حتى يُعلَن هنا.
const _public = {Routes.splash, Routes.login, Routes.register};

/// جسرٌ بين Riverpod و GoRouter: يُخطر الموجّهَ عند تغيّر حالة المصادقة.
class _AuthListenable extends ChangeNotifier {
  _AuthListenable(this._ref) {
    _ref.listen<AuthState>(
      authControllerProvider,
      (_, next) => notifyListeners(),
    );
  }
  final Ref _ref;
}

final routerProvider = Provider<GoRouter>((ref) {
  final listenable = _AuthListenable(ref);
  ref.onDispose(listenable.dispose);

  return GoRouter(
    initialLocation: Routes.splash,
    refreshListenable: listenable,
    redirect: (context, state) {
      final auth = ref.read(authControllerProvider);
      final path = state.matchedLocation;
      final isPublic = _public.contains(path);

      return switch (auth) {
        // ما زال يُسأل الخادم: يبقى على الإقلاع ولا يُقرَّر شيء
        AuthUnknown() => path == Routes.splash ? null : Routes.splash,
        // انتهت جلسةٌ كانت: إلى الدخول، وشاشتُه تعرض السبب
        AuthExpired() => path == Routes.login ? null : Routes.login,
        AuthAnonymous() =>
          isPublic
              ? (path == Routes.splash ? Routes.login : null)
              : Routes.login,
        // داخلٌ: لا يبقى على شاشات الدخول
        AuthSignedIn() => isPublic ? Routes.home : null,
      };
    },
    routes: [
      GoRoute(
        path: Routes.splash,
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: Routes.login,
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: Routes.register,
        builder: (context, state) => const RegisterScreen(),
      ),
      GoRoute(
        path: Routes.home,
        builder: (context, state) => const HomeScreen(),
      ),
      GoRoute(
        path: Routes.project,
        builder: (_, s) {
          final id = int.tryParse(s.pathParameters['id'] ?? '');
          // معرّفٌ غيرُ صالحٍ لا يُمرَّر إلى الشبكة: يُردّ هنا برسالةٍ
          // مفهومة بدل نداءٍ يعود ٤٠٤
          if (id == null) return const _BadRoute('رقمُ مشروعٍ غيرُ صالح');
          return ProjectScreen(projectId: id);
        },
      ),
      GoRoute(
        path: Routes.profile,
        builder: (context, state) => const ProfileScreen(),
      ),
      GoRoute(
        path: Routes.plans,
        builder: (context, state) => const PlansScreen(),
      ),
      GoRoute(
        path: Routes.settings,
        builder: (context, state) => const SettingsScreen(),
      ),
    ],
    errorBuilder: (_, s) => _BadRoute('مسارٌ غيرُ معروف: ${s.uri.path}'),
  );
});

class _BadRoute extends StatelessWidget {
  const _BadRoute(this.message);
  final String message;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('خطأ')),
    body: Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () => context.go(Routes.home),
              child: const Text('إلى الرئيسية'),
            ),
          ],
        ),
      ),
    ),
  );
}
