---
name: flutter-media
description: Audio and video in Flutter — video_player and chewie, custom controls, just_audio with background playback and lock-screen controls, recording with record, compression, thumbnails, caching and interruption handling. Use when the app plays or records media, or when the user says "فيديو", "صوت", "تشغيل", "تسجيل", "مشغل", "قرآن", "بودكاست", "video", "audio", "player", "record".
---

# Media: Video & Audio

Two independent stacks. Video: `video_player` (platform surface) + `chewie` (UI). Audio: `just_audio` (playback) + `just_audio_background` / `audio_service` (background + lock screen) + `audio_session` (interruptions). Never use `video_player` for audio-only playback — it has no background support.

## Video playback

```dart
// State: late final VideoPlayerController _video; ChewieController? _chewie; Object? _error;
// initState: _video = VideoPlayerController.networkUrl(Uri.parse(widget.url)); _init();
Future<void> _init() async {
  try {
    await _video.initialize();
    _chewie = ChewieController(
      videoPlayerController: _video,
      autoPlay: false,
      aspectRatio: _video.value.aspectRatio,
      allowFullScreen: true,
      deviceOrientationsOnEnterFullScreen: const [DeviceOrientation.landscapeLeft,
                                                  DeviceOrientation.landscapeRight],
      deviceOrientationsAfterFullScreen: const [DeviceOrientation.portraitUp],
      errorBuilder: (_, msg) => Center(child: Text('تعذر تشغيل الفيديو: $msg')),
    );
  } catch (e) {
    _error = e;
  }
  if (mounted) setState(() {});
}
// dispose(): _chewie?.dispose() FIRST, then _video.dispose(), then super.dispose()
// build(): _error != null -> Arabic error text; _chewie == null -> CircularProgressIndicator;
// else AspectRatio(aspectRatio: _video.value.aspectRatio, child: Chewie(controller: _chewie!))
```

Sources: `.asset('assets/intro.mp4')`, `.file(File(path))` for picked or recorded clips, `.networkUrl(Uri.parse(url))` for MP4, HLS `.m3u8` and DASH. HLS is handled natively by ExoPlayer and AVPlayer — no extra package. Progressive MP4 over a slow network stalls; ship HLS for anything over ~2 minutes. `_video.value.isBuffering` drives the spinner overlay, `hasError` + `errorDescription` the error state. Render both, always.

## Custom controls overlay

Pass `customControls:` to `ChewieController`, or drop chewie and stack your own on the `VideoPlayer` widget. The controller is a `ValueNotifier<VideoPlayerValue>`, so listen to it directly:

```dart
ValueListenableBuilder<VideoPlayerValue>(
  valueListenable: _video,
  builder: (context, v, _) => Column(children: [
    if (v.isBuffering) const LinearProgressIndicator(),
    VideoProgressIndicator(_video, allowScrubbing: true),
    Row(children: [
      IconButton(
        icon: Icon(v.isPlaying ? Icons.pause : Icons.play_arrow),
        tooltip: v.isPlaying ? 'إيقاف مؤقت' : 'تشغيل',
        onPressed: () => v.isPlaying ? _video.pause() : _video.play(),
      ),
      Text('${_fmt(v.position)} / ${_fmt(v.duration)}'),
    ]),
  ]),
)
```

Auto-hide with a `Timer` reset on every tap. On fullscreen enter call `SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky)`, and restore `SystemUiMode.edgeToEdge` on exit — otherwise the status bar stays hidden after the route pops.

## Audio with background playback

`just_audio_background` covers a notification, play/pause/seek and lock-screen art. Use full `audio_service` with a `BaseAudioHandler` only for custom actions, Android Auto or a native-driven queue.

```dart
// main(), after WidgetsFlutterBinding.ensureInitialized()
await JustAudioBackground.init(
  androidNotificationChannelId: 'com.example.app.audio',
  androidNotificationChannelName: 'تشغيل الصوت',
  androidNotificationOngoing: true,
);
final player = AudioPlayer();
await player.setAudioSources([
  AudioSource.uri(Uri.parse(url1), tag: MediaItem(
      id: '1', title: 'سورة البقرة', artist: 'الشيخ فلان', artUri: Uri.parse(artUrl))),
  AudioSource.uri(Uri.parse(url2), tag: MediaItem(id: '2', title: 'سورة آل عمران')),
], initialIndex: 0);
await player.play();
await player.seek(const Duration(minutes: 12), index: 1);   // seeks within or across items
await player.setSpeed(1.5);                                 // also setLoopMode, seekToNext
```

