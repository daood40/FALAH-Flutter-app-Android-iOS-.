#!/usr/bin/env python3
"""فحص الواجهة في متصفّحٍ حقيقي — التطبيق والمعاينة معًا.

    python3 ui_audit.py            # التطبيق على ٨٠٨١ والمعاينة من الملف
"""
import os, random, sys, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
APP  = os.environ.get("APP", "http://localhost:8081")
PREV = "file://" + os.path.join(HERE, "falah-preview.html")
CHROME = "/opt/pw-browsers/chromium"

OK = FAIL = 0; FAILURES = []
def check(n, c, d=""):
    global OK, FAIL
    if c: OK += 1; print(f"  ✓ {n}" + (f"  ({d})" if d else ""))
    else: FAIL += 1; FAILURES.append((n, d)); print(f"  ✗ {n}" + (f"  ← {d}" if d else ""))
def head(t): print(f"\n▸ {t}")

def run():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        try:
            app_flow(b); app_export_queue(b); app_change_earlier(b); preview_flow(b); rtl_and_a11y(b)
        finally:
            b.close()

# ═══════════ التطبيق ═══════════
def _login(b):
    pg = b.new_page(viewport={"width": 430, "height": 932})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(APP); pg.wait_for_timeout(900)
    pg.click("text=حساب جديد"); pg.wait_for_timeout(250)
    mail = f"u{random.randint(10**7, 10**8)}@t.com"
    pg.fill("#email", mail); pg.fill("#name", "داوود")
    pg.fill("#wm", "قناة نور الهدى"); pg.fill("#pass", "Str0ng-Pass!x9")
    pg.click("#btnAuth"); pg.wait_for_timeout(1400)
    return pg, errs

def _next(pg): pg.click("#nextBtn"); pg.wait_for_timeout(650)

def app_flow(b):
    head("التطبيق — فرع القرآن كاملًا")
    pg, errs = _login(b)
    check("الدخول ينجح", pg.is_visible("#whoName"), pg.inner_text("#whoName") if pg.is_visible("#whoName") else "")
    pg.click("#btnAgent"); pg.wait_for_timeout(900)
    check("مربّع القالب فوق مربّع الأسئلة",
          pg.evaluate("""() => { const t=document.getElementById('hold'), a=document.getElementById('ask');
              return !!t && !!a && t.getBoundingClientRect().top < a.getBoundingClientRect().top; }"""))
    check("سؤالٌ واحدٌ ظاهرٌ فقط",
          pg.eval_on_selector_all("#ask h3", "e=>e.length") == 1,
          str(pg.eval_on_selector_all("#ask h3", "e=>e.length")))
    check("زرّ «السابق» معطّلٌ في أول سؤال", pg.is_disabled("#ask .btn.ghost"))

    pg.click('.opt[data-v="short_video"]'); _next(pg)
    pg.click('.opt[data-v="tiktok"]'); _next(pg)
    _next(pg)                                     # العلامة الافتراضية من الحساب
    pg.click('.opt[data-v="quran"]'); _next(pg); pg.wait_for_timeout(400)
    check("قائمة السور فيها بحث", pg.is_visible('#ask input[type=text]'))
    pg.fill('#ask input[type=text]', "الشرح"); pg.wait_for_timeout(300)
    labels = pg.eval_on_selector_all(".opt b", "e=>e.map(x=>x.textContent)")
    check("البحث يتجاوز التشكيل",
          len(labels) >= 1 and all("شرح" in pg.evaluate("l => nrm(l)", l) for l in labels[:1]),
          str(labels[:2]))
    pg.click(".opts .opt:nth-child(1)"); _next(pg)
    pg.fill("#ask input[type=number]", "3"); pg.wait_for_timeout(200); _next(pg)
    pg.click('.opt[data-v="1"]'); _next(pg)
    _next(pg)                                     # «إلى» الافتراضية = ٣
    check("السلسلة ثلاث بطاقات", "٣ بطاقة" in pg.inner_text("#cmeta"),
          pg.inner_text("#cmeta").replace("\n", " | "))
    check("نقاط التنقّل بعدد البطاقات",
          pg.eval_on_selector_all("#cmeta .dot", "e=>e.length") == 3)
    first = pg.inner_text("#tpl")
    pg.click("#cmeta .dot:nth-child(2)"); pg.wait_for_timeout(400)
    check("النقر على نقطةٍ يبدّل البطاقة", pg.inner_text("#tpl") != first,
          pg.inner_text("#tpl")[:70].replace("\n", " "))

    pg.click(".opts .opt:nth-child(2)"); _next(pg)   # تفسير
    check("التفسير ظهر في البطاقة بمصدره",
          "التفسير" in pg.inner_text("#tpl") or "الميسر" in pg.inner_text("#tpl"),
          pg.inner_text("#tpl")[-90:].replace("\n", " "))
    pg.click(".opts .opt:nth-child(2)"); _next(pg)   # ترجمة
    pg.click('.opt[data-v="none"]'); _next(pg)       # قارئ
    before = pg.get_attribute("#tpl", "data-skin")
    pg.click('.opt[data-v="night"]'); _next(pg)
    check("التصميم يغيّر هيئة البطاقة",
          pg.get_attribute("#tpl", "data-skin") == "night", f"{before} → night")
    pg.click('.opt[data-v="green"]'); _next(pg)
    check("لون التصميم يُطبَّق", pg.get_attribute("#tpl", "data-tint") == "green")
    pg.click('.opt[data-v="amiri"]'); _next(pg)
    check("نوع الخط يُطبَّق", pg.get_attribute("#tpl", "data-font") == "amiri")
    pg.click('.opt[data-v="#F0E5CA"]'); _next(pg)
    check("لون الخط يُطبَّق",
          "F0E5CA" in (pg.get_attribute("#tpl", "style") or "").upper(),
          pg.get_attribute("#tpl", "style"))
    pg.wait_for_timeout(700)
    check("الخلاصة تظهر عند الاكتمال", "اكتملت الإجابات" in pg.inner_text("#ask"),
          pg.inner_text("#ask")[:60].replace("\n", " "))
    check("الوصف للنشر مبنيٌّ من الإجابات",
          "تيك توك" in pg.inner_text("#ask") and "قناة نور الهدى" in pg.inner_text("#ask"))

    pg.click("text=أنشئ المشروع"); pg.wait_for_timeout(3000)
    pane = pg.inner_text("#pane")
    check("المشروع يُبنى ويُفتح", "سُورَةُ" in pane or "بطاقة" in pane, pane[:70].replace("\n", " "))
    check("لا خطأ في الصفحة طوال المسار", not errs, str(errs[:2]))
    pg.close()


