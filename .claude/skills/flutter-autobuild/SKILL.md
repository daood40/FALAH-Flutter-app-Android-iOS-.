---
name: flutter-autobuild
description: Build a complete, working Flutter app end to end from a single sentence — decide the stack, scaffold, implement every screen and feature, wire the backend, test, and prepare the release, without stopping to ask the user for instructions between steps. Use whenever the user asks for a whole app or a whole feature area rather than one file, or says "اصنع تطبيق", "ابني لي تطبيق", "أريد تطبيق", "أكمل التطبيق", "build me an app", "make an app", "full app", "from start to finish".
---

# Autonomous App Build

This skill governs **how you work**, not what you type. It applies the moment the user asks for an app or a whole feature area instead of a single change.

## The contract

The user gave you one sentence. They should not have to give another one until the app runs. So:

- **Ask at most one round of questions, and only for things you genuinely cannot default.** Everything else you decide from the Defaults table below and state as an assumption.
- If the user is not responding, or told you to proceed, **do not ask at all** — pick the defaults, write them down at the top of your first message, and build.
- **Never stop mid-build to ask "shall I continue?"** Continue. Finish the phase, verify it, commit, start the next.
- **Never deliver a plan instead of an app.** A plan is the first 60 seconds, not the deliverable.
- **Never leave a `TODO`, a stub screen, a fake list of hardcoded items, or a button that does nothing.** If a feature is out of scope, remove it from the UI rather than leaving it dead.
- Report at the end: what was built, what was assumed, what is left, how to run it.

## Step 0 — Write the spec file first

Before any code, create `docs/SPEC.md` in the repo containing:

1. One sentence: who the app is for and the single core action.
2. The screen list.
3. The data model (tables/collections, columns, relationships, access rules).
4. The stack decisions with a one-line reason each.
5. The phase plan (below) as a checklist.

This file is your memory. Update its checklist as you complete each phase, and re-read it whenever you resume work in a later session. Without it, a long build drifts.

## Step 1 — Decide the stack (do not ask; use these defaults)

| Decision | Default unless the user said otherwise |
|---|---|
| Platforms | Android + iOS; add Web only if the user mentioned a site or dashboard |
| Language | Arabic-first with full RTL, English second, switchable at runtime |
| Backend | Supabase — unless the app is chat/offline-first with trivial queries, then Firebase; unless the user named one |
| Auth | Email + password, plus phone OTP if the app is consumer-facing in an Arab market |
| State | Riverpod |
| Routing | go_router with `StatefulShellRoute` if there is a bottom nav |
| Models | freezed + json_serializable |
| Networking | Supabase client directly, or dio if there is a custom API |
| Local storage | shared_preferences for settings; drift only if the app must work offline |
| Theme | Material 3, `ColorScheme.fromSeed`, light + dark |
| Font | Cairo or Tajawal, bundled |
| Structure | feature-first: `lib/features/<name>/{data,domain,presentation}` |
| CI | GitHub Actions running `analyze` + `test` on push |
| Error reporting | Sentry, added in the hardening phase |

Only ask the user when the answer changes the whole product and cannot be guessed: does money change hands and how; is there a role system (admin/user); must it work with no internet. Ask those **together, once**, at the start.

## Step 2 — Execute the phases in order

Do not start a phase before the previous one passes its gate. Do not skip a gate because it is "obviously fine".

**Phase 1 — Skeleton**
Scaffold, folder structure, `analysis_options.yaml`, theme (light + dark), localization wired with real ARB files, router with the real screen list as placeholders, env config, `.gitignore`, CI workflow.
*Gate:* `flutter analyze` clean, `flutter build apk --debug` succeeds, the app launches and the language switch flips direction.

**Phase 2 — Data layer & auth**
Schema written and applied (SQL migration file committed for Supabase; rules file for Firebase). **Security rules / RLS policies written in the same commit as the tables — never later.** Models, repositories, typed failures. Sign up, sign in, sign out, session persistence, auth-guarded routing, profile row created by trigger.
*Gate:* you can register, kill the app, reopen it and still be signed in; a signed-out client can read nothing it shouldn't.

**Phase 3 — Core feature**
The one thing the app exists to do, end to end: list → detail → create → edit → delete. Every screen handles loading, empty, error and data. Pagination on every list. All strings localized.
*Gate:* the core loop works against the real backend, and every error path shows an Arabic message, not an exception.

**Phase 4 — Supporting features**
One at a time, each finished before the next starts: search/filter, notifications, uploads, maps, AI, chat, payments — whatever the spec listed. A feature is "finished" when it has its four states, its errors handled, and its happy path tested.

**Phase 5 — Polish**
Page transitions, list entrance animation, skeleton loaders, empty-state illustrations, haptics, pull-to-refresh, accessibility pass (48px targets, semantics labels, 1.3× text scale), full RTL walkthrough, full dark-mode walkthrough.

**Phase 6 — Hardening**
Security review (no secrets in the client, every rule enforced server-side), performance profile, crash reporting, offline behaviour, forced-update / kill switch, error message audit.

**Phase 7 — Release prep**
App icon and splash, obfuscated release build, signing config documented, store listing text in Arabic and English, screenshots checklist, privacy policy draft, CI release workflow.

## Step 3 — Verify continuously, not at the end

After every meaningful change:

```bash
flutter analyze
flutter test
```

After every phase:

```bash
dart format --set-exit-if-changed .
flutter analyze --fatal-infos
flutter test
flutter build apk --debug
git add -A && git commit -m "<phase>: <what changed and why>"
```

If `analyze` or `test` fails, **fix it before doing anything else.** Never commit a build that does not compile. Never say a phase is done while a test is red.

When you cannot run a build in this environment, say so explicitly in the final report and list the exact commands the user must run — do not silently claim it builds.

## Step 4 — Report

End the whole build with, in this order:

1. What the app does now, in two sentences.
2. The assumptions you made (the Defaults table entries you applied).
3. What you did not build and why.
4. Exactly how to run it (`flutter pub get`, env values needed, migration to apply).
5. The single next thing worth doing.

## Non-negotiable rules for every line you write

- Every user-facing string comes from the localization file. No Dart string literals in the UI.
- Every screen handles loading, empty, error, data.
- Every list is paginated and keyed.
- Every controller, subscription, timer and focus node is disposed.
- Every `await` in a widget is followed by a `mounted` check before touching state or context.
- Every layout uses `EdgeInsetsDirectional` / `AlignmentDirectional`, never `left`/`right`.
- Every colour and text style comes from the theme.
- No secret in the client. Every authorization rule enforced server-side.
- No `print`. Use a logger, and never log tokens or personal data.
- Commit small, with a message that says why.

## When the user comes back later

Read `docs/SPEC.md` first, find the first unchecked phase, and continue from there without asking what to do. Re-verify the previous phase's gate before building on it.

## Which skill to open for each phase

Consult the classified index in `flutter-app-blueprint` and open the specific skill for the step you are on. Open it **before** writing that part, not after.
