---
name: flutter-background-tasks
description: Running work in Flutter when the app is not in the foreground — what each platform actually allows, workmanager periodic and one-off tasks, Android foreground services, app lifecycle handling, silent push as a trigger, offline write queues, Doze mode and OEM task killers, and isolates for heavy CPU work. Use for sync, tracking, or scheduled jobs, or when the user says "خلفية", "مهام مجدولة", "مزامنة", "background", "workmanager", "foreground service", "sync".
---

# Background Tasks

## What is actually possible

Say this to the user before writing code — most background feature requests are impossible as stated on iOS.

| Capability | Android | iOS |
|---|---|---|
| Periodic work | Yes, 15 min minimum, deferred by Doze | `BGAppRefreshTask` — the OS decides if and when; may never run |
| Long-running visible work | Foreground service with a persistent notification | No equivalent; only audio / location / VoIP background modes |
| Exact-time execution | Only with `SCHEDULE_EXACT_ALARM`, alarm-clock apps | Not possible |
| Woken by the server | Data-only FCM message | Silent push, throttled to a few per hour, dropped in Low Power Mode |
| Work while terminated | Yes, WorkManager survives an app kill | Almost never; a user force-quit stops everything until relaunch |

Two consequences that shape the design: **never promise "every hour"** — promise "when the system allows, at least once a day" and show the last successful sync time in the UI; and **the server is the scheduler, not the phone** — if something must happen at a specific time, do it server-side and push the result down.

## workmanager — periodic and one-off

```dart
@pragma('vm:entry-point')            // REQUIRED — the AOT tree-shaker removes it otherwise
void callbackDispatcher() {
  Workmanager().executeTask((task, inputData) async {
    WidgetsFlutterBinding.ensureInitialized();   // before any plugin call
    switch (task) {                  // one dispatcher, many task names
      case 'syncPending': await SyncService().flushQueue();
    }
    return true;                     // false or an exception → retried with backoff
  });
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Workmanager().initialize(callbackDispatcher, isInDebugMode: kDebugMode);
  await Workmanager().registerPeriodicTask('sync-periodic', 'syncPending',
    frequency: const Duration(minutes: 15),        // Android floor; less is ignored
    existingWorkPolicy: ExistingWorkPolicy.keep,   // do not stack a copy per launch
    initialDelay: const Duration(minutes: 5), backoffPolicy: BackoffPolicy.exponential,
    constraints: Constraints(
        networkType: NetworkType.connected, requiresBatteryNotLow: true));
  runApp(const MyApp());
}
```

With `flutter pub add workmanager`, the callback runs in a **separate isolate** with no access to your providers, app state, or open database handles — it constructs everything it needs itself. Use `registerOneOffTask` for fire-and-forget work (upload this file once the network returns); it takes the same constraints plus an `initialDelay`. iOS: enable **Background Modes → Background fetch** and **Background processing** in Xcode, list every task identifier in `BGTaskSchedulerPermittedIdentifiers` in `Info.plist`, and register them at startup. The plugin's iOS surface changed across versions (0.5.x and 0.6+ split fetch and processing tasks differently) — read the installed version's README before wiring iOS, and treat execution there as a bonus, never as the mechanism a feature depends on. It does not fire on its own in development; trigger it from the Xcode debugger with the `_simulateLaunchForTaskWithIdentifier` LLDB call.

## Foreground service (Android, long-running visible work)

For work the user explicitly started and can see: a live tracking session, a long upload, a workout timer. With `flutter_foreground_task`:

```dart
@pragma('vm:entry-point')
void startCallback() => FlutterForegroundTask.setTaskHandler(SyncTaskHandler());

class SyncTaskHandler extends TaskHandler {
  @override                          // onStart and onDestroy are also required overrides
  Future<void> onRepeatEvent(DateTime timestamp) async {
    await SyncService().flushQueue();
    FlutterForegroundTask.updateService(
        notificationTitle: 'جاري المزامنة', notificationText: 'آخر تحديث: ${_fmt(timestamp)}');
  }
}

await FlutterForegroundTask.startService(notificationTitle: 'التطبيق يعمل في الخلفية',
    notificationText: 'اضغط للعودة', callback: startCallback);
```

`TaskHandler` method signatures differ between major versions of the package — check the installed version's example before copying. The persistent, non-dismissible notification is mandatory; it is the contract with both the user and Android. Android 14 (API 34) additionally requires a declared service type, or `startService` throws:

```xml
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<service android:name="com.pravera.flutter_foreground_task.service.ForegroundService" android:foregroundServiceType="dataSync" android:exported="false" />
```

Pick the narrowest type (`dataSync`, `location`, `mediaPlayback`, `microphone`) — Play asks you to justify it, and `dataSync` is capped at roughly 6 hours per day on Android 15.

## App lifecycle

The cheapest win here: stop working the moment the app leaves the screen.

```dart
class _ChatScreenState extends State<ChatScreen> with WidgetsBindingObserver {
  @override
  void initState() { super.initState(); WidgetsBinding.instance.addObserver(this); }
  @override
  void dispose() { WidgetsBinding.instance.removeObserver(this); super.dispose(); }
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        _socket.reconnect();
        _refresh();                    // data is always stale after a pause
      case AppLifecycleState.hidden:   // added in Flutter 3.13, fires before paused
      case AppLifecycleState.paused:
        _timer?.cancel();
        _socket.disconnect();
        _saveDraft();                  // last reliable callback on iOS — persist here,
                                       // not in dispose(), which may never run
      case AppLifecycleState.inactive: // transient (call sheet, app switcher)
      case AppLifecycleState.detached: break;   // going away; start no async work
    }
  }
}
```

## Silent push instead of polling

