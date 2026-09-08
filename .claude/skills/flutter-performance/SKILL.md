---
name: flutter-performance
description: Diagnose and fix Flutter performance problems — jank, excessive rebuilds, slow lists, large images, heavy computation, memory leaks, and app size. Use when the app feels slow or stutters, before release, or when the user says "بطء", "تهنيج", "الأداء", "performance", "jank", "lag", "حجم التطبيق".
---

# Flutter Performance

## Measure before changing anything

```bash
flutter run --profile           # never profile in debug — debug is 5-10x slower
flutter run --profile --trace-skia
```

In DevTools: **Performance** view for the frame timeline, **CPU profiler** for hot functions, **Memory** for leaks, **Widget rebuild stats** for rebuild counts.

Frame budget: **16 ms** at 60 Hz, **8 ms** at 120 Hz. A red bar in the timeline is a dropped frame — click it to see whether the cost is in **UI** (your Dart code / build) or **Raster** (painting: shaders, opacity, clips, shadows). The fix is different for each.

## Rebuilds (the most common cause)

```dart
// ❌ whole page rebuilds on every tick
Widget build(context) {
  final count = ref.watch(counterProvider);
  return ExpensiveTree(child: Text('$count'));
}

// ✅ only the Text rebuilds
Widget build(context) => ExpensiveTree(
  child: Consumer(builder: (c, ref, _) => Text('${ref.watch(counterProvider)}')),
);
```

Rules:
- `const` every widget that can be const. A `const` subtree is skipped entirely on rebuild. Turn on `prefer_const_constructors`.
- Extract stable subtrees into **separate widget classes** — not `Widget _build...()` helper methods, which always rebuild with the parent.
- Watch narrowly: `ref.watch(p.select((s) => s.name))`, `context.select<Model, String>((m) => m.name)`, `BlocSelector`.
- Pass the static part as `child:` to `AnimatedBuilder`, `ValueListenableBuilder`, `Consumer` — it is built once and reused.
- Move `setState` down to the smallest widget that owns the changing state.

## Lists

- Always `ListView.builder` / `.separated` / `GridView.builder` — never `Column` + `children: items.map(...)` for a list that can grow.
- Give items a stable `ValueKey(item.id)` so element reuse and animations work.
- Set `itemExtent` (or `prototypeItem`) when rows are a fixed height — it lets Flutter skip layout for off-screen items and makes scrollbar/jump-to-index instant.
- Do **not** set `shrinkWrap: true` on a long list; it lays out every child. Use slivers (`CustomScrollView` + `SliverList`) to combine scrolling sections.
- Paginate: load 20–50 at a time and fetch more near the end. A 5,000-row list built at once will jank no matter what.
- Keep `itemBuilder` cheap — no date parsing, no JSON decoding, no `MediaQuery` math per row. Precompute into the model.
- `addAutomaticKeepAlives: false` when items don't need to keep state.

## Images

The number one memory and raster cost.

```dart
Image.network(
  url,
  cacheWidth: 320,          // decode at display size, not source size
  cacheHeight: 320,
)

CachedNetworkImage(
  imageUrl: url,
  memCacheWidth: 320,
  fadeInDuration: const Duration(milliseconds: 120),
  placeholder: (c, _) => const ColoredBox(color: Colors.black12),
)
```

A 4000×3000 photo decodes to ~48 MB in memory regardless of the widget size. Always constrain `cacheWidth`/`cacheHeight`, or serve resized images from the server (Supabase image transforms, a CDN).

Also: use WebP over PNG/JPEG for assets, provide the right resolution buckets (`2.0x`, `3.0x`), and compress uploads client-side.

## Raster-side costs

- `Opacity` over a large subtree forces an offscreen layer — animate with `FadeTransition`, or change a color's alpha instead.
- `ClipRRect` on scrolling items is expensive; prefer `BoxDecoration(borderRadius:)` where possible.
- `BackdropFilter` (blur) is very expensive — never inside a scrolling list.
- Many `BoxShadow`s cost real time; one soft shadow is fine, a shadow per list row is not.
- `RepaintBoundary` around a small, frequently-repainting widget (an animation, a video) stops it repainting its neighbours. Overusing it costs memory — apply it where the timeline shows repaint churn.
- **Shader jank on first run** (iOS especially): Impeller is the default on iOS/Android in recent Flutter versions and removes most of this. If on the Skia backend, use SkSL warm-up.

## Heavy computation

Anything over ~8 ms belongs off the UI thread.

```dart
final parsed = await compute(parseReports, jsonString);

// long-lived worker
final results = await Isolate.run(() => heavyWork(input));
```

`compute` / `Isolate.run` arguments must be sendable (primitives, lists, maps, `TransferableTypedData`). Parsing a large JSON payload, image processing, and crypto all belong here.

Note: `await` alone does **not** move work off the UI thread — an `async` function still runs its body on the main isolate.

## Startup time

- Do not `await` non-essential work in `main()`. Initialize analytics, remote config, and prefetching after the first frame.
- Show a native splash (`flutter_native_splash`) so the first paint is instant.
- Defer heavy providers with `.autoDispose` + lazy reads.
- Measure: `flutter run --profile --trace-startup`.

## Memory leaks

Symptoms: memory grows on every navigation and never returns.

Always dispose: `AnimationController`, `TextEditingController`, `FocusNode`, `ScrollController`, `StreamSubscription`, `Timer`, `PageController`, realtime channels, `WebSocketChannel`.

```dart
@override
void dispose() {
  _sub?.cancel();
  _timer?.cancel();
  _controller.dispose();
  super.dispose();
}
```

A `StreamSubscription` that is never cancelled keeps the whole widget tree alive. Check the Memory view: navigate in and out of a screen ten times, force GC, and confirm instance counts return to baseline.

## App size

```bash
flutter build apk --release --analyze-size
flutter build appbundle --release      # Play Store splits per-ABI automatically
```

- Ship an **App Bundle**, not a universal APK — it can halve the download.
- Remove unused assets and unused font weights.
- `--split-per-abi` if you must distribute APKs directly.
- Audit dependencies: one package pulling in a large native SDK can add several MB.

## Web-specific

- Prefer the CanvasKit renderer for graphics-heavy apps, the HTML/skwasm path for content sites (smaller download).
- Enable deferred loading (`deferred as`) for big optional screens.
- Serve gzip/brotli, and set long cache headers on hashed assets.

## Quick triage

| Symptom | Look at |
|---|---|
| Jank while scrolling | itemBuilder cost, image decode size, shadows/clips |
| Jank on one interaction | UI thread spike → find it in the CPU profiler |
| Slow first launch | work in `main()`, synchronous I/O |
| Memory climbing | undisposed controllers/subscriptions, unbounded caches |
| Everything slow | you are in debug mode — rerun with `--profile` |