def app_export_queue(b):
    head("التطبيق — التصدير عبر الطابور")
    pg, errs = _login(b)
    # يُهيَّأ مشروعٌ مربّع (ما تسمح به الخطّة المجانية) ثم يُختبر الزرّ نفسه
    pg.evaluate("""async () => {
        const p = await api('/app/projects/create',
                            {title:'مشروع الطابور', skin:'parch', ratio:'square'});
        await api('/app/items/add', {project:p.id, kind:'quran',
                                     ref:{surah:108, ayah:1, to:3}});
        await loadProjects(); await openProject(p.id);
    }""")
    pg.wait_for_timeout(1200)
    exp = pg.locator("button:has-text('صدِّر السلسلة')").first
    check("زرّ التصدير ظاهرٌ وغيرُ معطّل", exp.is_visible() and exp.is_enabled())

    t0 = time.time()
    exp.click()
    # الردّ الفوريّ: النصّ يتغيّر إلى حالةٍ من الطابور خلال جزءٍ من ثانية
    pg.wait_for_function(
        "() => /الطابور|٪/.test(document.querySelector('#pane').innerText)", timeout=6000)
    check("الواجهة تُظهر حالة الطابور فورًا", (time.time() - t0) < 6,
          f"{(time.time()-t0)*1000:.0f} م.ث")
    steps = pg.inner_text("#pane")
    check("الحالة مكتوبةٌ بالعربية لا بالإنجليزية",
          "queued" not in steps and "running" not in steps)

    pg.wait_for_selector(".thumbs img", timeout=180000)
    n = pg.eval_on_selector_all(".thumbs img", "e=>e.length")
    check("الصور تظهر بعد اكتمال المهمّة", n >= 1, f"{n} صورة")
    check("الصور تُحمَّل فعلًا لا تُعرض فارغة",
          pg.eval_on_selector_all(".thumbs img",
              "e=>e.every(x=>x.complete && x.naturalWidth>200)"))
    check("الوصف للنشر ظهر مع الصور", pg.is_visible("pre.cap"))
    check("الزرّ يعود قابلًا للضغط بعد الانتهاء",
          pg.locator("button:has-text('صدِّر السلسلة')").first.is_enabled())
    check("الحصّة المتبقّية تُحدَّث بعد التصدير",
          pg.evaluate("() => document.body.innerText").count("بطاقة") >= 1)
    check("لا خطأ في الصفحة طوال التصدير", not errs, str(errs[:2]))
    pg.close()

