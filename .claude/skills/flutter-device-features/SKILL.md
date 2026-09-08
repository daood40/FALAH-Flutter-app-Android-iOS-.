---
name: flutter-device-features
description: Native device capabilities in Flutter — camera and gallery, file picking and saving, location and maps, sharing, QR scanning, connectivity, permissions, deep links, and writing platform channels. Use when the app needs hardware or OS features, or when the user says "كاميرا", "صور", "موقع", "خريطة", "مشاركة", "ملفات", "camera", "location", "map", "permissions", "QR".
---

# Device & Platform Features

## Permissions (do this first for every feature below)

```bash
flutter pub add permission_handler
```

```dart
Future<bool> ensure(Permission p) async {
  var status = await p.status;
  if (status.isGranted) return true;
  if (status.isPermanentlyDenied) { await openAppSettings(); return false; }
  status = await p.request();
  return status.isGranted;
}
```

Ask at the moment of use, after a one-line explanation of why. Declare in `AndroidManifest.xml` and add a localized `NS*UsageDescription` to `Info.plist` for every iOS permission — a missing purpose string crashes the app on iOS and fails review.

## Camera & gallery

```bash
flutter pub add image_picker flutter_image_compress
```

```dart
final picker = ImagePicker();
final x = await picker.pickImage(
  source: ImageSource.camera,
  maxWidth: 1600,
  imageQuality: 80,            // compress at capture
);
if (x == null) return;         // user cancelled — always handle

final compressed = await FlutterImageCompress.compressWithFile(
  x.path, minWidth: 1280, quality: 75,
);
```

Multiple: `pickMultiImage()`. Video: `pickVideo(source:, maxDuration:)`.

Notes: on Android the picked file lives in a cache directory that can be cleared — copy it to app documents if you need it later. Always compress before upload. For a custom camera UI (overlays, continuous capture) use the `camera` package, and dispose its controller.

## Files

```bash
flutter pub add file_picker path_provider share_plus open_filex
```

```dart
final res = await FilePicker.platform.pickFiles(
  type: FileType.custom,
  allowedExtensions: ['pdf', 'docx'],
  allowMultiple: false,
);
final path = res?.files.single.path;

// where to write
final docs = await getApplicationDocumentsDirectory();  // persists, backed up
final tmp = await getTemporaryDirectory();              // OS may delete
final support = await getApplicationSupportDirectory(); // persists, not user-visible

// share / export — the correct way to "save" a file on both platforms
await Share.shareXFiles([XFile(file.path)], text: 'تقرير البلاغات');

await OpenFilex.open(file.path);
```

Do not write to arbitrary paths — scoped storage on Android and the sandbox on iOS forbid it. `getExternalStorageDirectory()` is Android-only and still app-scoped.

## Location

```bash
flutter pub add geolocator geocoding
```

```dart
if (!await Geolocator.isLocationServiceEnabled()) {
  await Geolocator.openLocationSettings();
  return;
}
var perm = await Geolocator.checkPermission();
if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
if (perm == LocationPermission.deniedForever) { await Geolocator.openAppSettings(); return; }

final pos = await Geolocator.getCurrentPosition(
  locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
);

final places = await placemarkFromCoordinates(pos.latitude, pos.longitude,
    localeIdentifier: 'ar');
```

Two separate failure modes — **service off** and **permission denied** — need different messages and different fixes; handle both.

Continuous updates: `Geolocator.getPositionStream(...)` — cancel the subscription in `dispose`, and set a `distanceFilter` so you aren't waking the GPS constantly.

Background location requires extra manifest entries, a foreground-service notification on Android, `NSLocationAlwaysAndWhenInUseUsageDescription` on iOS, and a written justification to both stores. Avoid it unless the app genuinely cannot work without it.

## Maps

`google_maps_flutter` (needs an API key per platform, restricted by package name/SHA-1 and bundle id — restrict it, an open key is billable by anyone) or `flutter_map` (OpenStreetMap tiles, no key, no billing).

```dart
GoogleMap(
  initialCameraPosition: CameraPosition(target: LatLng(32.8872, 13.1913), zoom: 12),
  markers: reports.map((r) => Marker(
    markerId: MarkerId(r.id),
    position: LatLng(r.lat, r.lng),
    infoWindow: InfoWindow(title: r.title),
  )).toSet(),
  onMapCreated: (c) => _controller.complete(c),
  myLocationEnabled: true,
)
```

Cluster markers above ~100 pins (`google_maps_cluster_manager`) — hundreds of individual markers will jank. Store coordinates in Postgres with PostGIS/`earthdistance` and query by radius server-side rather than downloading everything.

## QR / barcode

```bash
flutter pub add mobile_scanner qr_flutter
```

```dart
MobileScanner(onDetect: (capture) {
  final code = capture.barcodes.first.rawValue;
  if (code == null || _handled) return;
  _handled = true;                      // guard: onDetect fires repeatedly
  _controller.stop();
  _handle(code);
});
```

Generating: `QrImageView(data: value, size: 220)`.

## Connectivity

```dart
final result = await Connectivity().checkConnectivity();
Connectivity().onConnectivityChanged.listen((r) => _onChange(r));
```

Connectivity means "a network interface exists", not "the internet works". Confirm with a lightweight request before telling the user they're online.

## Other common ones

| Need | Package |
|---|---|
| Open a URL / phone / email | `url_launcher` |
| Device & OS info | `device_info_plus` |
| App version | `package_info_plus` |
| Vibration / haptics | `HapticFeedback.mediumImpact()` (built in) |
| Battery, sensors | `battery_plus`, `sensors_plus` |
| Local auth | `local_auth` (see `flutter-security`) |
| Background work | `workmanager` (Android-friendly; iOS background execution is severely limited) |

## Platform channels (when no package exists)

```dart
const _ch = MethodChannel('com.example.app/native');

Future<String?> serial() async {
  try {
    return await _ch.invokeMethod<String>('getSerial');
  } on PlatformException catch (e) {
    logger.w('native call failed: ${e.code}');
    return null;
  } on MissingPluginException {
    return null;   // platform not implemented (e.g. web)
  }
}
```

```kotlin
// android/app/src/main/kotlin/.../MainActivity.kt
class MainActivity : FlutterActivity() {
  override fun configureFlutterEngine(engine: FlutterEngine) {
    super.configureFlutterEngine(engine)
    MethodChannel(engine.dartExecutor.binaryMessenger, "com.example.app/native")
      .setMethodCallHandler { call, result ->
        when (call.method) {
          "getSerial" -> result.success(Build.SERIAL)
          else -> result.notImplemented()
        }
      }
  }
}
```

Implement every channel on every platform you ship, or guard the call. Use `EventChannel` for a native stream. Keep native work off the main thread.

## Before shipping any device feature

- [ ] Permission denied path handled with a settings link
- [ ] Permanently-denied path handled separately
- [ ] Cancelled picker returns cleanly
- [ ] Feature degrades gracefully when unavailable (no camera, no GPS, web platform)
- [ ] Tested on a real device — emulators fake camera, GPS and sensors
- [ ] iOS purpose strings written in the user's language
- [ ] API keys restricted by package/bundle id
