---
name: flutter-analytics
description: Product analytics in a Flutter app — choosing the few events that matter, a typed event catalogue, Firebase Analytics with go_router screen tracking, funnels, consent and ATT, crash and performance monitoring, and reading the numbers without chasing vanity metrics. Use when instrumenting a product or asking why users drop off, or when the user says "تحليلات", "أحداث", "قياس", "سلوك المستخدم", "analytics", "events", "funnel", "retention", "Firebase Analytics".
---

# Analytics

## Decide the events before writing any code

Pick **5–10 events** that answer real questions, and write them down before instrumenting.

| Question | Event class | Example |
|---|---|---|
| Did the user reach value? | Activation | `signup_completed`, `first_report_created` |
| Are they doing the thing the app exists for? | Core action | `report_created`, `order_placed` |
| Do they come back? | Retention | session/`app_open` (automatic) + core action per user per day |
| Where do they quit? | Drop-off | `checkout_started` vs `checkout_completed` |
| What breaks? | Errors | `payment_failed` with a `reason` property |

If an event can never change a decision you would actually make, do not log it. A `button_tapped` on every widget is noise; a missing `checkout_started` is the whole product question. Logging everything also produces a dashboard nobody reads and a privacy liability.

## Naming convention

- `snake_case`, lowercase, ASCII, `object_action` in past tense: `report_created`, `order_placed`, `filter_applied` — not `createReport`, `TapOrder`, `Filter`.
- Property names identical everywhere: always `report_id`, never `reportId` here and `id` there. Values are ids and enums — never free text, never a user-typed string.
- Firebase limits: event name ≤ 40 chars, ≤ 25 parameters per event, string parameter values ≤ 100 chars, ~500 distinct event names per app, 25 user properties. Names starting with `firebase_`, `google_`, `ga_` are reserved. Verify the current limits in Firebase's docs before designing a wide event.

## A typed event catalogue

Event names must never appear as string literals inside widgets — a typo becomes a silently missing event that nobody notices for a month. One `sealed` hierarchy makes the compiler list every event the app can send, and adding a property becomes a compile error at each call site instead of silent schema drift.

```dart
// lib/analytics/events.dart
sealed class AppEvent {
  const AppEvent();
  String get name;
  Map<String, Object> get params => const {};
}

class ReportCreated extends AppEvent {
  final String reportId;
  final String category;
  final int photoCount;
  const ReportCreated(this.reportId, this.category, this.photoCount);
  @override
  String get name => 'report_created';
  @override
  Map<String, Object> get params =>
      {'report_id': reportId, 'category': category, 'photo_count': photoCount};
}
```

## Firebase Analytics implementation

`flutter pub add firebase_analytics`, then keep every SDK call behind one class:

```dart
// lib/analytics/analytics.dart
class Analytics {
  Analytics(this._fa);
  final FirebaseAnalytics _fa;
  Future<void> log(AppEvent e) async {
    if (kDebugMode && !Env.analyticsInDebug) {   // never pollute production data
      debugPrint('[analytics] ${e.name} ${e.params}');
      return;
    }
    await _fa.logEvent(name: e.name, parameters: e.params);
  }

  Future<void> identify(String? userId) => _fa.setUserId(id: userId);
  Future<void> setPlan(String plan) =>
      _fa.setUserProperty(name: 'plan', value: plan);   // 'free' | 'pro'
  Future<void> screen(String name) =>
      _fa.logScreenView(screenName: name, screenClass: name);
  Future<void> setEnabled(bool on) => _fa.setAnalyticsCollectionEnabled(on);
}
```

`setUserId` takes an **opaque internal id** — never an email, phone number or anything that identifies a person outside your system. User properties are for slicing (`plan`, `city_zone`, `locale`, `signup_month`), not for storing data. `parameters` on `logEvent` is `Map<String, Object>?` and values must be non-null `String` or `num`; a `bool` or a nested map is dropped silently, so send `1`/`0` or a string.

## Screen tracking with go_router

```dart
class AnalyticsRouteObserver extends NavigatorObserver {
  AnalyticsRouteObserver(this._analytics);
  final Analytics _analytics;

  void _send(Route<dynamic>? route) {
    final name = route?.settings.name;
    if (route is PageRoute && name != null && name.isNotEmpty) _analytics.screen(name);
  }

  @override
  void didPush(Route route, Route? prev) => _send(route);
  @override
  void didPop(Route route, Route? prev) => _send(prev);
  @override
  void didReplace({Route? newRoute, Route? oldRoute}) => _send(newRoute);
}

GoRouter(observers: [AnalyticsRouteObserver(analytics)], routes: [...]);
```

This depends on `route.settings.name` being populated, which in turn depends on giving every `GoRoute` a `name:` and on how your go_router version names its pages — verify in DebugView that real screen names arrive, and if they come through null or as raw paths, log `screen_view` explicitly from each screen instead. `firebase_analytics` also ships `FirebaseAnalyticsObserver`, which accepts a `nameExtractor`; check its current signature against the package version in `pubspec.lock`. Note that `StatefulShellBranch` has its own navigator, so a top-level observer may miss tab-internal pushes — attach observers per branch if tabs matter.

## Funnels