`setAudioSources` is the current playlist API (just_audio 0.10+); on 0.9.x it is `ConcatenatingAudioSource(children: [...])` passed to `setAudioSource`. Check the pinned version before writing playlist mutation code — `addAudioSource` / `removeAudioSourceAt` moved from the concatenating source onto the player. Every item needs a `MediaItem` tag or the notification renders blank. Bind UI to `positionStream`, `bufferedPositionStream`, `durationStream`, `playerStateStream` (`playing` + `processingState`) and `sequenceStateStream` (current item), combining the first three with `rxdart`'s `Rx.combineLatest3` instead of nesting three `StreamBuilder`s.

### Platform requirements — `AndroidManifest.xml`

```xml
<uses-permission android:name="android.permission.WAKE_LOCK" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />
<!-- inside <application>, next to <activity android:launchMode="singleTask"> -->
<service android:name="com.ryanheise.audioservice.AudioService"
         android:foregroundServiceType="mediaPlayback" android:exported="true">
  <intent-filter><action android:name="android.media.browse.MediaBrowserService" /></intent-filter>
</service>
<receiver android:name="com.ryanheise.audioservice.MediaButtonReceiver" android:exported="true">
  <intent-filter><action android:name="android.intent.action.MEDIA_BUTTON" /></intent-filter>
</receiver>
```

`MainActivity` must extend `AudioServiceActivity`, not `FlutterActivity`, or tapping the notification will not reopen the app. iOS: add `audio` to `UIBackgroundModes` in `Info.plist` (Background Modes → Audio in Xcode). Without it, iOS suspends playback the moment the screen locks.

## Long audio with resume (Quran, lectures)

Persist the position, not just the track id, and throttle the writes — `positionStream` fires several times a second.

```dart
player.positionStream
    .throttleTime(const Duration(seconds: 5))   // rxdart
    .listen((p) => prefs.setInt('pos_$trackId', p.inMilliseconds));
await player.setUrl(url,                        // resume where the user stopped
    initialPosition: Duration(milliseconds: prefs.getInt('pos_$trackId') ?? 0));
```

`setUrl` / `setAudioSource` take `initialPosition`, which is cheaper and glitch-free versus `play()` then `seek()`. Also flush the position on `AppLifecycleState.paused`, and reset it to zero when `processingState` reaches `ProcessingState.completed`.

## Recording

```dart
final _rec = AudioRecorder();                       // record ^5.x
if (await _rec.hasPermission()) {
  final dir = await getApplicationDocumentsDirectory();
  await _rec.start(
    const RecordConfig(encoder: AudioEncoder.aacLc, bitRate: 64000,
                       sampleRate: 44100, numChannels: 1),
    path: '${dir.path}/rec_${DateTime.now().millisecondsSinceEpoch}.m4a',
  );
}
final savedPath = await _rec.stop();                // String?; then _rec.dispose()
```

`aacLc` in an `.m4a` container is the one encoder that works unchanged on Android, iOS and web. Mono at 64 kbps is ~0.5 MB per minute — fine for voice, small enough to upload. Add `RECORD_AUDIO` to the manifest and `NSMicrophoneUsageDescription` (written in Arabic) to `Info.plist`. `_rec.pause()`, `resume()` and `cancel()` exist; `onStateChanged()` streams `RecordState`.

Waveform: `_rec.onAmplitudeChanged(const Duration(milliseconds: 100))` emits `Amplitude` with `current` and `max` in **dBFS** — negative, roughly −60 to 0. Normalize before drawing: `((db + 60) / 60).clamp(0.0, 1.0)`. Keep a fixed-length list of recent values and paint it with a `CustomPainter`; do not rebuild a `ListView` of bars per tick.

## Picking, compressing, thumbnails, caching

