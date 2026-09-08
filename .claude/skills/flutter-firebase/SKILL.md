---
name: flutter-firebase
description: Firebase in Flutter — Auth, Firestore data modelling and security rules, Cloud Storage, Cloud Functions, Analytics, Crashlytics and Remote Config, plus how it compares to Supabase. Use for any Firebase backend work, or when the user says "فايربيس", "فايرستور", "firebase", "firestore", "crashlytics", "analytics".
---

# Firebase with Flutter

## Setup

```bash
dart pub global activate flutterfire_cli
flutterfire configure
flutter pub add firebase_core firebase_auth cloud_firestore firebase_storage
```

```dart
await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
```

`google-services.json` / `GoogleService-Info.plist` and `firebase_options.dart` contain public client config — they are not secrets, but keep them out of public repos anyway and lock access down with **Security Rules**, which is the real protection.

## Firebase or Supabase?

| | Firebase | Supabase |
|---|---|---|
| Database | Firestore (NoSQL documents) | Postgres (SQL, joins, constraints) |
| Auth | Very mature, many providers | Solid, RLS-integrated |
| Queries | Limited — no joins, no OR across fields, no aggregation without extensions | Full SQL |
| Offline | Excellent, built-in | Build it yourself |
| Cost model | Per document read — a bad query is expensive | Per row/storage, more predictable |
| Self-host | No | Yes |

Rough rule: relational or reporting data → Supabase; offline-first chat/feed apps with simple access patterns → Firebase. Do not use both for the same data.

## Auth

```dart
final auth = FirebaseAuth.instance;

await auth.createUserWithEmailAndPassword(email: e, password: p);
await auth.signInWithEmailAndPassword(email: e, password: p);
await auth.signOut();

auth.authStateChanges().listen((user) { /* null = signed out */ });
```

Phone auth (widely used in Arabic markets):

```dart
await auth.verifyPhoneNumber(
  phoneNumber: '+218912345678',
  verificationCompleted: (cred) => auth.signInWithCredential(cred), // Android auto-retrieval
  verificationFailed: (e) => _show(e.message),
  codeSent: (verificationId, resendToken) => _goToOtpScreen(verificationId),
  codeAutoRetrievalTimeout: (_) {},
);

await auth.signInWithCredential(
  PhoneAuthProvider.credential(verificationId: id, smsCode: code));
```

Add SHA-1 and SHA-256 fingerprints to the Firebase console or phone auth and Google sign-in fail silently on release builds. Map `FirebaseAuthException.code` (`weak-password`, `email-already-in-use`, `invalid-verification-code`, `too-many-requests`) to localized messages.

## Firestore modelling

Design around the queries you will run, not around normalization.

```dart
final db = FirebaseFirestore.instance;

await db.collection('reports').add({
  'title': title,
  'userId': uid,
  'authorName': displayName,          // denormalized on purpose — avoids a second read
  'status': 'open',
  'createdAt': FieldValue.serverTimestamp(),
});

final q = db.collection('reports')
    .where('status', isEqualTo: 'open')
    .orderBy('createdAt', descending: true)
    .limit(20);

final snap = await q.get();
final more = await q.startAfterDocument(snap.docs.last).get();   // pagination

// live
Stream<List<Report>> watch() => q.snapshots().map(
    (s) => s.docs.map((d) => Report.fromJson({...d.data(), 'id': d.id})).toList());
```

Rules that keep the bill down and the app fast:
- **You are billed per document read.** Always `.limit()`. A screen that reads a whole collection is a bill and a bug.
- Denormalize the few fields a list needs instead of N follow-up reads.
- Store counters with `FieldValue.increment(1)`, not by reading and writing.
- Composite queries need a composite index — Firestore's error message contains a link that creates it; follow it.
- Use `FieldValue.serverTimestamp()`, never the device clock.
- Batch up to 500 writes with `db.batch()`; use `runTransaction` when a write depends on a current value.
- Sub-collections for unbounded children (`reports/{id}/comments`), arrays only for small bounded lists.

Offline is on by default on mobile. `snapshot.metadata.isFromCache` tells you the data is local; surface that in the UI.

## Security rules — write them before launch

Default test-mode rules expire and are wide open. Anyone with your public config can read everything.

```js
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    function signedIn() { return request.auth != null; }
    function isOwner(uid) { return signedIn() && request.auth.uid == uid; }

    match /reports/{id} {
      allow read: if signedIn();
      allow create: if isOwner(request.resource.data.userId)
                    && request.resource.data.title is string
                    && request.resource.data.title.size() <= 200;
      allow update, delete: if isOwner(resource.data.userId);
    }

    match /users/{uid} {
      allow read: if signedIn();
      allow write: if isOwner(uid);
    }
  }
}
```

`resource.data` is the existing document; `request.resource.data` is the incoming one. Validate types and sizes in rules — the client cannot be trusted. Test with the Rules Playground and the local emulator (`firebase emulators:start`).

## Storage

```dart
final ref = FirebaseStorage.instance.ref('avatars/$uid.jpg');
final task = ref.putFile(file, SettableMetadata(contentType: 'image/jpeg'));
task.snapshotEvents.listen((s) => onProgress(s.bytesTransferred / s.totalBytes));
final url = await (await task).ref.getDownloadURL();
```

```js
match /avatars/{uid} {
  allow read: if request.auth != null;
  allow write: if request.auth.uid == uid
               && request.resource.size < 5 * 1024 * 1024
               && request.resource.contentType.matches('image/.*');
}
```

## Cloud Functions

For anything needing a secret, a third-party API, or logic the client must not control.

```ts
export const onReportCreated = onDocumentCreated('reports/{id}', async (event) => {
  const data = event.data?.data();
  await sendPushToAdmins(data);
});

export const redeemCode = onCall({ enforceAppCheck: true }, async (req) => {
  if (!req.auth) throw new HttpsError('unauthenticated', 'login required');
  // validate and write with admin privileges
});
```

```dart
final res = await FirebaseFunctions.instanceFor(region: 'europe-west1')
    .httpsCallable('redeemCode').call({'code': code});
```

Match the region in the client or the call 404s. Callable functions require the Blaze (pay-as-you-go) plan.

## Analytics, Crashlytics, Remote Config

```dart
await FirebaseAnalytics.instance.logEvent(
  name: 'report_created', parameters: {'category': category});

FlutterError.onError = FirebaseCrashlytics.instance.recordFlutterFatalError;
PlatformDispatcher.instance.onError = (e, s) {
  FirebaseCrashlytics.instance.recordError(e, s, fatal: true);
  return true;
};

final rc = FirebaseRemoteConfig.instance;
await rc.setDefaults({'maintenance_mode': false, 'min_version': '1.0.0'});
await rc.fetchAndActivate();
```

Remote Config is how you ship a kill switch, a forced-update gate, and feature flags without a store release — set both up before launch, not after you need them.

Upload dSYM/symbols so Crashlytics traces are readable, and verify with a deliberate test crash before release.

## App Check

`firebase_app_check` proves requests come from your genuine app, blocking scripted abuse of your Firestore and Functions. Enable it (Play Integrity / DeviceCheck) before any public launch.

## Checklist

- [ ] Security rules written, tested in the emulator, not left in test mode
- [ ] Every query limited and indexed
- [ ] Reads minimized by denormalizing list fields
- [ ] Server timestamps used
- [ ] SHA fingerprints registered for release builds
- [ ] Crashlytics + Remote Config kill switch live
- [ ] App Check enabled
- [ ] Budget alerts set in Google Cloud billing