A funnel is only measurable if every step is a real event with a shared correlation property — `checkout_started → address_entered → payment_method_selected → order_placed`. Requirements: consistent ordering, one event per step (never a single `checkout_step` with a `step` number if you want per-step user counts in Firebase's funnel UI), a shared `checkout_id` so steps can be joined, and a failure event (`payment_failed` with `reason`) so the drop is explained rather than merely counted. Log the *attempt*, not only the success — a funnel with no `..._started` event tells you nothing.

## Alternatives

| | Firebase Analytics | PostHog | Mixpanel | Amplitude |
|---|---|---|---|---|
| Cost | free, unlimited events | generous free tier, self-hostable | free tier, then per-event | free tier, then per-event |
| Raw event access | via BigQuery export | full, SQL | yes | yes |
| Funnels/retention UI | basic, sampled, delayed | strong | strong | strong |
| Session replay / feature flags | no | yes | partial | partial |

Only Firebase Analytics ties natively into Crashlytics and Performance, and it is the default when you already use Firebase and want zero cost. Reach for PostHog or Amplitude when you need ad-hoc funnels and cohort analysis without BigQuery. Sending to two backends is legitimate — put both behind the single `Analytics` class above so call sites do not change.

## Consent and privacy

Never log: name, email, phone, national id, message or note content, search text, exact address, or precise location. Log an `is_logged_in` flag, a `city_zone`, an internal id — nothing that would embarrass you in a data-subject request.

- Give the user a real, discoverable toggle and honour it with `setAnalyticsCollectionEnabled(false)`; disabled means events are not queued for later. `firebase_analytics` also exposes `setConsent(...)` for storage/ad consent signals — required in the EU/UK alongside a CMP; confirm its parameter names against your package version.
- Both stores require a privacy policy and a data-collection declaration: App Store **privacy labels** (App Privacy in App Store Connect) and Google Play **Data safety**. Declare analytics identifiers and crash data; an undeclared SDK is a rejection or a takedown, and Play checks this against the SDKs it detects in the bundle.

### App Tracking Transparency (iOS)

If you use IDFA, cross-app attribution, or ad SDKs, iOS requires the ATT prompt (`app_tracking_transparency`). Add `NSUserTrackingUsageDescription` to `Info.plist` with an Arabic-localized reason, then request **after** a short pre-prompt explaining the benefit — asking cold gets a low opt-in rate.

Skipping it: without authorization the IDFA is zeroed, so attribution and ad audiences degrade badly, and shipping tracking without the prompt is an App Review rejection (Guideline 5.1.2) and can get the app pulled. Plain Firebase Analytics using only the app-instance id still works without ATT.

## Crashes and performance are the same picture

An event drop-off is often a crash or a 10-second screen, not a UX problem. **Crashlytics** (`firebase_crashlytics`) or **Sentry** (`sentry_flutter`): route `FlutterError.onError` and `PlatformDispatcher.instance.onError` into it, upload symbols on release builds, and attach the internal user id and the last few event names as breadcrumbs — never PII. **`firebase_performance`** gives automatic app-start, screen-rendering and HTTP metrics, plus custom traces on the flows you care about. Read them at p90/p95, not the average — the average hides the users who leave.

```dart
final trace = FirebasePerformance.instance.newTrace('checkout_flow');
await trace.start();
trace.putAttribute('payment_method', 'card');
try {
  await runCheckout();
  trace.putMetric('items', cart.length);
} finally {
  await trace.stop();   // always stop, or the trace is never reported
}
```

## Debug guard and validation

Development traffic in production data corrupts every conversion rate you compute. The `kDebugMode` guard above handles the obvious case; also exclude internal testers via a user property or a separate Firebase project for staging. Before shipping, prove events actually arrive:

- Enable **DebugView** in the Firebase console — Android: `adb shell setprop debug.firebase.analytics.app com.example.app`; iOS: add `-FIRDebugEnabled` to the scheme's launch arguments.
- Turn the guard off locally (`Env.analyticsInDebug`) while validating, and confirm each event's **name and every parameter** — Firebase discards unknown or wrongly typed parameters silently, so an event arriving with two of its four properties is the normal failure mode and only DebugView shows it.
- Standard reports lag by hours and are sampled; DebugView is near real-time, so never conclude "it does not work" from an empty dashboard on day one.

## Reading the numbers

Vanity metrics — total installs, total screen views, cumulative registered users — only ever go up and cannot tell you if the product works. Ignore them. For a small app, two numbers matter:

1. **Retention**: of users who activated in a given week, how many performed the core action again in week 2, week 4? A flat-ish curve means the product works; a curve to zero means nothing else is worth optimizing yet.
2. **Core-action completion rate**: of users who started the core flow, how many finished it? Segment by locale, platform and app version — a drop confined to one version is a bug, not a market.

Screen views are diagnostic, never a success metric, and small-scale absolute counts are noise: 12 vs 15 conversions is not a result — prefer rates and cohorts of comparable size.

## Common mistakes

- Instrumenting first and deciding what to measure afterwards.
- Event names as string literals in widgets; two spellings of the same event.
- Logging PII, search text or message content into event parameters.
- Debug/test traffic mixed into production data, or an event assumed to work because it compiles — never validated in DebugView.
- Only logging successes, so a funnel has no denominator.
- Shipping ad/attribution SDKs without ATT or without store data-safety declarations.
- Reading total installs instead of retention and core-action completion.

## Checklist

- [ ] 5–10 events chosen and written down before instrumenting
- [ ] `snake_case` `object_action` names with consistent property names, in a central typed event catalogue; no event-name literals in widgets
- [ ] `setUserId` uses an opaque internal id, never an email
- [ ] Screen tracking wired to go_router and verified per tab
- [ ] Every funnel step logged, including the start and the failure reason
- [ ] No PII, message content, search text or precise location in parameters
- [ ] Consent toggle honoured with `setAnalyticsCollectionEnabled`
- [ ] ATT prompt + `NSUserTrackingUsageDescription` if tracking or ads; App Store privacy labels and Play Data safety declarations match reality
- [ ] Crashlytics/Sentry wired with PII-free breadcrumbs; perf traces on key flows
- [ ] `kDebugMode` guard so dev traffic stays out of production
- [ ] Every event verified in DebugView with all parameters before release
- [ ] Dashboard shows retention and core-action rate, not installs
