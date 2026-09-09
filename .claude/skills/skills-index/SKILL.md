---
name: skills-index
description: الفهرس الكامل للمهارات الـ121 وقواعد الأسبقية بينها — أي مهارة تُفتح لأي مهمة، وأيّها يحكم عند التداخل، وترتيب فتحها في مشروع كامل من الفكرة إلى الإطلاق. تُفتح في بداية أي مهمة غير بديهية، أو عند ذكر "أي مهارة", "ما المهارات", "من أين أبدأ", "الفهرس", "which skill", "index", "what skills".
---

# فهرس المهارات وقواعد الأسبقية

١٢١ مهارة في تسع عائلات. **افتح المهارة قبل كتابة الجزء الذي تخصّه، لا بعده.**

## قواعد الأسبقية — تمنع التعارض

| التداخل | من يحكم |
|---|---|
| قرار تصميمي (لون، مسافة، حجم خط) مقابل تنفيذه في Flutter | `design-*` تحدّد **القيمة والسبب**، و`flutter-ui-design` تحدّد **الكود**. لا قيم خام في الكود؛ مرّرها عبر الثيم. |
| واجهة ويب مقابل واجهة Flutter | `web-*` للمسار غير-Flutter فقط. لا تخلطهما في مشروع واحد. |
| Supabase من التطبيق مقابل من الخادم | `flutter-supabase` للعميل، و`data-supabase-backend` للـSQL والسياسات والدوال. القواعد الأمنية تُكتب في الثانية دائماً. |
| ذكاء اصطناعي في التطبيق مقابل على الخادم | `flutter-ai-integration` للعميل، و`ai-*` للمنهج والخادم. المفتاح السرّي لا يدخل التطبيق أبداً — تعلو على كل شيء. |
| **كتابة اختبار مقابل الحكم عليه** | `flutter-testing` تشرح **كيف يُكتب** الاختبار، وعائلة `qa-*` تشرح **ماذا يُختبر ومتى وكيف يُحكم بنجاح أو فشل**. |
| إصلاح مشكلة مقابل قياسها | `flutter-performance` و`web-performance` و`flutter-security` **تُصلح**؛ `qa-performance-testing` و`qa-security-testing` **تقيس وتحكم**. |
| نشر التطبيق للمتاجر مقابل النشر عموماً | `flutter-build-release` للمتاجر، و`ops-*` لـgit وCI والاستضافة والمراقبة. |
| نصوص الواجهة مقابل شكل الحالة | `content-ux-writing-arabic` تحكم **الصياغة**، و`design-empty-error-states` تحكم **متى تظهر الحالة وشكلها**. |
| قرار منتج مقابل قرار تقني | `product-*` تقرّر **ماذا نبني ولمن**؛ البقية تقرّر **كيف**. |
| أي تعارض مع تعليمات المستودع | **`CLAUDE.md` ووثائق `docs/` و`memory/` تسبق كل المهارات.** المهارات مرجع تقني لا مصدر قرار. |

عند الشك: افتح الأضيق نطاقاً، لا الأوسع.

## ٠ — الطريقة (7)

| المهارة | متى |
|---|---|
| `flutter-autobuild` | بناء تطبيق أو ميزة كاملة من جملة واحدة بلا أوامر بينية |
| `flutter-app-blueprint` | خريطة مهارات Flutter وخطة المراحل السبع |
| `project-memory` | ملفات `memory/` — حتى لا تبدأ كل جلسة وكأن المشروع جديد |
| `simplicity-first` | منع التعقيد الزائد: أبسط حل يعمل أولاً |
| `claude-code-mastery` | صياغة الطلبات، إدارة السياق، وضع التخطيط، الوكلاء |
| `claude-code-mobile` | العمل من الجوال، وGitHub Actions كجهاز البناء |
| `claude-code-project-setup` | تجهيز المستودع: CLAUDE.md، المهارات، الوكلاء، الصلاحيات |

**اقرأ `project-memory` في بداية كل جلسة على مشروع قائم، و`simplicity-first` قبل أي قرار بنيوي.**

## ١ — التصميم وتجربة المستخدم (18)

**الأساسيات:** `design-foundations` · `design-color-theory` · `design-color-palette` · `design-typography` · `design-arabic-typography` · `design-spacing-layout`

**النظام:** `design-system-building` · `design-tokens` · `design-dark-mode` · `design-accessibility`

**التجربة:** `design-mobile-ux` · `design-navigation-ia` · `design-forms-ux` · `design-empty-error-states` · `design-onboarding` · `design-arabic-ui`

**الحكم البصري:** `design-taste` (منع المظهر المولّد العام) · `design-critique` (مراجعة واجهة قائمة)

## ٢ — Flutter (34)

**التأسيس:** `flutter-project-setup` · `flutter-code-quality`
**الواجهة:** `flutter-ui-design` · `flutter-navigation` · `flutter-forms-validation` · `flutter-animations` · `flutter-charts`
**البيانات:** `flutter-state-management` · `flutter-supabase` · `flutter-firebase` · `flutter-networking-api` · `flutter-local-database`
**الميزات:** `flutter-arabic-rtl` · `flutter-search-filter` · `flutter-device-features` · `flutter-notifications` · `flutter-ai-integration` · `flutter-chat-realtime` · `flutter-media` · `flutter-documents` · `flutter-background-tasks`
**الأعمال:** `flutter-monetization` · `flutter-payments` · `flutter-analytics`
**الجودة:** `flutter-security` · `flutter-performance` · `flutter-testing` · `flutter-debugging`
**النشر:** `flutter-build-release` · `flutter-web-deploy` · `flutter-desktop` · `flutter-package-authoring`

