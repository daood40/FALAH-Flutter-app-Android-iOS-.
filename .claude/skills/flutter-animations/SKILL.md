---
name: flutter-animations
description: Flutter animations and motion — implicit animations, AnimationController, Hero transitions, page transitions, staggered lists, CustomPainter, Lottie/Rive. Use when adding motion, transitions, loading effects, or when the user says "حركة", "أنيميشن", "انتقال", "animation", "transition", "shimmer".
---

# Flutter Animations

## Choose the cheapest tool that works

1. **Implicit** (`AnimatedContainer`, `AnimatedOpacity`, `AnimatedAlign`, `AnimatedSwitcher`, `AnimatedPadding`, `TweenAnimationBuilder`) — one value changing from A to B. Use this ~80% of the time.
2. **Explicit** (`AnimationController` + `AnimatedBuilder`) — you need to pause, reverse, repeat, chain, or drive several things from one timeline.
3. **Hero / PageRouteBuilder** — element or screen transitions.
4. **CustomPainter** — shapes and graphs that no widget gives you.
5. **Lottie / Rive** — designer-authored illustrations.

## Implicit

```dart
AnimatedContainer(
  duration: const Duration(milliseconds: 250),
  curve: Curves.easeOutCubic,
  height: expanded ? 220 : 96,
  decoration: BoxDecoration(
    color: expanded ? scheme.primaryContainer : scheme.surfaceContainer,
    borderRadius: BorderRadius.circular(expanded ? 24 : 12),
  ),
  child: content,
)
```

`AnimatedSwitcher` needs a **different `key`** on each child or it will not animate:

```dart
AnimatedSwitcher(
  duration: const Duration(milliseconds: 200),
  child: loading
      ? const CircularProgressIndicator(key: ValueKey('load'))
      : Text(value, key: ValueKey(value)),
)
```

## Explicit

```dart
class Pulse extends StatefulWidget {
  const Pulse({super.key, required this.child});
  final Widget child;
  @override
  State<Pulse> createState() => _PulseState();
}

class _PulseState extends State<Pulse> with SingleTickerProviderStateMixin {
  late final _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  late final _scale = Tween(begin: 1.0, end: 1.06)
      .chain(CurveTween(curve: Curves.easeInOut))
      .animate(_c);

  @override
  void dispose() { _c.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) => ScaleTransition(
        scale: _scale,
        child: widget.child,   // passed as child → not rebuilt each frame
      );
}
```

Two rules: always `dispose()` the controller, and pass the static subtree as `child:` to `AnimatedBuilder`/`*Transition` so it is built once instead of 60 times a second.

Use `SingleTickerProviderStateMixin` for one controller, `TickerProviderStateMixin` for several.

## Staggered list entrance

```dart
ListView.builder(
  itemCount: items.length,
  itemBuilder: (c, i) => TweenAnimationBuilder<double>(
    tween: Tween(begin: 0, end: 1),
    duration: Duration(milliseconds: 300 + (i.clamp(0, 8) * 60)),
    curve: Curves.easeOut,
    builder: (c, t, child) => Opacity(
      opacity: t,
      child: Transform.translate(offset: Offset(0, 16 * (1 - t)), child: child),
    ),
    child: ItemTile(items[i]),
  ),
)
```

Clamp the index — otherwise item 200 waits 12 seconds to appear.

## Hero

```dart
// list
Hero(tag: 'report-${r.id}', child: Image.network(r.image))
// detail
Hero(tag: 'report-${r.id}', child: Image.network(r.image))
```

Tags must be unique per screen and identical across the two screens. For text, wrap the `Hero` child in `Material(type: MaterialType.transparency)` to avoid the yellow-underline flash.

## Custom page transition

```dart
GoRoute(
  path: '/detail',
  pageBuilder: (c, s) => CustomTransitionPage(
    key: s.pageKey,
    child: const DetailScreen(),
    transitionDuration: const Duration(milliseconds: 250),
    transitionsBuilder: (c, anim, sec, child) => FadeTransition(
      opacity: anim,
      child: SlideTransition(
        position: Tween(begin: const Offset(0, .04), end: Offset.zero).animate(anim),
        child: child,
      ),
    ),
  ),
)
```

In RTL, a horizontal slide must flip direction — use `Offset(Directionality.of(context) == TextDirection.rtl ? -0.1 : 0.1, 0)`.

## Animated list mutations

```dart
final _key = GlobalKey<AnimatedListState>();
_key.currentState!.insertItem(0);
_key.currentState!.removeItem(i, (c, anim) => SizeTransition(sizeFactor: anim, child: removedTile));
```

## CustomPainter

```dart
class RingPainter extends CustomPainter {
  RingPainter(this.progress, this.color);
  final double progress;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round
      ..color = color;
    canvas.drawArc(rect.deflate(5), -1.5708, 6.2832 * progress, false, paint);
  }

  @override
  bool shouldRepaint(RingPainter old) =>
      old.progress != progress || old.color != color;
}
```

`shouldRepaint` returning `true` unconditionally repaints every frame — always compare the real inputs.

## Timing that feels right

| Motion | Duration | Curve |
|---|---|---|
| Micro (ripple, checkbox, color) | 100–150 ms | `easeOut` |
| Standard (expand, sheet, fade) | 200–300 ms | `easeOutCubic` |
| Page transition | 250–350 ms | `easeInOutCubicEmphasized` |
| Enter (appear) | slower | `easeOut` / `easeOutBack` |
| Exit (disappear) | faster | `easeIn` |

Anything above ~400 ms on a repeated interaction feels sluggish.

## Accessibility

Respect reduced motion:

```dart
final reduce = MediaQuery.disableAnimationsOf(context);
final duration = reduce ? Duration.zero : const Duration(milliseconds: 300);
```

## Performance

- Never animate inside `build()` by calling `setState` in a loop — use a controller.
- `RepaintBoundary` around an animating widget stops it repainting its siblings.
- Avoid animating `Opacity` over a large subtree; prefer `FadeTransition` (it uses the same layer) or animate color alpha.
- Profile with `flutter run --profile` + the "Track widget rebuilds" / raster timeline in DevTools.
