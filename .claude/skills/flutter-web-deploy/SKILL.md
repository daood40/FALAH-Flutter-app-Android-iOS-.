---
name: flutter-web-deploy
description: Build and deploy Flutter Web — renderer choice, base href, routing and 404 handling, PWA and service worker, SEO limits, and deploying to GitHub Pages, Netlify, Vercel, Firebase Hosting or Supabase. Use for any web build or hosting question, or when the user says "موقع", "ويب", "نشر على الويب", "flutter web", "github pages", "PWA".
---

# Flutter Web & Deployment

## Is Flutter Web the right choice?

Good for: dashboards, internal tools, app companions, anything behind a login.
Poor for: content sites that need SEO, landing pages, blogs. Flutter Web renders to canvas — crawlers see very little, and the initial download is 1.5–3 MB. For a marketing site, write HTML.

## Build

```bash
flutter build web --release --dart-define-from-file=env/prod.json
# output: build/web/
```

Renderer (flag names vary by Flutter version — check `flutter build web --help`):

- **CanvasKit / skwasm** — pixel-identical to mobile, better for graphics; larger download.
- **HTML / auto** — smaller and faster to load; some rendering differences.

For a mostly-text app prefer the lighter option; for a chart/animation-heavy app use CanvasKit.

## base href — the #1 deployment bug

`web/index.html` contains `<base href="$FLUTTER_BASE_HREF">`.

- Root domain (`example.com`) → `--base-href=/`
- Subpath (`user.github.io/quiz/`) → `--base-href=/quiz/`

```bash
flutter build web --release --base-href=/quiz/
```

A blank white page after deploying is almost always a wrong `base href` — open the browser console and look for 404s on `main.dart.js` or `flutter_bootstrap.js`.

## Routing / 404 rewrite

go_router gives real URLs (`/report/42`). The host must serve `index.html` for **any** path, or a refresh on a deep URL 404s.

| Host | How |
|---|---|
| Netlify | `_redirects` file: `/*  /index.html  200` |
| Vercel | `vercel.json`: `{"rewrites":[{"source":"/(.*)","destination":"/index.html"}]}` |
| Firebase | `firebase.json`: `"rewrites":[{"source":"**","destination":"/index.html"}]` |
| GitHub Pages | No rewrite support — copy `index.html` to `404.html` |
| Nginx | `try_files $uri $uri/ /index.html;` |

Optionally remove the `#` from URLs: `usePathUrlStrategy()` from `flutter_web_plugins` in `main()` (requires the rewrite above).

## GitHub Pages (works entirely from a phone)

`.github/workflows/deploy-web.yml`:

```yaml
name: deploy-web
on:
  push:
    branches: [main]
permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
        with: { channel: stable, cache: true }
      - run: flutter pub get
      - run: flutter build web --release --base-href=/${{ github.event.repository.name }}/
      - run: cp build/web/index.html build/web/404.html
      - uses: actions/upload-pages-artifact@v3
        with: { path: build/web }

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

Then Settings → Pages → Source = **GitHub Actions**. Every push to `main` redeploys — no local machine needed.

Secrets for the build go in repository secrets and are written to `env/prod.json` in the workflow. Remember anything in a web build is public — see `flutter-security`.

## Other hosts

```bash
# Firebase
firebase init hosting        # public dir: build/web, single-page app: yes
firebase deploy --only hosting

# Netlify
netlify deploy --prod --dir=build/web

# Vercel
vercel --prod build/web
```

## PWA / installable

`web/manifest.json`: set `name`, `short_name`, `theme_color`, `background_color`, `display: "standalone"`, `start_url`, and 192/512 icons (plus a `maskable` one).

Flutter registers a service worker automatically. The consequence: **users get a cached old version**. Prompt for reload on update:

```dart
// simplest reliable approach: version the deploy and check it
final live = await http.get(Uri.parse('/version.json'));
if (jsonDecode(live.body)['build'] != Env.buildNumber) showUpdateBanner();
```

Set `Cache-Control: no-cache` on `index.html` and `flutter_service_worker.js`, and long immutable caching on hashed assets. Mismatched caching is why "I deployed but I still see the old site".

## Web-specific code

```dart
import 'package:flutter/foundation.dart' show kIsWeb;

if (kIsWeb) { /* ... */ }
```

`dart:io` is unavailable on web — `File`, `Platform`, `Directory` will not compile. Guard with `kIsWeb` and use conditional imports for platform-specific implementations. Check pub.dev's platform badges before adding a package.

## Making it feel like a website, not a phone app

- Constrain content width on large screens (`maxWidth: 1100`) and centre it.
- `NavigationRail` / top nav bar instead of a bottom bar on desktop widths.
- Support keyboard: focus traversal, Enter to submit, Esc to close dialogs.
- Show real hover states (`MouseRegion`, `InkWell` hover colors) and a `SelectionArea` so text can be selected and copied.
- Set `<title>` and favicon in `index.html`, and add Open Graph meta tags for link previews (these are read from the raw HTML, so they work even though the app is canvas-rendered).

## SEO reality

Flutter Web is a single-page canvas app. You can add meta tags and a static `index.html` description, but content inside the app is largely invisible to search engines. If organic search matters, build the public pages as plain HTML and link into the Flutter app for the authenticated part.

Still do: `robots.txt`, a `sitemap.xml` for whatever static pages exist, and Open Graph tags.

## Checklist

- [ ] Correct `--base-href`
- [ ] SPA rewrite / `404.html` in place
- [ ] Tested on Chrome, Safari and a mobile browser
- [ ] Caching headers set; update prompt works
- [ ] No secrets in the build (web ships them in plain text)
- [ ] Responsive at 360 px, 768 px and 1440 px
- [ ] RTL verified in the browser
