---
name: flutter-app-blueprint
description: The classified index and ordered build plan for every Flutter skill in this package — which skill to open at which phase, ordered recipes per app type, and the decisions to settle before writing code. Use at the start of any Flutter work to route to the right skill, or when the user says "من أين أبدأ", "خطة", "ترتيب", "ما الخطوات", "roadmap", "plan", "where do I start".
---

# Flutter Blueprint — Index, Order, Plan

This is the map. `flutter-autobuild` is the method. Open a specific skill **before** writing that part of the app.

## The skills, classified

### Level 0 — Method
| # | Skill | Opens when |
|---|---|---|
| 0.1 | `flutter-autobuild` | The user asks for a whole app or feature area; governs how you work end to end |
| 0.2 | `flutter-app-blueprint` | You need to know which skill comes next (this file) |

### Level 1 — Foundation (always, first)
| # | Skill | Opens when |
|---|---|---|
| 1.1 | `flutter-project-setup` | Scaffolding, folders, packages, flavors, env, icons, splash |
| 1.2 | `flutter-code-quality` | Lints, naming, null safety, sealed classes, error conventions, review |

### Level 2 — Interface
| # | Skill | Opens when |
|---|---|---|
| 2.1 | `flutter-ui-design` | Any screen, theme, Material 3, dark mode, responsive layout |
| 2.2 | `flutter-navigation` | Routing, tabs, auth guards, deep links |
| 2.3 | `flutter-forms-validation` | Login, signup, any data entry, validators |
| 2.4 | `flutter-animations` | Transitions, motion, CustomPainter |
| 2.5 | `flutter-charts` | Graphs, statistics, dashboards, KPI tiles |

### Level 3 — Data & backend
| # | Skill | Opens when |
|---|---|---|
| 3.1 | `flutter-state-management` | Riverpod/Bloc, async state, controllers |
| 3.2 | `flutter-supabase` | Supabase auth, queries, RLS, realtime, storage |
| 3.3 | `flutter-firebase` | Firebase auth, Firestore, rules, Crashlytics, Remote Config |
| 3.4 | `flutter-networking-api` | Custom REST API, dio, interceptors, JSON models |
| 3.5 | `flutter-local-database` | Offline-first, caching, drift/sqflite/Hive, sync |

### Level 4 — Features
| # | Skill | Opens when |
|---|---|---|
| 4.1 | `flutter-arabic-rtl` | Arabic, RTL, i18n, fonts, plurals, dates — open in phase 1, not at the end |
| 4.2 | `flutter-search-filter` | Search, filters, sorting, Arabic text normalization |
| 4.3 | `flutter-device-features` | Camera, files, location, maps, QR, permissions |
| 4.4 | `flutter-notifications` | Push, local notifications, reminders |
| 4.5 | `flutter-ai-integration` | LLM features, chatbot, RAG, on-device ML |
| 4.6 | `flutter-chat-realtime` | User-to-user chat, live feeds, presence |
| 4.7 | `flutter-media` | Video and audio playback, recording, background audio |
| 4.8 | `flutter-documents` | PDF generation and viewing, Excel/CSV export, printing |
| 4.9 | `flutter-background-tasks` | Periodic sync, foreground services, lifecycle handling |

### Level 5 — Business
| # | Skill | Opens when |
|---|---|---|
| 5.1 | `flutter-monetization` | Subscriptions, in-app purchase, ads, store payment policy |
| 5.2 | `flutter-payments` | Payment gateways for physical goods and real-world services |
| 5.3 | `flutter-analytics` | Event tracking, funnels, retention, consent |

### Level 6 — Quality
| # | Skill | Opens when |
|---|---|---|
| 6.1 | `flutter-security` | Secrets, tokens, obfuscation, biometrics, pre-release review |
| 6.2 | `flutter-performance` | Jank, rebuilds, memory, image cost, app size |
| 6.3 | `flutter-testing` | Unit, widget, integration, golden tests, CI |
| 6.4 | `flutter-debugging` | Any error, crash, or failed build |

### Level 7 — Ship
| # | Skill | Opens when |
|---|---|---|
| 7.1 | `flutter-build-release` | Signing, App Bundle, stores, CI/CD |
| 7.2 | `flutter-web-deploy` | Flutter Web, hosting, PWA |
| 7.3 | `flutter-desktop` | Windows, macOS, Linux builds |
| 7.4 | `flutter-package-authoring` | Extracting reusable code into a package |