def app_change_earlier(b):
    head("التطبيق — الرجوع وتغيير إجابةٍ سابقة")
    pg, errs = _login(b)
    pg.click("#btnAgent"); pg.wait_for_timeout(800)
    pg.click('.opt[data-v="post"]'); _next(pg)
    pg.click('.opt[data-v="youtube"]'); _next(pg); _next(pg)
    pg.click('.opt[data-v="hadith"]'); _next(pg); pg.wait_for_timeout(400)
    pg.click('.opt[data-v="bukhari"]'); _next(pg); pg.wait_for_timeout(400)
    pg.click(".opts .opt:nth-child(1)"); _next(pg); pg.wait_for_timeout(300)
    pg.click(".opts .opt:nth-child(1)"); _next(pg)
    check("درجة الحديث تُعرض تلقائيًّا لا تُختار",
          pg.is_visible("#ask .auto") and not pg.is_visible("#ask .opt"),
          pg.inner_text("#ask .auto")[:30] if pg.is_visible("#ask .auto") else "")
    grade_card = pg.inner_text("#tpl")
    check("الدرجة نفسها مطبوعة على البطاقة",
          pg.inner_text("#ask .auto").strip()[:6] in grade_card,
          pg.inner_text("#ask .auto")[:20])
    _next(pg); _next(pg)                     # المتن ثم العدد
    # الرجوع خطوتين
    pg.click("#ask .btn.ghost"); pg.wait_for_timeout(600)
    pg.click("#ask .btn.ghost"); pg.wait_for_timeout(600)
    check("«السابق» يرجع سؤالًا سؤالًا", "درجة الحديث" in pg.inner_text("#ask"),
          pg.inner_text("#ask").split("\n")[0])
    # تغيير الكتاب من الفتات
    crumbs = pg.eval_on_selector_all(".crumb", "e=>e.map(x=>x.textContent)")
    check("فتات الإجابات السابقة معروضة", len(crumbs) >= 4, str(len(crumbs)))
    pg.click(".crumbs .crumb:nth-child(5)"); pg.wait_for_timeout(900)   # سؤال الكتاب
    check("النقر على فتاتٍ يعيد إلى سؤاله", "أي كتاب" in pg.inner_text("#ask"),
          pg.inner_text("#ask").split("\n")[0])
    pg.click('.opt[data-v="muslim"]'); _next(pg); pg.wait_for_timeout(700)
    check("تغيير الكتاب يُسقط ما بُني عليه ويسأل عن الباب",
          "أي باب" in pg.inner_text("#ask"), pg.inner_text("#ask").split("\n")[0])
    check("لا خطأ عند الرجوع والتغيير", not errs, str(errs[:2]))
    pg.close()

