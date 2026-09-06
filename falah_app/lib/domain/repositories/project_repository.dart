/// عقدُ المشاريع والطابور — كلُّ ما يخصّ إنشاءَ المحتوى وتصديرَه.
library;

import '../../core/network/api_client.dart' show Result;
import '../entities/entitlements.dart';
import '../entities/project.dart';

abstract interface class ProjectRepository {
  Future<Result<List<Project>>> list();

  Future<Result<Project>> open(int id);

  Future<Result<Project>> create(String title);

  Future<Result<void>> update(int id, {String? skin, String? ratio});

  Future<Result<void>> delete(int id);

  /// يُضاف نصٌّ **بمرجعه لا بمتنه**: العميلُ يرسل `{surah, ayah}` والخادمُ
  /// يجلب النصَّ من قاعدة المحتوى المفحوصة. وهذا شرطُ `SOURCE_LOCK`:
  /// لا يصل متنٌ من العميل إلى بطاقةٍ بحال.
  Future<Result<void>> addItem({
    required int projectId,
    required String kind,
    required Map<String, dynamic> ref,
  });

  Future<Result<void>> removeItem({
    required int projectId,
    required int itemId,
  });

  Future<Result<void>> acceptDrift({
    required int projectId,
    required int itemId,
  });

  /// يُضيف مهمّةَ تصديرٍ إلى الطابور ويردّ رقمَها فورًا (٢٠٢).
  /// التصييرُ لا يجري في الطلب — بطاقةٌ ≈ ٣ث.
  Future<Result<int>> startExport(int projectId);

  Future<Result<int>> startVideo({required int projectId, required int itemId});

  Future<Result<Job>> job(int id);

  /// إلغاءُ مهمّةٍ جارية. المسارُ موجودٌ في الخادم منذ P0 **ولم تكن له
  /// واجهةٌ في العميل القديم** — وهي فجوةٌ رصدها التدقيق وتُغلَق هنا.
  Future<Result<void>> cancelJob(int id);

  Future<Result<Entitlements>> entitlements();
}
