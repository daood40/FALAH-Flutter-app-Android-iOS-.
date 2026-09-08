---
name: flutter-ui-design
description: Build Flutter screens and widgets — layout, Material 3 theming, responsive/adaptive design, dark mode, design tokens, and reusable component patterns. Use when creating or restyling any UI, or when the user says "صمم شاشة", "واجهة", "ثيم", "screen", "widget", "responsive", "dark mode".
---

# Flutter UI & Design

## Theme first, styles never inline

Define a single `ThemeData` and read from it. Never write raw `Color(0xFF...)` or `TextStyle(fontSize: 16)` inside a screen.

```dart
final seed = const Color(0xFF0B6E4F);

ThemeData buildTheme(Brightness b) {
  final scheme = ColorScheme.fromSeed(seedColor: seed, brightness: b);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: scheme.surface,
    textTheme: GoogleFonts.cairoTextTheme(ThemeData(brightness: b).textTheme),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerHighest,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide.none,
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
  );
}

MaterialApp(
  theme: buildTheme(Brightness.light),
  darkTheme: buildTheme(Brightness.dark),
  themeMode: ThemeMode.system,
)
```

In widgets: `Theme.of(context).colorScheme.primary`, `Theme.of(context).textTheme.titleMedium`.

Every screen must be checked in both light and dark. A hardcoded `Colors.white` background is the most common dark-mode bug.

## Spacing scale

Use a 4pt scale — `4, 8, 12, 16, 24, 32, 48`. Put it in one place:

```dart
abstract class Gap {
  static const xs = SizedBox(height: 4);
  static const sm = SizedBox(height: 8);
  static const md = SizedBox(height: 16);
  static const lg = SizedBox(height: 24);
}
```

## Layout rules that prevent the common errors

- **Unbounded height** (`ListView` inside `Column`): wrap in `Expanded`, or set `shrinkWrap: true` + `physics: NeverScrollableScrollPhysics()` for short lists only.
- **Row overflow**: wrap the flexible child in `Expanded` or `Flexible`. Text that may overflow gets `overflow: TextOverflow.ellipsis, maxLines: 2`.
- **Keyboard covering fields**: `resizeToAvoidBottomInset: true` (default) + put the form in a `SingleChildScrollView`. Add `padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom)` for a bottom-pinned button.
- **Notches and system bars**: `SafeArea` around body content, and `SliverPadding` for scroll views.
- Prefer `ListView.builder` / `ListView.separated` over `Column` + `map` for any list that can grow.

## Responsive & adaptive

```dart
class Breakpoints {
  static const compact = 600;   // phone
  static const medium = 840;    // tablet / foldable
  static const expanded = 1200; // desktop / web
}

LayoutBuilder(
  builder: (context, c) {
    if (c.maxWidth >= Breakpoints.expanded) return _ThreePane();
    if (c.maxWidth >= Breakpoints.compact) return _TwoPane();
    return _SinglePane();
  },
);
```

- Use `LayoutBuilder` (parent size), not `MediaQuery` size, when deciding a widget's own layout.
- On web/desktop, constrain content width: `Center(child: ConstrainedBox(constraints: BoxConstraints(maxWidth: 720), child: ...))`. Full-bleed text lines on a desktop browser look broken.
- Bottom `NavigationBar` on compact → `NavigationRail` on medium → permanent `NavigationDrawer` on expanded.

## Component pattern

Extract a widget when it is used twice, exceeds ~80 lines, or has its own state. Extract into a **class**, not a `Widget _buildX()` method — a method rebuilds with the parent and cannot be `const`.

```dart
class StatCard extends StatelessWidget {
  const StatCard({super.key, required this.label, required this.value, this.onTap});
  final String label;
  final String value;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: t.textTheme.labelMedium),
              const SizedBox(height: 4),
              Text(value, style: t.textTheme.headlineSmall),
            ],
          ),
        ),
      ),
    );
  }
}
```

## Every screen needs four states

Loading, empty, error, and content. A screen that only handles the happy path is not finished.

```dart
switch (state) {
  Loading() => const Center(child: CircularProgressIndicator()),
  Empty()   => EmptyView(message: 'لا توجد عناصر بعد', onAction: onCreate),
  Failure(:final message) => ErrorView(message: message, onRetry: onRetry),
  Data(:final items) => _List(items),
}
```

Use skeleton placeholders (`shimmer` package or a grey `Container`) instead of a bare spinner for list screens.

## Accessibility (non-negotiable)

- Minimum tap target 48×48.
- Icon-only buttons get `tooltip:` or a `Semantics(label: ...)`.
- Never convey meaning by color alone; add an icon or text.
- Respect text scale: test at `MediaQuery.withClampedTextScaling(minScaleFactor: 1.3)`. Fixed-height rows break here — use `IntrinsicHeight` or let them grow.
- Contrast ≥ 4.5:1 for body text.

## Images

`Image.asset` for bundled, `CachedNetworkImage` for remote (gives you placeholder + error widget + disk cache). Always set `width`/`height` or wrap in `AspectRatio` to avoid layout jump.
