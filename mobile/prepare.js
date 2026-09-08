/* يجهّز www/ للقشرة الأصلية: نسخة الواجهة والخطوط والأيقونات وعامل الخدمة،
   مع تحويل نداءات الواجهة إلى خادم فلاح المنشور بدل المسارات النسبية.

     node prepare.js                 # يقرأ FALAH_API أو يستعمل النطاق الافتراضي

   القاعدة: لا يُنسخ نصٌّ شرعيٌّ إلى القشرة. النصوص تبقى في الخادم حيث
   يجري الفحص، فلا تُشحن نسخةٌ قد تشيخ في جهاز المستخدم. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const WWW  = path.join(__dirname, "www");
const API  = process.env.FALAH_API || "https://app.falah.example";

function copy(src, dst) {
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(src, dst);
}

function copyDir(src, dst, filter) {
  if (!fs.existsSync(src)) return 0;
  let n = 0;
  for (const f of fs.readdirSync(src)) {
    if (filter && !filter(f)) continue;
    copy(path.join(src, f), path.join(dst, f));
    n++;
  }
  return n;
}

fs.rmSync(WWW, { recursive: true, force: true });
fs.mkdirSync(WWW, { recursive: true });

// ١ · الواجهة: المسارات النسبية تصير مطلقةً إلى الخادم المنشور
let ui = fs.readFileSync(path.join(ROOT, "falah-app.html"), "utf8");
ui = ui
  .replace(/fetch\("\//g, `fetch("${API}/`)
  .replace(/api\("\//g, `api("${API}/`)
  .replace(/url\(\/fonts\//g, "url(fonts/")
  .replace(/href="\/icons\//g, 'href="icons/')
  .replace(/href="\/manifest\.webmanifest"/g, 'href="manifest.webmanifest"')
  .replace(/register\("\/sw\.js"\)/g, 'register("sw.js")');
// الجلسة داخل القشرة تُرسل مع الطلبات عبر النطاقات
ui = ui.replace(/credentials:\s*"same-origin"/g, 'credentials: "include"');
if (!/credentials:/.test(ui)) {
  ui = ui.replace(/const o = body \?/, 'const o = body ?');   // الواجهة تضبطها بنفسها
}
fs.writeFileSync(path.join(WWW, "index.html"), ui);

// ٢ · القشرة الساكنة
copy(path.join(ROOT, "manifest.webmanifest"), path.join(WWW, "manifest.webmanifest"));
copy(path.join(ROOT, "sw.js"), path.join(WWW, "sw.js"));
const nf = copyDir(path.join(ROOT, "fonts"), path.join(WWW, "fonts"),
                   f => /\.(ttf|woff2)$/.test(f));
const ni = copyDir(path.join(ROOT, "icons"), path.join(WWW, "icons"),
                   f => f.endsWith(".png"));

// ٣ · صفحة الانقطاع: تُعرض حين لا شبكة ولا نسخة
fs.writeFileSync(path.join(WWW, "offline.html"), `<!doctype html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>فَلاح — بلا اتصال</title>
<style>body{margin:0;display:grid;place-items:center;min-height:100dvh;background:#070D0B;
color:#F1E7CE;font-family:system-ui,sans-serif;text-align:center;padding:24px;line-height:1.9}
h1{font-size:22px;margin-bottom:8px}p{color:#9C8C62;max-width:34ch}</style></head>
<body><div><h1>لا اتصال</h1>
<p>فلاح لا يعرض نصًّا شرعيًّا من نسخةٍ لم تُفحص. أعد الاتصال ليُقرأ النصّ من مصدره.</p>
</div></body></html>`);

console.log(`www جاهزة: الواجهة + البيان + عامل الخدمة + ${nf} خطًّا + ${ni} أيقونة`);
console.log(`الخادم: ${API}`);
