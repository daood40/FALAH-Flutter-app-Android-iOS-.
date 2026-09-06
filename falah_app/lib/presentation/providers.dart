/// حقنُ الاعتماديات — مزوِّدٌ لكلِّ عقد، ويُستبدَل في الاختبار بلا تعديلِ شاشة.
///
/// `apiClientProvider` يُرمى عمدًا إن لم يُتجاوَز: بناؤه غيرُ متزامنٍ
/// (يحتاج مسارَ جرّة الكعك على القرص)، فيُهيَّأ في `main` ويُحقن في
/// `ProviderScope.overrides`. والرميُ هنا خيرٌ من قيمةٍ صامتةٍ خاطئة.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/network/api_client.dart';
import '../data/repositories/auth_repository_impl.dart';
import '../data/repositories/content_repository_impl.dart';
import '../data/repositories/project_repository_impl.dart';
import '../domain/repositories/auth_repository.dart';
import '../domain/repositories/content_repository.dart';
import '../domain/repositories/project_repository.dart';

final apiClientProvider = Provider<ApiClient>((ref) {
  throw UnimplementedError(
    'apiClientProvider يجب أن يُتجاوَز في ProviderScope — انظر main.dart',
  );
});

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepositoryImpl(ref.watch(apiClientProvider)),
);

final projectRepositoryProvider = Provider<ProjectRepository>(
  (ref) => ProjectRepositoryImpl(ref.watch(apiClientProvider)),
);

// ═══ التصفّح والوكيل والجدولة والنشر ═══

final contentRepositoryProvider = Provider<ContentRepository>(
  (ref) => ContentRepositoryImpl(ref.watch(apiClientProvider)),
);

final agentRepositoryProvider = Provider<AgentRepository>(
  (ref) => AgentRepositoryImpl(ref.watch(apiClientProvider)),
);

final scheduleRepositoryProvider = Provider<ScheduleRepository>(
  (ref) => ScheduleRepositoryImpl(ref.watch(apiClientProvider)),
);

final publishRepositoryProvider = Provider<PublishRepository>(
  (ref) => PublishRepositoryImpl(ref.watch(apiClientProvider)),
);
