---
name: flutter-charts
description: Data visualization in Flutter — choosing a chart library, line/bar/pie/donut charts with fl_chart, dark mode and RTL axes, Arabic number and date labels, empty and loading states, performance with large series, accessibility, and exporting a chart as an image. Use when visualizing data, or when the user says "رسم بياني", "إحصائيات", "مخطط", "chart", "graph", "dashboard", "KPI".
---

# Charts in Flutter

## Choosing a library

| Option | Use when | Cost |
|---|---|---|
| `fl_chart` | Default. Line, bar, pie, radar, scatter. Small, full control, no licence friction. | Free (MIT) |
| `syncfusion_flutter_charts` | Candlestick, waterfall, box-and-whisker, zoom/pan, trackball, date-time axes out of the box. | Community licence free only under $1M USD annual gross revenue and ≤ 5 developers; else paid. Needs `SyncfusionLicense.registerLicense(key)` in `main()`. |
| `CustomPainter` | One bespoke shape — a gauge, a ring, a sparkline. Anything reusable is faster in fl_chart. | Free |

Do not pull in two chart libraries. Style whichever you pick from `ColorScheme`, never from hardcoded hex:

```dart
final cs = Theme.of(context).colorScheme;
final grid   = cs.outlineVariant;
final label  = TextStyle(color: cs.onSurfaceVariant, fontSize: 11);
final series = [cs.primary, cs.tertiary, cs.secondary, cs.error];
```

## Line chart

```dart
LineChart(
  LineChartData(
    minY: 0,
    gridData: FlGridData(show: true, drawVerticalLine: false, horizontalInterval: step,
        getDrawingHorizontalLine: (v) => FlLine(color: grid, strokeWidth: 1)),
    borderData: FlBorderData(show: false),
    titlesData: FlTitlesData(
      topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
      rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
      leftTitles: AxisTitles(sideTitles: SideTitles(
        showTitles: true, reservedSize: 44, interval: step,
        getTitlesWidget: (value, meta) =>
            SideTitleWidget(meta: meta, child: Text(compact.format(value), style: label)),
      )),
      bottomTitles: AxisTitles(sideTitles: SideTitles(
        showTitles: true, reservedSize: 32, interval: 1,
        getTitlesWidget: (value, meta) {
          final i = value.toInt();
          if (i < 0 || i >= points.length) return const SizedBox.shrink();
          return SideTitleWidget(
              meta: meta, child: Text(monthFmt.format(points[i].date), style: label));
        },
      )),
    ),
    lineTouchData: LineTouchData(touchTooltipData: LineTouchTooltipData(
      getTooltipColor: (spot) => cs.inverseSurface,
      getTooltipItems: (spots) => [
        for (final s in spots)
          LineTooltipItem(money.format(s.y), TextStyle(color: cs.onInverseSurface)),
      ],
    )),
    lineBarsData: [
      LineChartBarData(
        spots: [for (var i = 0; i < points.length; i++) FlSpot(i.toDouble(), points[i].value)],
        isCurved: true, preventCurveOverShooting: true, color: cs.primary, barWidth: 3,
        dotData: const FlDotData(show: false),
        belowBarData: BarAreaData(show: true, color: cs.primary.withValues(alpha: 0.12)),
      ),
    ],
  ),
  duration: const Duration(milliseconds: 250),
)
```

API drift between fl_chart majors is the #1 build break here: `tooltipBgColor` became `getTooltipColor`, `swapAnimationDuration` became `duration`, `SideTitleWidget(axisSide: meta.axisSide)` became `SideTitleWidget(meta: meta)`. Pin the version in `pubspec.yaml` and read that version's example, not a blog post. A `reservedSize` that is too small silently clips axis labels, and Arabic labels and Arabic-Indic digits are wider than the English you tested with.

## Bar, pie, donut

```dart
BarChart(BarChartData(
  alignment: BarChartAlignment.spaceAround,
  maxY: maxValue * 1.15,                       // headroom above the tallest bar
  barGroups: [
    for (var i = 0; i < data.length; i++)
      BarChartGroupData(x: i, barRods: [
        BarChartRodData(toY: data[i].value, color: cs.primary, width: 18,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(4))),
      ]),
  ],
  barTouchData: BarTouchData(
      touchTooltipData: BarTouchTooltipData(getTooltipColor: (_) => cs.inverseSurface)),
))

PieChart(PieChartData(
  sectionsSpace: 2,
  centerSpaceRadius: isDonut ? 62 : 0,          // donut = pie with a hole
  sections: [
    for (var i = 0; i < slices.length; i++)
      PieChartSectionData(
        value: slices[i].value, color: series[i % series.length],
        radius: touchedIndex == i ? 66 : 58,
        title: percent.format(slices[i].value / total),
        titleStyle: TextStyle(color: cs.onPrimary, fontWeight: FontWeight.w600),
      ),
  ],
  pieTouchData: PieTouchData(touchCallback: (event, res) => setState(() =>
      touchedIndex = res?.touchedSection?.touchedSectionIndex ?? -1)),
))
```

Bars must start at zero. A truncated `minY` exaggerates differences and is the classic misleading chart.

Cap a pie at ~5 slices and group the rest into `'أخرى'`; beyond 6 it is unreadable — use a bar chart. Never use a pie for values that do not sum to a meaningful whole.

## Dark mode and RTL

