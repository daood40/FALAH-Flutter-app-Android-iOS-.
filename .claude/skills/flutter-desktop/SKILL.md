---
name: flutter-desktop
description: Shipping a Flutter app on Windows, macOS and Linux — window management, mouse and keyboard UI, menus and shortcuts, system tray, real file access and drag-and-drop, then packaging with MSIX, a notarised .dmg or AppImage/Flatpak/Snap. Use for any desktop target question, or when the user says "ديسكتوب", "سطح المكتب", "ويندوز", "ماك", "لينكس", "desktop", "windows app", "macos", "msix", "notarize".
---

# Flutter Desktop (Windows / macOS / Linux)

## Enabling the platforms

```bash
flutter config --enable-windows-desktop --enable-macos-desktop --enable-linux-desktop
flutter create --platforms=windows,macos,linux .   # adds runners to an existing project
```

Run with `flutter run -d windows` (or `macos` / `linux`). You can only build for the OS you are on — use three CI runners (`windows-latest`, `macos-latest`, `ubuntu-latest`), not one. A Linux build host also needs `clang cmake ninja-build pkg-config libgtk-3-dev liblzma-dev`.

| Mobile assumption | Desktop reality |
|---|---|
| One window, fixed size | Resizable to 320 px or 4000 px by the user |
| Touch only | Hover, right-click, scroll wheel, precise cursors |
| Keyboard only in text fields | Tab traversal, Esc, Enter, Cmd/Ctrl shortcuts |
| Sandboxed storage | Real file system, user-chosen paths, drag-and-drop |
| Every plugin works | Many plugins have no desktop implementation |

## Window management (`window_manager`)

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();
  const options = WindowOptions(
    size: Size(1180, 760), minimumSize: Size(820, 560),
    center: true, title: 'لوحة التحكم',
  );
  await windowManager.waitUntilReadyToShow(options, () async {
    await windowManager.show();
  });
  runApp(const MyApp());
}
```

Showing the window before `waitUntilReadyToShow` completes makes it flash at the default size first. Persist size and position yourself (`getBounds()` / `setBounds()` into `shared_preferences`) — the OS will not restore them. Close-to-tray: call `windowManager.setPreventClose(true)`, mix `WindowListener` into your state class, register it in `initState`, and in `onWindowClose()` check `await windowManager.isPreventClose()` then `await windowManager.hide()` instead of quitting. Remove the listener in `dispose`.

## System tray (`tray_manager`)

```dart
await trayManager.setIcon(Platform.isWindows ? 'assets/tray.ico' : 'assets/tray.png');
await trayManager.setContextMenu(Menu(items: [
  MenuItem(key: 'show', label: 'إظهار النافذة'),
  MenuItem.separator(),
  MenuItem(key: 'quit', label: 'خروج'),
]));
```

Implement `TrayListener` (`onTrayIconMouseDown`, `onTrayMenuItemClick`) on the same state class. Windows needs a `.ico`; macOS wants a small monochrome template image. On Linux the tray needs the desktop environment to provide an AppIndicator and silently does nothing on some setups — never make it the only way to restore or quit.

## Menu bar and keyboard shortcuts

macOS gets a real native menu bar from `PlatformMenuBar`; on other platforms it renders only its `child`, so use the Material `MenuBar` + `SubmenuButton` + `MenuItemButton` there.

```dart
PlatformMenuBar(
  menus: [
    PlatformMenu(label: 'ملف', menus: [
      PlatformMenuItem(
        label: 'حفظ',
        shortcut: const SingleActivator(LogicalKeyboardKey.keyS, meta: true),
        onSelected: _save,
      ),
    ]),
  ],
  child: const HomeScreen(),
)
```

Add OS-provided items (Quit, Services) with `PlatformProvidedMenuItem`, guarded by `PlatformProvidedMenuItem.hasMenu(...)`. `meta` is Cmd on macOS and the Windows key elsewhere, so bind per platform or Ctrl+S does nothing on a Mac:

```dart
final isMac = defaultTargetPlatform == TargetPlatform.macOS;

CallbackShortcuts(
  bindings: {
    SingleActivator(LogicalKeyboardKey.keyS, meta: isMac, control: !isMac): _save,
    const SingleActivator(LogicalKeyboardKey.escape): _closePanel,
  },
  child: Focus(autofocus: true, child: body),
)
```

Use `Shortcuts` + `Actions` + a custom `Intent` instead when the same command also appears in a menu item or a button, so one `Action` serves all three. Shortcuts fire only when something in the subtree has focus — without `Focus(autofocus: true)` the bindings look dead.

## Mouse and large-screen UI

- Hover feedback everywhere: `MouseRegion(cursor: SystemMouseCursors.click, onEnter:, onExit:)`; `InkWell` and `ListTile` already carry hover colors. A desktop UI without it feels broken.
- Right-click: `GestureDetector(onSecondaryTapDown: (d) => showMenu(context: context, position: RelativeRect.fromLTRB(d.globalPosition.dx, d.globalPosition.dy, 0, 0), items: [PopupMenuItem(child: Text('نسخ'))]))`, or a `MenuAnchor` opened from the same callback. `Tooltip` on every icon-only button; `SelectionArea` around long text so it can be copied. Resizable panes: a `Row` of fixed and `Expanded` children with a draggable divider (`GestureDetector.onHorizontalDragUpdate` adjusting a stored width), or a `NavigationRail` beside the content.
- Branch on width with `LayoutBuilder`: rail plus master/detail above ~900 px, single column below; never lock the window to a phone shape.

## Files, dialogs and drag-and-drop

Desktop file access is genuinely open — no scoped storage, no photo-picker permission. `path_provider` gives `getApplicationSupportDirectory()` for app data and `getDownloadsDirectory()` (desktop only, nullable).

```dart
// file_selector — native dialogs on all three platforms
final file = await openFile(acceptedTypeGroups: [
  const XTypeGroup(label: 'صور', extensions: ['jpg', 'png']),
]);
final location = await getSaveLocation(suggestedName: 'تقرير.pdf');
if (location != null) await File(location.path).writeAsBytes(bytes);

