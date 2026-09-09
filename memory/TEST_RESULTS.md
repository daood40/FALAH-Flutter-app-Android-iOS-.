# memory/TEST_RESULTS.md   (يُكتب بعد تشغيل حقيقي فقط)

## 2026-09-09 — تشغيلٌ في جلسة Claude Code على استنساخٍ نظيف

الأمر: `python3 gate.py` → **٦ PASS · ١ BLOCKED · ١ FAIL**
  ✓ ruff · mypy · الأسرار · عقد API · سلامة القاعدة · بروفة الهجرات
  ! ثغرات الاعتماديات — BLOCKED (`pip-audit` غير مثبَّتٍ محلّيًّا؛ **يمرّ في CI**)
  ✗ `unit` — `unable to open database file` (لا `falah.db`) → ENV-01

الأمر: `python3 invariants.py` → **١٩ ثابتًا صامدة · QUALITY_GATE = PASS**
الأمر: `cors_test` · `obs_test` · `pub_test` · `sched_test` → **١٦٤ فحصًا · ٠ ساقط**
المرحلتان الساكنتان في `authz_test` + `rbac_test` → **٩٩ فحصًا · ٠ ساقط**

## 2026-09-09 — GitHub Actions run #13 (commit 2831804)
`static`  → **success** · ١٢ خطوة، ومنها pip-audit و ruff و mypy وعقد API
`flutter` → **success** · ومنه:
   · بناءُ APK التجربة · صلاحيةُ الإنترنت **موجودةٌ في الحزمة فعلًا**
   · الهُويّةُ تقول إنّه تجريبيّ · الاختباراتُ **على خادمٍ حيّ** · لا تخطٍّ صامت
   · الأثر: `falah-android-staging-apk` — ٢٦٫٥ م.ب
`tests` → **failure** عند «بناء قاعدة المحتوى» → ENV-01 · وما بعده متخطًّى
`build` (الحاوية) و`QUALITY_GATE` → متخطٍّ / فاشلٌ تبعًا

## لم يُشغَّل — ولا يُدَّعى
`tests.py` (١٤٦٦ فحصًا) · المراحلُ الحيّة في `authz`/`rbac`/`leak` ·
`flutter test` محلّيًّا (لا Flutter SDK هنا؛ يجري في CI) · بناءُ iOS ·
بناءُ صورة الحاوية · اختبارُ حِمل.