## ٣ — ضمان الجودة والاختبار (18)

**المنهج:** `qa-test-strategy` · `qa-engineer-mode` · `qa-test-plan-writing` · `qa-bug-reporting`
**المسارات:** `qa-e2e-testing` · `qa-regression-testing`
**التقني:** `qa-api-testing` · `qa-database-testing` · `qa-security-testing` · `qa-performance-testing` · `qa-network-testing`
**المنصّات:** `qa-mobile-testing` · `qa-web-testing` · `qa-cross-platform-testing`
**الجودة الشاملة:** `qa-localization-testing` · `qa-accessibility-testing` · `qa-visual-regression`
**البوابة:** `qa-production-readiness`

**قاعدة ملزمة:** لا يُقال "جاهز للإنتاج" إلا بعد اجتياز بوابات `qa-production-readiness` بتقرير PASS/FAIL حقيقي.

## ٤ — الويب (9)

`web-html-semantics` · `web-css-modern` · `web-tailwind` · `web-responsive` · `web-react-foundations` · `web-react-state` · `web-typescript` · `web-performance` · `web-seo`

## ٥ — البيانات والخادم (9)

`data-sql-fundamentals` · `data-schema-design` · `data-postgres-advanced` · `data-supabase-backend` · `data-migrations` · `data-api-design` · `data-auth-patterns` · `data-caching` · `data-backup-recovery`

## ٦ — الذكاء الاصطناعي (7)

`ai-prompt-engineering` · `ai-app-architecture` · `ai-rag-systems` · `ai-agents-tools` · `ai-evaluation` · `ai-cost-optimization` · `ai-arabic-nlp`

## ٧ — التشغيل (6)

`ops-git-workflow` · `ops-github-actions` · `ops-cicd-pipelines` · `ops-hosting` · `ops-monitoring` · `ops-secrets`

## ٨ — المنتج والمحتوى (14)

`product-discovery` · `product-mvp-scoping` · `product-spec-writing` · `product-user-research` · `product-metrics` · `product-pricing` · `product-launch-aso` · `product-growth-retention` · `product-arab-market` · `product-legal-privacy`

`content-ux-writing-arabic` · `content-store-copy` · `content-technical-docs` · `content-marketing-social`

## ترتيب المشروع الكامل

| المرحلة | المهارات بالترتيب |
|---|---|
| قبل الكود | `product-discovery` → `product-user-research` → `product-mvp-scoping` → `product-spec-writing` → `product-arab-market` |
| القرار البصري | `design-taste` → `design-foundations` → `design-color-palette` → `design-arabic-typography` → `design-spacing-layout` → `design-tokens` |
| التأسيس | `claude-code-project-setup` → `project-memory` → `flutter-project-setup` → `flutter-arabic-rtl` → `ops-git-workflow` → `ops-github-actions` |
| البيانات | `data-schema-design` → `data-supabase-backend` → `data-migrations` → `flutter-supabase` |
| البناء | `flutter-autobuild` يقود، و`simplicity-first` تحكم كل قرار بنيوي |
| التجربة | `design-mobile-ux` → `design-forms-ux` → `design-empty-error-states` → `design-onboarding` → `content-ux-writing-arabic` |
| الاختبار | `qa-test-strategy` → `qa-engineer-mode` → `qa-e2e-testing` → `qa-api-testing` → `qa-database-testing` → `qa-network-testing` → `qa-localization-testing` → `qa-accessibility-testing` → `qa-security-testing` → `qa-performance-testing` |
| بوابة الإطلاق | `qa-production-readiness` — لا يُتجاوز |
| الإطلاق | `product-pricing` → `flutter-monetization` → `product-legal-privacy` → `content-store-copy` → `flutter-build-release` → `product-launch-aso` |
| بعد الإطلاق | `product-metrics` → `flutter-analytics` → `qa-regression-testing` → `product-growth-retention` → `design-critique` |

## قواعد ثابتة تعلو على تفاصيل أي مهارة

- لا مفتاح سرّي داخل كود التطبيق أو نسخة الويب — أبداً.
- الصلاحيات تُفرض على الخادم؛ فحص العميل تجربة استخدام لا أمان.
- كل نص ظاهر للمستخدم من ملف الترجمة.
- كل شاشة لها أربع حالات: تحميل، فراغ، خطأ، بيانات.
- **لا ادعاء نجاح بناء أو اختبار لم يُشغَّل فعلاً، ولا "جاهز للإنتاج" بلا تقرير.**
- أبسط حل يعمل أولاً؛ لا تبنِ للمستقبل المتخيَّل.
- ملفات `memory/` تُحدَّث في نفس الـcommit الذي أحدث التغيير.
- العمل على فرع، وcommit صغير برسالة تشرح السبب.

## قائمة تحقق عند بدء أي مهمة

- [ ] قرأت `memory/PROJECT_MEMORY.md` و`TODO.md` إن كان المشروع قائماً
- [ ] حدّدت العائلة التي تنتمي إليها المهمة
- [ ] فتحت المهارة الأضيق نطاقاً لا الأوسع
- [ ] راجعت قاعدة الأسبقية إن تداخل الموضوع مع عائلة أخرى
- [ ] تحققت أن `CLAUDE.md` لا يناقض ما ستفعله
- [ ] القواعد الثابتة أعلاه مطبّقة
