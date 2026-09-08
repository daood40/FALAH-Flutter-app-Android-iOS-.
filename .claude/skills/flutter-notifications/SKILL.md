---
name: flutter-notifications
description: Push and local notifications in Flutter — Firebase Cloud Messaging setup for Android and iOS, permissions, foreground/background/terminated handling, notification tap routing, local scheduled reminders, and topics. Use when adding notifications or reminders, or when the user says "إشعارات", "تنبيهات", "notification", "FCM", "push", "reminder".
---

# Notifications (FCM + Local)

## Packages

```bash
flutter pub add firebase_core firebase_messaging flutter_local_notifications
dart pub global activate flutterfire_cli
flutterfire configure     # generates lib/firebase_options.dart
```

`flutterfire configure` also writes `google-services.json` (Android) and `GoogleService-Info.plist` (iOS). Add both to `.gitignore` and keep them out of a public repo.

## Init

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  FirebaseMessaging.onBackgroundMessage(_bgHandler);
  await NotificationService.I.init();
  runApp(const MyApp());
}

// MUST be a top-level function, not a closure or a method
@pragma('vm:entry-point')
Future<void> _bgHandler(RemoteMessage m) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  // keep this light — no UI, no long work
}
```

## Permissions

```dart
final settings = await FirebaseMessaging.instance.requestPermission(
  alert: true, badge: true, sound: true,
);
final granted = settings.authorizationStatus == AuthorizationStatus.authorized;
```

Android 13+ needs `POST_NOTIFICATIONS` in the manifest, and the request above triggers the system dialog.

Ask **in context**, not on first launch. A prompt shown after the user creates their first report ("نبّهني عند الرد") is accepted far more often than one shown at startup. If denied, do not re-prompt — offer a button that opens system settings (`app_settings` package).

## Token

```dart
final token = await FirebaseMessaging.instance.getToken();
await _saveToken(token);
FirebaseMessaging.instance.onTokenRefresh.listen(_saveToken);
```

Store tokens in a `device_tokens` table keyed by `(user_id, token)` with a `platform` and `updated_at`. Delete the row on sign-out — otherwise the next notification goes to a device that is no longer logged in as that user. Prune tokens the FCM API reports as unregistered.

## The three delivery states

| App state | What happens | What you must do |
|---|---|---|
| Foreground | No system notification on Android by default | Show one yourself with `flutter_local_notifications` via `onMessage` |
| Background | System tray shows it | Handle the tap in `onMessageOpenedApp` |
| Terminated | System tray shows it | Read `getInitialMessage()` on startup |

```dart
FirebaseMessaging.onMessage.listen((m) => _showLocal(m));
FirebaseMessaging.onMessageOpenedApp.listen(_route);
final initial = await FirebaseMessaging.instance.getInitialMessage();
if (initial != null) _route(initial);      // do not forget this one
```

Forgetting `getInitialMessage()` is the single most common notification bug: tapping a notification from a killed app just opens the home screen.

## Local notification channel + display

```dart
const channel = AndroidNotificationChannel(
  'high_importance', 'تنبيهات مهمة',
  importance: Importance.high,
);

await _plugin
    .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
    ?.createNotificationChannel(channel);

await _plugin.initialize(
  const InitializationSettings(
    android: AndroidInitializationSettings('@mipmap/ic_launcher'),
    iOS: DarwinInitializationSettings(),
  ),
  onDidReceiveNotificationResponse: (r) => _routeFromPayload(r.payload),
);

void _showLocal(RemoteMessage m) {
  final n = m.notification;
  if (n == null) return;
  _plugin.show(
    n.hashCode, n.title, n.body,
    NotificationDetails(
      android: AndroidNotificationDetails(channel.id, channel.name,
          importance: Importance.high, priority: Priority.high),
      iOS: const DarwinNotificationDetails(),
    ),
    payload: jsonEncode(m.data),
  );
}
```

Create the channel **before** the first notification — a channel's importance cannot be raised after creation; you would have to change the channel id.

## Routing a tap

Put the destination in `data`, never in the display text:

```json
{
  "notification": { "title": "رد جديد على بلاغك", "body": "اضغط للعرض" },
  "data": { "type": "report", "id": "42" }
}
```

```dart
void _route(RemoteMessage m) {
  final type = m.data['type'];
  final id = m.data['id'];
  if (type == 'report' && id != null) {
    rootNavigatorKey.currentContext?.push('/report/$id');
  }
}
```

Use a global navigator key (or your router instance) — you have no `BuildContext` in these callbacks. If the tap arrives before the router is ready, queue the route and apply it after the first frame.

## Sending (server side)

```ts
// Supabase Edge Function using the FCM HTTP v1 API
await fetch(`https://fcm.googleapis.com/v1/projects/${PROJECT}/messages:send`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    message: {
      token: deviceToken,
      notification: { title, body },
      data: { type: 'report', id },
      android: { priority: 'HIGH' },
      apns: { payload: { aps: { sound: 'default', badge: 1 } } },
    },
  }),
});
```

The legacy server key API is retired — use HTTP v1 with a service account. The service account JSON lives on the server only.

Trigger it from a Postgres trigger or a `pg_cron` job so notifications are sent by the database event, not by the client.

## Topics

```dart
await FirebaseMessaging.instance.subscribeToTopic('announcements_ar');
await FirebaseMessaging.instance.unsubscribeFromTopic('announcements_ar');
```

Good for broadcast by language or region. Not for per-user messages — a topic is public; anyone who knows the name can subscribe.

## Local scheduled reminders (no server)

```bash
flutter pub add timezone
```

```dart
tz.initializeTimeZones();
tz.setLocalLocation(tz.getLocation(await FlutterTimezone.getLocalTimezone()));

await _plugin.zonedSchedule(
  id, 'تذكير', 'حان وقت مهمتك',
  tz.TZDateTime.from(when, tz.local),
  const NotificationDetails(android: AndroidNotificationDetails('reminders', 'تذكيرات')),
  androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
  matchDateTimeComponents: DateTimeComponents.time,   // daily
);
```

Exact alarms on Android 13+ require the `SCHEDULE_EXACT_ALARM` / `USE_EXACT_ALARM` permission and are heavily restricted — use inexact scheduling unless the app is genuinely an alarm clock. Reschedule everything after a device reboot (`RECEIVE_BOOT_COMPLETED`).

## iOS specifics

- Enable **Push Notifications** and **Background Modes → Remote notifications** capabilities in Xcode.
- Upload an APNs auth key (`.p8`) to the Firebase console.
- Push does not work on the iOS Simulator — test on a real device.
- iOS shows no foreground banner unless you call `setForegroundNotificationPresentationOptions(alert: true, badge: true, sound: true)`.

## Checklist

- [ ] `getInitialMessage()` handled
- [ ] Foreground messages displayed manually
- [ ] Channel created before first use
- [ ] Tap routing driven by `data`, not text
- [ ] Tokens saved, refreshed, and deleted on sign-out
- [ ] Permission asked in context, with a settings fallback
- [ ] Notification text localized on the server per the user's saved language
- [ ] Tested in all three app states on a real device
