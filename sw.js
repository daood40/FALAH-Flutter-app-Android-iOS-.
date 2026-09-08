/* عامل خدمة فلاح — يجعل التطبيق يفتح بلا شبكة، ولا يُخزّن شيئًا من الحساب.

   القاعدة: ما كان قشرةً (صفحة، خط، أيقونة) يُخزَّن ويُقدَّم من المخزن أولًا،
   وما كان نصًّا شرعيًّا يُطلب من الشبكة أولًا ويُخزَّن نسخةً للطوارئ —
   فلا يُعرض متنٌ قديم ما دامت الشبكة تعطي الأحدث. وما كان حسابًا أو
   مشروعًا فلا يُخزَّن أبدًا. */

const V = "falah-v3";
const SHELL = `${V}-shell`;
const TEXTS = `${V}-texts`;

const SHELL_FILES = [
  "/", "/manifest.webmanifest",
  "/fonts/Amiri-Regular.ttf", "/fonts/Amiri-Bold.ttf", "/fonts/AmiriQuran.ttf",
  "/icons/icon-192.png", "/icons/icon-512.png", "/icons/maskable-512.png",
];

// النصوص الشرعية: تُقرأ ولا تتغيّر، فيصحّ تخزينها نسخةً للطوارئ
const TEXT_PATHS = ["/options", "/chapters", "/chapter/hadiths",
                    "/quran/ayah", "/hadith", "/card", "/template", "/templates"];
// الحساب والمشاريع والتصدير: لا يُخزَّن منها شيء
const NEVER = ["/app/"];

self.addEventListener("install", e => {
  e.waitUntil((async () => {
    const c = await caches.open(SHELL);
    await Promise.allSettled(SHELL_FILES.map(f => c.add(new Request(f, {cache: "reload"}))));
    self.skipWaiting();
  })());
});

self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => !k.startsWith(V)).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

const isText = p => TEXT_PATHS.some(x => p === x || p.startsWith(x + "?") || p.startsWith(x + "/"));
const isNever = p => NEVER.some(x => p.startsWith(x));

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;                       // الكتابة لا تُعترض
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;        // لا نعترض غير نطاقنا
  if (isNever(url.pathname)) return;                      // الحساب يمرّ إلى الشبكة وحدها

  // الصفحة نفسها: من الشبكة إن أمكن، ومن المخزن إن انقطعت
  if (req.mode === "navigate") {
    e.respondWith((async () => {
      try {
        const net = await fetch(req);
        const c = await caches.open(SHELL); c.put("/", net.clone());
        return net;
      } catch {
        return (await caches.match("/")) || Response.error();
      }
    })());
    return;
  }

  if (isText(url.pathname)) {
    // الشبكة أولًا: لا يُعرض نصٌّ من مخزنٍ قديم ما دام الأحدث متاحًا
    e.respondWith((async () => {
      try {
        const net = await fetch(req);
        if (net.ok) { const c = await caches.open(TEXTS); c.put(req, net.clone()); }
        return net;
      } catch {
        const hit = await caches.match(req);
        if (hit) {
          const h = new Headers(hit.headers);
          h.set("X-FALAH-Offline", "1");     // الواجهة تُخبر المستخدم أنّه بلا اتصال
          return new Response(await hit.blob(), {status: hit.status, headers: h});
        }
        return new Response(JSON.stringify({error: "لا اتصال، ولا نسخة محفوظة لهذا الطلب"}),
                            {status: 503, headers: {"Content-Type": "application/json; charset=utf-8"}});
      }
    })());
    return;
  }

  // القشرة: من المخزن أولًا لأنها لا تتغيّر إلا بإصدارٍ جديد
  e.respondWith((async () => {
    const hit = await caches.match(req);
    if (hit) return hit;
    try {
      const net = await fetch(req);
      if (net.ok && (url.pathname.startsWith("/fonts/") || url.pathname.startsWith("/icons/"))) {
        const c = await caches.open(SHELL); c.put(req, net.clone());
      }
      return net;
    } catch {
      return Response.error();
    }
  })());
});

// عند تسجيل الخروج تُمحى نسخ النصوص كذلك، فلا يبقى للجهاز أثرٌ من الجلسة
self.addEventListener("message", e => {
  if (e.data === "falah:purge") caches.delete(TEXTS);
});
