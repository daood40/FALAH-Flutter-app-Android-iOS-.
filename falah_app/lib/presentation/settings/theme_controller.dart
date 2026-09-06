/// السمةُ المختارة — تُحفظ في التفضيلات لا في التخزين الآمن.
///
/// **التمييزُ مقصود**: `SharedPreferences` للراحةِ لا للأسرار. اختيارُ
/// السمةِ ليس سرًّا، والجلسةُ في كعكةٍ لا تمرّ بشيفرة Dart أصلًا.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _key = 'theme_mode';

class ThemeModeController extends Notifier<ThemeMode> {
  SharedPreferences? _prefs;

  @override
  ThemeMode build() {
    _load();
    return ThemeMode.system;
  }

  Future<void> _load() async {
    _prefs = await SharedPreferences.getInstance();
    final v = _prefs?.getString(_key);
    if (v != null) state = _parse(v);
  }

  Future<void> set(ThemeMode m) async {
    state = m;
    _prefs ??= await SharedPreferences.getInstance();
    await _prefs!.setString(_key, m.name);
  }

  static ThemeMode _parse(String s) => switch (s) {
    'light' => ThemeMode.light,
    'dark' => ThemeMode.dark,
    _ => ThemeMode.system,
  };
}

final themeModeProvider = NotifierProvider<ThemeModeController, ThemeMode>(
  ThemeModeController.new,
);