## Decide these before the first line of code

1. **The one core action.** One sentence. Everything else is secondary.
2. **Platforms** — mobile only, or mobile + web.
3. **Backend** — Supabase (relational, reporting, SQL) vs Firebase (NoSQL, offline-first chat/feed) vs custom API. This shapes every layer; decide now.
4. **Auth** — email, phone OTP, OAuth, anonymous.
5. **Roles** — is there an admin? Write the access rules before the tables.
6. **Offline** — required or not. Retrofitting offline is a rewrite.
7. **Money** — free, subscription, one-time, ads, or real-world payments. Store policy changes the design.
8. **Language** — Arabic-first is the default here; set it up in phase 1.

## Phase order (the same phases `flutter-autobuild` executes)

| Phase | Work | Skills | Gate |
|---|---|---|---|
| 1. Skeleton | Scaffold, theme, i18n, router, CI | 1.1, 1.2, 2.1, 2.2, 4.1 | Runs; language switch flips direction; analyze clean |
| 2. Data & auth | Schema + rules, models, repos, login | 3.1, 3.2 or 3.3 or 3.4, 1.2 | Session persists; signed-out client reads nothing |
| 3. Core feature | List/detail/create/edit/delete, 4 states | 2.1, 2.3, 3.1, 3.2 | Core loop works on real backend |
| 4. Features | One at a time, each finished | Level 4 as needed | Each has 4 states + errors + a test |
| 5. Polish | Motion, skeletons, a11y, RTL & dark pass | 2.4, 2.1, 4.1 | Walkthrough in both languages and themes |
| 6. Hardening | Security, perf, crash reporting, offline | 6.1, 6.2, 6.3, 3.5 | No secrets client-side; no red tests |
| 7. Ship | Icons, signing, listing, CI release | 7.1, 7.2 | Release build installs and runs on a real device |

## Recipes by app type

Open these in this order after phase 1.

**Reporting / incident platform (بلاغات)** → 3.2 Supabase (RLS by role) → 2.3 forms → 4.3 camera + location + maps → 2.5 charts for the admin dashboard → 4.4 notifications on status change → 4.8 PDF export → 6.1 security.

**Quiz / competition app (مسابقات)** → 3.2 backend + schema for questions, attempts, scores → 3.1 timer and answer state → 2.4 animations for feedback → 2.5 charts for the leaderboard → 4.4 notifications for a new round → 5.1 monetization (check prize/contest policy before building) → 4.9 if rounds run on a schedule.

**Tasks / habits tracker (مهام وعادات)** → 3.5 local database first (must work offline) → 3.1 state → 4.4 local scheduled reminders → 2.5 streak charts → 3.2 optional cloud sync → 5.1 subscription for premium.

**Content / Islamic content platform** → 3.2 backend + storage → 4.7 audio playback with background + resume → 4.2 search with Arabic normalization → 3.5 offline downloads → 4.8 sharing and export → 5.3 analytics.

**Chat / community app** → 3.3 Firebase or 3.2 Supabase realtime → 4.6 chat → 4.4 push with deep-link routing → 4.3 attachments → 6.1 moderation and blocking.

**Store / marketplace** → 3.2 backend + inventory schema → 4.2 search and filters → 5.2 payment gateway + cash on delivery → 4.4 order-status notifications → 4.8 invoice PDF → 5.3 analytics.

**AI assistant app** → 4.5 AI integration (server proxy first) → 4.6 chat UI patterns → 3.2 for history and quotas → 5.1 subscription to cover model cost → 6.1 security.

**Dashboard / internal tool** → 7.2 web deploy → 2.1 responsive with a NavigationRail → 2.5 charts → 3.2 backend with role-based RLS → 4.8 export.

## Working rules

- One feature at a time, finished. Half-built features across five screens is how apps die.
- Four states on every screen: loading, empty, error, data.
- Localize from the first commit.
- The server enforces every rule; client checks are UX only.
- `flutter analyze` and `flutter test` clean before every commit.
- Test on a real, cheap Android device — not only the emulator.
