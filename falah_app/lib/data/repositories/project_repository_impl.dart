/// تنفيذُ عقد المشاريع على المسارات القائمة — بلا تعديلِ سطرٍ في الخادم.
library;

import '../../core/errors/failure.dart';
import '../../core/network/api_client.dart';
import '../../domain/entities/entitlements.dart';
import '../../domain/entities/project.dart';
import '../../domain/repositories/project_repository.dart';
import '../dto/mappers.dart';

class ProjectRepositoryImpl implements ProjectRepository {
  ProjectRepositoryImpl(this._api);

  final ApiClient _api;

  @override
  Future<Result<List<Project>>> list() async =>
      (await _api.get('/app/projects')).fold((f) => Err(f), (j) {
        final raw = j['projects'];
        if (raw is! List) return const Ok(<Project>[]);
        return Ok(
          raw
              .whereType<Map>()
              .map((e) => Mappers.project(Map<String, dynamic>.from(e)))
              .toList(),
        );
      });

  @override
  Future<Result<Project>> open(int id) async => (await _api.get(
    '/app/projects/$id',
  )).fold((f) => Err(f), (j) => Ok(Mappers.projectDetail(j)));

  @override
  Future<Result<Project>> create(String title) async => (await _api.post(
    '/app/projects/create',
    body: {'title': title},
  )).fold((f) => Err(f), (j) => Ok(Mappers.projectDetail(j)));

  @override
  Future<Result<void>> update(int id, {String? skin, String? ratio}) async {
    final body = <String, dynamic>{'id': id};
    if (skin != null) body['skin'] = skin;
    if (ratio != null) body['ratio'] = ratio;
    return (await _api.post(
      '/app/projects/update',
      body: body,
    )).fold((f) => Err(f), (_) => const Ok(null));
  }

  @override
  Future<Result<void>> delete(int id) async => (await _api.post(
    '/app/projects/delete',
    body: {'id': id},
  )).fold((f) => Err(f), (_) => const Ok(null));

  @override
  Future<Result<void>> addItem({
    required int projectId,
    required String kind,
    required Map<String, dynamic> ref,
  }) async => (await _api.post(
    '/app/items/add',
    body: {'project': projectId, 'kind': kind, 'ref': ref},
  )).fold((f) => Err(f), (_) => const Ok(null));

  @override
  Future<Result<void>> removeItem({
    required int projectId,
    required int itemId,
  }) async => (await _api.post(
    '/app/items/remove',
    body: {'project': projectId, 'id': itemId},
  )).fold((f) => Err(f), (_) => const Ok(null));

  @override
  Future<Result<void>> acceptDrift({
    required int projectId,
    required int itemId,
  }) async => (await _api.post(
    '/app/items/accept-drift',
    body: {'project': projectId, 'id': itemId},
  )).fold((f) => Err(f), (_) => const Ok(null));

  @override
  Future<Result<int>> startExport(int projectId) =>
      _job('/app/export', {'project': projectId});

  @override
  Future<Result<int>> startVideo({
    required int projectId,
    required int itemId,
  }) => _job('/app/video', {'project': projectId, 'item': itemId});

  Future<Result<int>> _job(String path, Map<String, dynamic> body) async =>
      (await _api.post(path, body: body)).fold((f) => Err(f), (j) {
        final id = j['job'] is Map
            ? (j['job'] as Map)['id']
            : (j['job_id'] ?? j['id']);
        final n = id is int ? id : int.tryParse('$id');
        return n == null
            ? const Err(UnknownFailure('لم يُعد رقمُ المهمّة'))
            : Ok(n);
      });

  @override
  Future<Result<Job>> job(int id) async => (await _api.get(
    '/app/jobs/$id',
  )).fold((f) => Err(f), (j) => Ok(Mappers.job(j)));

  @override
  Future<Result<void>> cancelJob(int id) async => (await _api.post(
    '/app/jobs/cancel',
    body: {'id': id},
  )).fold((f) => Err(f), (_) => const Ok(null));

  @override
  Future<Result<Entitlements>> entitlements() async => (await _api.get(
    '/app/entitlements',
  )).fold((f) => Err(f), (j) => Ok(Mappers.entitlements(j)));
}