The only reliable way to make the app act at a time you choose: a data-only FCM message wakes it, it does a short piece of work, it sleeps again.

```json
{ "message": { "token": "…",
    "data": { "type": "sync", "since": "2026-09-01T00:00:00Z" },
    "android": { "priority": "high" },
    "apns": { "headers": { "apns-priority": "5" }, "payload": { "aps": { "content-available": 1 } } } } }
```

No `notification` block, or iOS treats it as a visible alert. Handle it in the top-level `@pragma('vm:entry-point')` background handler (see `flutter-notifications`) and keep the work to a few seconds. iOS throttles these hard and drops them in Low Power Mode, so the same work must also run on the next `resumed`.

## Background location

`geolocator` with `LocationPermission.always` plus `ACCESS_BACKGROUND_LOCATION` on Android, and `UIBackgroundModes: location` with `NSLocationAlwaysAndWhenInUseUsageDescription` on iOS. Know the cost first: Play requires a background-location declaration form and a demo video, Apple review rejects it without a clearly visible user benefit, and both platforms show a recurring "this app has been using your location" prompt that drives uninstalls. If a geofence or significant-location-change suffices, use that instead of continuous tracking.

## Pending-writes queue

What makes an app genuinely offline-capable: writes land in a local table first, a worker drains it.

```dart
Future<void> flushQueue() async {   // table: id, endpoint, payload, attempts, last_error
  for (final op in await db.pendingOps(limit: 50)) {
    try {
      await api.replay(op);                        // server upserts on op.id
      await db.deleteOp(op.id);
    } on ApiException catch (e) {
      if (e.isPermanent) {
        await db.markFailed(op.id, e.message);     // 4xx: never retry forever
      } else {
        await db.bumpAttempts(op.id);
        return;                                    // 5xx/network: stop, keep order
      }
    }
  }
}
```

Trigger it on `resumed`, on connectivity regained (`connectivity_plus` — `onConnectivityChanged` emits a `List<ConnectivityResult>` in v5+, and "connected" is not "reachable", so confirm with a real request), and from the periodic workmanager task. Cap `attempts` and surface a "لم تتم المزامنة" state rather than retrying silently forever.

## Doze, App Standby and OEM killers

- **Doze / App Standby buckets** defer WorkManager jobs on an idle device into batched maintenance windows. Do not fight it — design for "eventually", not "on time".
- **Xiaomi (MIUI), Huawei (EMUI), Oppo/Realme (ColorOS), Vivo and Samsung** kill background work far more aggressively than stock Android, and a swipe-away from recents often terminates WorkManager jobs too. No Dart code fixes this.
- Mitigation is a user instruction, not code: guide the user once, from an in-app screen with device-specific text, to Settings → Battery → unrestricted / autostart. `permission_handler`'s `Permission.ignoreBatteryOptimizations` opens the system dialog on Android — ask only if the app truly needs it, since Play policy restricts the request.
- **Design so a kill is never data loss.** Anything the user typed or captured is persisted locally the instant it exists; background work only moves already-durable data.

## Heavy CPU work — isolates

Background *scheduling* and background *threading* are different problems. Parsing a large payload, image processing or encryption belongs off the UI isolate — but an isolate is not a background task, it dies with the app.

```dart
final parsed = await Isolate.run(() => _parseBigJson(raw));   // Dart 2.19+
final thumb  = await compute(_makeThumbnail, bytes);
// to call a plugin from a spawned isolate, pass RootIsolateToken.instance! in, then:
BackgroundIsolateBinaryMessenger.ensureInitialized(token);
```

Only top-level or static functions, and arguments must be sendable — no `BuildContext`, no open database handle.

## Idempotent and resumable

Assume every background task is killed halfway and runs again later, sometimes twice concurrently.

- Every unit of work carries a client-generated id; the server upserts on it.
- Write progress as you go (`last_synced_at`, a per-item `done` flag) so a rerun continues instead of restarting, and never "read counter, add one, write counter" — use an atomic server-side increment.
- Wrap multi-step local writes in a transaction so a kill leaves no half-state, and log each run's outcome with a timestamp — a background bug is unreproducible without it.

## Common mistakes

- Missing `@pragma('vm:entry-point')` — works in debug, silently never fires in release.
- Forgetting `WidgetsFlutterBinding.ensureInitialized()` in the callback, then crashing on the first plugin call.
- Registering the periodic task on every launch without `ExistingWorkPolicy.keep`, producing dozens of duplicate jobs.
- Expecting a period under 15 minutes on Android, or any guaranteed period on iOS, or testing only on a Pixel or an emulator and then shipping to a Xiaomi user base.
- Using a foreground service to dodge WorkManager limits for invisible work — Play rejects it — or assuming providers, app state or a warm database connection exist in the background isolate.

## Checklist

- [ ] The user has been told plainly what iOS will and will not do
- [ ] `@pragma('vm:entry-point')` and `WidgetsFlutterBinding.ensureInitialized()` on every background entry point
- [ ] Periodic task registered once, with `ExistingWorkPolicy.keep` and constraints
- [ ] Foreground service declares an Android 14 `foregroundServiceType` and shows its notification
- [ ] `AppLifecycleState` handled: timers/sockets stopped and drafts saved on `paused`, refresh on `resumed`
- [ ] Silent push used for server-driven work instead of polling
- [ ] Pending-writes queue with attempt caps and a permanent-vs-transient error split, drained on `resumed`, on reconnect, and from the periodic task
- [ ] Every task idempotent, resumable, safe to run twice; heavy CPU work in `Isolate.run`
- [ ] Battery-optimization guidance for OEM devices; no data loss if a task is killed
- [ ] Last successful run timestamp logged and visible in the UI