Grid lines at full `outline` opacity glare on dark surfaces — use `outlineVariant` or `cs.onSurface.withValues(alpha: 0.08)`, and check the area fill and tooltip surface still separate from the background in both themes. For RTL, note that `leftTitles` / `rightTitles` are **physical** sides, not `start`/`end`; they do not flip with `Directionality`. So:

- Wrap the chart in `Directionality(textDirection: TextDirection.ltr, child: ...)` to keep its internal geometry stable while the surrounding UI stays RTL.
- Arabic reads right-to-left, so a time series should progress right-to-left too. Reverse the **data**, not the widget: build spots from `points.reversed.toList()` and map the bottom titles against that same reversed list. `Transform.flip` mirrors the labels too and produces reversed digits.
- Inside `getTitlesWidget`, wrap a numeric or Latin label in `Directionality(textDirection: TextDirection.ltr, ...)` when the app is RTL.

## Formatting labels with intl

```dart
final compact  = NumberFormat.compact(locale: 'ar');        // ١٢ ألف
final money    = NumberFormat.currency(locale: 'ar_LY', symbol: 'د.ل', decimalDigits: 0);
final percent  = NumberFormat.percentPattern('ar');
final monthFmt = DateFormat.MMM('ar');                       // سبتمبر
```

Call `initializeDateFormatting('ar')` once before formatting dates outside a `MaterialApp` locale context. Verify compact output for your locale, and decide deliberately between Arabic-Indic and Latin digits — then use that same choice in every chart and KPI tile. Axis labels must never overlap: use `NumberFormat.compact` on the value axis and show every *n*th bottom label via `interval:` rather than shrinking the font below 10sp.

## Empty, loading, error

A chart with no data must not render an empty grid — it reads as a broken screen. A single data point is a KPI tile, not a line; one point has no trend.

```dart
Widget build(BuildContext context) => SizedBox(
  height: 220,                                  // same height in every branch, or the page jumps
  child: switch (state) {
    ChartLoading() => const ChartShimmer(),
    ChartFailure(:final message) => ErrorView(message: message, onRetry: onRetry),
    ChartData(:final points) when points.isEmpty =>
        const Center(child: Text('لا توجد بيانات لعرضها في هذه الفترة')),
    ChartData(:final points) => _LineChart(points),
  },
);
```

## Performance

- **Downsample before drawing.** Above ~300 visible points the line is denser than the pixels. Aggregate server-side (per day/week) or reduce with a stride or LTTB, in the repository layer — never in `build`.
- Build `LineChartData` from a pre-computed immutable list. Rebuilding `spots` on every rebuild is the usual cause of chart jank.
- Wrap the chart in `RepaintBoundary` so unrelated `setState` calls do not repaint it.
- Disable `dotData` and set `duration: Duration.zero` for large or rapidly-changing series.

## Accessibility

**Never encode meaning in color alone.** Distinguish series with `dashArray`, markers, or direct labels, and always render a legend for more than one series — a tooltip is not a substitute, being unreachable by keyboard and screen readers. fl_chart paints to a canvas and exposes nothing to assistive tech, so wrap it and state the takeaway:

```dart
Semantics(
  label: 'رسم بياني لمبيعات آخر ٦ أشهر، من ${money.format(minV)} إلى ${money.format(maxV)}',
  child: ExcludeSemantics(child: chart),
)
```

Offer a data table alternative for the same figures, and keep series colors ≥ 3:1 against the surface.

## Exporting a chart as an image

```dart
final _chartKey = GlobalKey();   // on RepaintBoundary(key: _chartKey, child: chart)

Future<Uint8List?> captureChart({double pixelRatio = 3}) async {
  final boundary = _chartKey.currentContext?.findRenderObject() as RenderRepaintBoundary?;
  if (boundary == null) return null;
  final image = await boundary.toImage(pixelRatio: pixelRatio);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  return data?.buffer.asUint8List();
}
```

`ui` is `dart:ui`. The boundary must already be laid out and painted — capturing in `initState` returns null, so capture after the first frame. Off-screen widgets cannot be captured; render the export copy in a subtree that is still painted. Composite the PNG onto an opaque background: the capture is transparent, and a transparent chart is invisible in a light PDF viewer.

## KPI tiles, sparklines, and when a table wins

A dashboard is mostly numbers. Lead with stat tiles: large value, small label, a delta carrying an arrow **and** a sign (not color alone), optionally a sparkline. A sparkline is a `LineChart` with everything off — `titlesData: FlTitlesData(show: false)`, `gridData: FlGridData(show: false)`, `borderData: FlBorderData(show: false)`, `lineTouchData: LineTouchData(enabled: false)`, no dots — in a ~40px-tall box. No axes means no scale, so never print a number on a sparkline; it shows shape only.

Use a table instead of a chart when there are fewer than ~5 values, when exact numbers matter (invoices, financials), when the user will compare or copy precise figures, or when categories are unordered labels. A chart earns its space only for a trend, a comparison across many categories, or a part-to-whole seen at a glance. A three-slice pie is always worse than three rows of text.

## Checklist

- [ ] One chart library, styled entirely from `ColorScheme`
- [ ] Bars and areas start at zero; no truncated axes
- [ ] Loading, empty, and error branches share one fixed height
- [ ] Axis numbers and dates formatted with `intl`; digit style consistent app-wide
- [ ] Verified in dark mode and with the app in Arabic
- [ ] Series distinguishable without color; legend present
- [ ] `Semantics` summary on every chart
- [ ] Large series downsampled; chart wrapped in `RepaintBoundary`
- [ ] fl_chart version pinned and API checked against that version