// desktop_drop
DropTarget(
  onDragDone: (detail) => _import(detail.files.map((f) => f.path).toList()),
  onDragEntered: (_) => setState(() => _hovering = true),
  child: dropZone,
)
```

`detail.files` items expose `.path`; the element type name changed between `desktop_drop` versions, so read the version you pinned. On macOS the app is sandboxed — writing outside its container needs `com.apple.security.files.user-selected.read-write` in **both** `macos/Runner/DebugProfile.entitlements` and `Release.entitlements`.

## Plugins that do not work on desktop

| Package | Desktop status |
|---|---|
| `firebase_messaging`, `google_mobile_ads`, `in_app_purchase` | None |
| `webview_flutter` | Android/iOS/macOS — use `webview_windows` or `flutter_inappwebview` |
| `camera`, `geolocator`, `permission_handler`, `local_auth` | Partial or missing per OS |
| `path_provider`, `shared_preferences`, `url_launcher`, `file_selector` | Full |

Check pub.dev platform badges, then verify on the real OS — a package can declare support and still throw `MissingPluginException`. Guard with `!kIsWeb && (Platform.isWindows || Platform.isMacOS || Platform.isLinux)`. Prefer `defaultTargetPlatform` in widget code (it compiles on web and respects test overrides) and use `dart:io`'s `Platform` only where the code never runs on web.

## Local database

`sqflite` is Android/iOS only; on desktop call `sqfliteFfiInit(); databaseFactory = databaseFactoryFfi;` from `sqflite_common_ffi`. The native SQLite library must ship with the app — add `sqlite3_flutter_libs`, which bundles it into the Windows/Linux build. Without it the app runs on your machine (system sqlite present) and fails on a clean user machine. `drift` + `sqlite3_flutter_libs` is the safest default; see `flutter-local-database`.

## Packaging

```bash
flutter build windows --release   # build/windows/x64/runner/Release/
flutter build macos   --release   # build/macos/Build/Products/Release/App.app
flutter build linux   --release   # build/linux/x64/release/bundle/
```

**Windows — MSIX.** Add the `msix` dev dependency, put an `msix_config:` block in `pubspec.yaml` (display name, publisher, identity name, logo, capabilities), then `dart run msix:create`. Store submissions must use the identity assigned by Partner Center; for sideloading, sign with a code-signing certificate or SmartScreen warns every user. Zipping the whole `Release` folder (exe plus all DLLs) also works.

**macOS — signing and notarisation are mandatory.** Without them the app shows "cannot be opened because the developer cannot be verified" and most users never get past it.

```bash
codesign --deep --force --options runtime --timestamp \
  --sign "Developer ID Application: NAME (TEAMID)" MyApp.app
xcrun notarytool submit MyApp.dmg --keychain-profile "notary" --wait && \
xcrun stapler staple MyApp.dmg
```

This needs a paid Apple Developer account, the hardened runtime, and every entitlement you actually use. Classic failure: network calls work in debug and fail in release because `com.apple.security.network.client` is only in `DebugProfile.entitlements` — add it to `Release.entitlements` too.

**Linux.** Ship `bundle/` as an AppImage (`appimagetool`), a Flatpak, or a Snap. `flutter_distributor` with a `distribute_options.yaml` drives MSIX, DMG, AppImage and Deb from one command.

## Auto-update and maturity

MSIX from the Microsoft Store updates itself; sideloaded builds need your own updater. Cross-platform, `auto_updater` wraps Sparkle (macOS) and WinSparkle (Windows) around an appcast XML you host. Linux updates come from whichever store you shipped through. Code-push tools such as Shorebird target mobile — do not plan a desktop release around them. At minimum, compare the build number against a hosted `version.json` and show a download link. Desktop is supported but far less exercised than mobile: expect plugin gaps, third-party widgets with no keyboard handling, and platform-specific rendering bugs. Budget real time on each target OS — a Windows-only crash will not appear on your Mac.

## Common mistakes

- Designing at phone width and letting the window resize into a broken layout.
- Hard-coding `control: true`, so every shortcut is dead on macOS.
- Omitting `Focus(autofocus: true)` so `Shortcuts` never receives keys.
- Shipping macOS un-notarised, or missing `network.client` in `Release.entitlements`.
- Relying on system SQLite instead of bundling `sqlite3_flutter_libs`.
- Trusting a pub.dev platform badge without running on that OS, or making the system tray the only path to restore or quit on Linux.

## Checklist

- [ ] Minimum window size set; layout verified at that size
- [ ] Window bounds persisted and restored
- [ ] Hover states, tooltips, right-click menus; Cmd vs Ctrl correct; Tab traversal works
- [ ] Native file dialogs and drag-and-drop tested with real files
- [ ] Every plugin verified on each target OS; SQLite native library bundled
- [ ] macOS Release entitlements complete; signed, notarised, stapled
- [ ] Windows MSIX or signed installer; Linux bundle tested on a clean machine
- [ ] Update path decided and wired; Arabic/RTL verified on each platform