```dart
final picked = await ImagePicker().pickVideo(
    source: ImageSource.gallery, maxDuration: const Duration(minutes: 3));
VideoCompress.compressProgress$.subscribe((p) => setState(() => _progress = p / 100));
final info = await VideoCompress.compressVideo(picked!.path,
    quality: VideoQuality.MediumQuality, deleteOrigin: false, includeAudio: true);
final thumb = await VideoCompress.getFileThumbnail(picked.path, quality: 50, position: -1);
await VideoCompress.deleteAllCache();      // compression leaves temp files behind
```

`info` carries `path`, `filesize` and `duration`. Compression is heavy: show progress and allow `VideoCompress.cancelCompression()`. The package is lightly maintained — verify it against your Android target SDK and consider `light_compressor` instead; for thumbnails alone, `video_thumbnail` writes a JPEG from a local path or URL. Cache remote media with `flutter_cache_manager` (`DefaultCacheManager().getSingleFile(url)`) and hand the `File` to `VideoPlayerController.file` — progressive MP4 and MP3 only, since **HLS cannot be cached this way**: the URL is a manifest of many segments. For audio, `just_audio`'s `LockCachingAudioSource(Uri.parse(url))` streams and caches in one pass (also non-HLS).

## Interruptions, ducking, headphones

```dart
final session = await AudioSession.instance;
await session.configure(const AudioSessionConfiguration.music());
session.interruptionEventStream.listen((e) {
  final duck = e.type == AudioInterruptionType.duck;
  if (e.begin) {
    duck ? player.setVolume(0.3) : player.pause();
  } else if (duck) {
    player.setVolume(1.0);
  } else if (e.type == AudioInterruptionType.pause) {
    player.play();                  // transient and ours to resume; unknown stays paused
  }
});

session.becomingNoisyEventStream.listen((_) => player.pause());  // headphones unplugged
```

Never auto-resume after an `unknown` interruption — that is the phone-call case, and resuming mid-call is the top complaint. `becomingNoisy` must pause; blasting audio out of the speaker after the user pulls the jack is a bug, not a feature.

## Web, memory and battery

- Browsers block autoplay with sound until the user has interacted with the page — `player.play()` from `initState` silently fails or throws `NotAllowedError`. Start muted (`setVolume(0)`) and unmute on first tap, or require a play button. Background audio does not exist on web.
- **Never keep several `VideoPlayerController`s alive in a scrolling list.** Each holds a hardware decoder; devices allow only a handful and the rest fail silently. Keep one controller in the list's state and swap its data source as the visible item changes — detect it with `visibility_detector` (`onVisibilityChanged` → `info.visibleFraction > 0.6`).
- Dispose every controller, recorder and `AudioPlayer`. A leaked `AudioPlayer` holds the audio session and wakelock and drains the battery long after the screen is gone.
- Pause video on `AppLifecycleState.paused`; video is never allowed to play in the background.
- Do not create an `AudioPlayer` per row or call `setUrl` on every item just to read its duration — store durations in the data model and let just_audio handle look-ahead.

## Common mistakes

- Disposing `VideoPlayerController` before `ChewieController` — chewie first.
- `setState` after `await controller.initialize()` without `if (!mounted) return;`.
- Using `value.aspectRatio` before `isInitialized` — it is `1.0` until then, so the layout jumps.
- Declaring the `audio_service` Android service but leaving `MainActivity` on `FlutterActivity`.
- Recording into `getTemporaryDirectory()`, or playing a picker's raw `File` path without copying it first — both files disappear out from under you.

## Checklist

- [ ] Every controller, player and recorder disposed, in the right order
- [ ] Loading, buffering and error states rendered for video
- [ ] One video controller per list, driven by visibility
- [ ] `audio_session` configured; interruption and becoming-noisy handled
- [ ] Android foreground service + `AudioServiceActivity`; iOS `UIBackgroundModes: audio`
- [ ] `MediaItem` tags set so the lock screen shows title and artwork
- [ ] Position persisted (throttled) and restored via `initialPosition`
- [ ] Mic permission with an Arabic purpose string; denied path handled
- [ ] No autoplay-with-sound on web; compression progress shown, cancellable, cache cleared
