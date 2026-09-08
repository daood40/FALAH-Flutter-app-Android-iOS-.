---
name: flutter-navigation
description: Routing and navigation in Flutter with go_router — nested shell routes, bottom nav, auth redirect guards, path/query parameters, deep links and app links. Use when adding screens, tabs, or login gating, or when the user says "تنقل", "راوتر", "شاشات", "navigation", "routing", "deep link".
---

# Flutter Navigation (go_router)

Use `go_router` for anything beyond 3 screens. It gives you URL-based routing (needed for Flutter Web), typed parameters, redirect guards and deep links in one place.

## Router definition

```dart
final routerProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(authStateProvider);

  return GoRouter(
    initialLocation: '/',
    debugLogDiagnostics: true,
    refreshListenable: auth,          // re-evaluates redirect on auth change
    redirect: (context, state) {
      final loggedIn = auth.isLoggedIn;
      final goingToAuth = state.matchedLocation.startsWith('/auth');
      if (!loggedIn && !goingToAuth) return '/auth/login?from=${state.uri}';
      if (loggedIn && goingToAuth) return '/';
      return null;                     // null = no redirect
    },
    errorBuilder: (context, state) => NotFoundScreen(uri: state.uri),
    routes: [
      GoRoute(path: '/auth/login', builder: (c, s) => const LoginScreen()),

      StatefulShellRoute.indexedStack(
        builder: (c, s, shell) => ScaffoldWithNavBar(shell: shell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(
              path: '/',
              builder: (c, s) => const HomeScreen(),
              routes: [
                GoRoute(
                  path: 'report/:id',              // no leading slash = child
                  builder: (c, s) => ReportScreen(id: s.pathParameters['id']!),
                ),
              ],
            ),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/profile', builder: (c, s) => const ProfileScreen()),
          ]),
        ],
      ),
    ],
  );
});

MaterialApp.router(
  routerConfig: ref.watch(routerProvider),
)
```

`StatefulShellRoute.indexedStack` is what keeps each tab's own navigation stack and scroll position alive — plain `ShellRoute` does not.

## Navigating

| Intent | Call |
|---|---|
| Replace the current location (tab switch, after login) | `context.go('/profile')` |
| Push on top, keep back button | `context.push('/report/42')` |
| Return a value from a pushed screen | `final r = await context.push<bool>('/edit'); ` then `context.pop(true)` |
| Go back | `context.pop()` |
| Named route | `context.goNamed('report', pathParameters: {'id': '42'})` |

Name every route (`name: 'report'`) and navigate by name — a path string typo is a runtime crash, and paths change.

## Parameters

- Path params for identity: `/report/:id` → `state.pathParameters['id']`
- Query params for options: `/search?q=fire&page=2` → `state.uri.queryParameters['q']`
- `extra:` for a full object: `context.push('/detail', extra: report)`. **Never rely on `extra` alone** — it is lost on a web refresh or a cold deep link. Pass the id in the path and re-fetch, using `extra` only as an optimization.

## Guards beyond auth

Put every guard in the single top-level `redirect`; scattered `if (!allowed) Navigator.pop()` calls in `initState` cause flicker and race conditions.

```dart
redirect: (context, state) {
  if (!auth.isLoggedIn) return '/auth/login';
  if (!auth.emailVerified && !state.matchedLocation.startsWith('/verify')) return '/verify';
  if (state.matchedLocation.startsWith('/admin') && !auth.isAdmin) return '/';
  return null;
},
```

## Deep links

Android — `android/app/src/main/AndroidManifest.xml` inside `<activity>`:

```xml
<meta-data android:name="flutter_deeplinking_enabled" android:value="true" />
<intent-filter android:autoVerify="true">
  <action android:name="android.intent.action.VIEW" />
  <category android:name="android.intent.category.DEFAULT" />
  <category android:name="android.intent.category.BROWSABLE" />
  <data android:scheme="https" android:host="example.com" />
</intent-filter>
```

iOS — add Associated Domains (`applinks:example.com`) in Xcode and set `FlutterDeepLinkingEnabled` to `true` in `Info.plist`.

Host `/.well-known/assetlinks.json` (Android) and `/.well-known/apple-app-site-association` (iOS) on the domain. Test: `adb shell am start -a android.intent.action.VIEW -d "https://example.com/report/42"`.

## Back button and unsaved changes

```dart
PopScope(
  canPop: !hasUnsavedChanges,
  onPopInvokedWithResult: (didPop, _) async {
    if (didPop) return;
    final leave = await showDialog<bool>(...);
    if (leave == true && context.mounted) context.pop();
  },
  child: form,
)
```

## Common mistakes

- Using `Navigator.push(MaterialPageRoute(...))` alongside go_router — the pushed route is invisible to the router and breaks web URLs and deep links. Pick one.
- Calling `context.go` after an `await` without checking `if (!context.mounted) return;`.
- Rebuilding `GoRouter` on every widget rebuild — it must live in a provider / top-level final, or the whole stack resets.
