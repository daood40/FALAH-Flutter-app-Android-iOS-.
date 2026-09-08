/// حالةُ الرئيسية — المشاريعُ والحقوق، وكلاهما من الخادم.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/failure.dart';
import '../../domain/entities/entitlements.dart';
import '../../domain/entities/project.dart';
import '../auth/auth_controller.dart';
import '../providers.dart';

/// يترجم فشلَ التفويض إلى انتهاءِ جلسةٍ في حالةِ المصادقة، فيتولّى
/// الموجّهُ الخروجَ. بهذا لا تُكرَّر معالجةُ ٤٠١ في كلِّ شاشة.
void _handleAuth(Ref ref, Failure f) {
  if (f is UnauthorizedFailure) {
    ref.read(authControllerProvider.notifier).expire(f.message);
  }
}

final projectsProvider = FutureProvider.autoDispose<List<Project>>((ref) async {
  final r = await ref.watch(projectRepositoryProvider).list();
  return r.fold((f) {
    _handleAuth(ref, f);
    throw f;
  }, (v) => v);
});

final entitlementsProvider = FutureProvider.autoDispose<Entitlements>((
  ref,
) async {
  final r = await ref.watch(projectRepositoryProvider).entitlements();
  return r.fold((f) {
    _handleAuth(ref, f);
    throw f;
  }, (v) => v);
});

final projectDetailProvider = FutureProvider.autoDispose.family<Project, int>((
  ref,
  id,
) async {
  final r = await ref.watch(projectRepositoryProvider).open(id);
  return r.fold((f) {
    _handleAuth(ref, f);
    throw f;
  }, (v) => v);
});