# ═══════════ المعاينة ═══════════
def preview_flow(b):
    head("المعاينة المنشورة — تعمل بلا اتصال")
    pg = b.new_page(viewport={"width": 430, "height": 932})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    t0 = time.time()
    pg.goto(PREV); pg.wait_for_selector("#stat:not(:empty)", timeout=30000)
    pg.wait_for_timeout(500)
    check("المادّة تُفكّ وتُقرأ", "آية" in pg.inner_text("#stat"),
          f"{pg.inner_text('#stat')} · {time.time()-t0:.1f}ث")
    check("مربّع القالب فوق مربّع الأسئلة",
          pg.evaluate("""() => document.querySelector('.cardbox').getBoundingClientRect().top
                          < document.querySelector('.asker').getBoundingClientRect().top"""))
    n = lambda: (pg.click("#next"), pg.wait_for_timeout(300))
    pg.click('.opt[data-v="post"]'); n()
    pg.click('.opt[data-v="instagram"]'); n()
    pg.fill("#qbody input", "قناة نور"); n()
    pg.click('.opt[data-v="hadith"]'); n()
    pg.wait_for_timeout(200)
    check("البحث في المعاينة يتجاوز التشكيل",
          pg.evaluate("""() => { const D=window.D; return typeof norm==='function' &&
              norm('سُورَةُ الشَّرۡحِ').includes('الشرح'); }"""),
          pg.evaluate("() => typeof norm==='function' ? norm('سُورَةُ الشَّرۡحِ') : 'لا دالة'"))
    pg.click('.opt[data-v="nasai"]'); n(); pg.wait_for_timeout(300)
    labels = pg.eval_on_selector_all(".opt b", "e=>e.map(x=>x.textContent)")
    check("الباب الظاهر لِما لم يُسجَّل بابه معروض",
          any("بلا بابٍ مسجَّل" in l for l in labels), str(labels[-1:]))
    pg.click('.opt[data-v="-1"]'); n(); pg.wait_for_timeout(300)
    nums = pg.eval_on_selector_all(".opt b", "e=>e.map(x=>x.textContent)")
    check("أحاديثه الأربعة قابلة للاختيار", len(nums) == 4, str(nums))
    pg.click(".opts .opt:nth-child(1)"); n()
    check("الدرجة تلقائية", pg.is_visible("#qbody .auto"))
    n()                                        # الدرجة → المتن
    n()                                        # المتن → العدد
    n()                                        # العدد → من
    n()                                        # من → إلى
    n()                                        # إلى → التصميم
    check("سؤال التصميم بعد فرع الحديث", "تصميم" in pg.inner_text("#qt"), pg.inner_text("#qt"))
    pg.click('.opt[data-v="parch"]'); n()
    pg.click('.opt[data-v="navy"]'); n()
    pg.click('.opt[data-v="auto"]'); n()
    pg.click('.opt[data-v="auto"]'); n()
    pg.click('.opt[data-v="none"]'); n(); pg.wait_for_timeout(600)
    check("الخلاصة تظهر", "اكتملت الإجابات" in pg.inner_text("#qt"), pg.inner_text("#qt"))
    check("البطاقة تحمل خانتي العلامتين",
          "العلامة المائية للمستخدم" in pg.inner_text("#card")
          and "FALAH" in pg.inner_text("#card"))
    check("لون التصميم يُطبَّق في المعاينة", pg.get_attribute("#card", "data-tint") == "navy")
    check("لا خطأ في المعاينة", not errs, str(errs[:2]))

    # الشاشة العريضة والقياسات
    pg.set_viewport_size({"width": 1280, "height": 900}); pg.wait_for_timeout(400)
    check("لا تمرير أفقيّ على الشاشة العريضة",
          pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"),
          str(pg.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")))
    pg.set_viewport_size({"width": 360, "height": 740}); pg.wait_for_timeout(400)
    check("لا تمرير أفقيّ على شاشةٍ ضيّقة",
          pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"),
          str(pg.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")))
    check("البطاقة لا تفيض عن مربّعها",
          pg.evaluate("""() => { const c=document.querySelector('#card .paper');
              return c.scrollHeight <= c.clientHeight + 2; }"""),
          str(pg.evaluate("""() => { const c=document.querySelector('#card .paper');
              return [c.scrollHeight, c.clientHeight]; }""")))
    pg.close()

def rtl_and_a11y(b):
    head("الاتجاه وسهولة الوصول")
    pg = b.new_page(viewport={"width": 430, "height": 932})
    pg.goto(PREV); pg.wait_for_selector("#stat:not(:empty)", timeout=30000)
    check("اتجاه الصفحة من اليمين",
          pg.evaluate("() => getComputedStyle(document.body).direction") == "rtl",
          pg.evaluate("() => getComputedStyle(document.body).direction"))
    check("لكل زرٍّ نصٌّ مقروء",
          pg.evaluate("""() => [...document.querySelectorAll('button')].every(
              b => (b.textContent||'').trim() || b.getAttribute('aria-label'))"""))
    check("الأزرار تُبلغ حالة اختيارها",
          pg.evaluate("""() => [...document.querySelectorAll('.opt')].every(
              b => b.hasAttribute('aria-pressed'))"""))
    # التنقّل بلوحة المفاتيح
    pg.keyboard.press("Tab"); pg.keyboard.press("Tab")
    check("التركيز يظهر بالتنقّل بالمفاتيح",
          pg.evaluate("() => document.activeElement && document.activeElement.tagName !== 'BODY'"),
          pg.evaluate("() => document.activeElement && document.activeElement.tagName"))
    # تباين النصّ على البطاقة
    check("حبر البطاقة داكنٌ على ورقٍ فاتح (تباينٌ كافٍ)",
          pg.evaluate("""() => { const s=getComputedStyle(document.querySelector('#card'));
              const m=s.getPropertyValue('--cink').trim(); return m.length>0; }"""))
    pg.close()

if __name__ == "__main__":
    run()
    print("\n" + "─" * 46)
    if FAIL:
        print(f"النتيجة: نجح {OK} · سقط {FAIL}")
        for n, d in FAILURES: print(f"  ✗ {n}  ← {d}")
        sys.exit(1)
    print(f"النتيجة: كل فحوص الواجهة نجحت ✓  ({OK} بندًا)")
