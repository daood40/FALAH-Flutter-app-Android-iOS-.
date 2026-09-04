# أوامر فلاح — `make` وحدها تعرض القائمة.
#
# القاعدة: كل ما يفعله خطُّ التكامل يمكن تشغيله هنا بالأمر نفسه. فما نجح
# محلّيًّا ينجح هناك، ولا يُكتشف الخطأ بعد الدفع.

.DEFAULT_GOAL := help
SHELL := /bin/bash
PY    ?= python3
PORT  ?= 8080
APP   ?= http://localhost:$(PORT)

.PHONY: help dev worker lint typecheck security deps contract test audit ui failure leak isolation authz rbac gate gate-all gate-list \
        db db-check db-backup db-restore-test migrate-check migrate-guard db-safe-migrate \
        migrate migrate-plan status build docker clean install

help:  ## يعرض هذه القائمة
	@echo "أوامر فلاح:"
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	 | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## يثبّت اعتماديات التطوير
	pip install --no-cache-dir -r requirements.txt
	pip install --no-cache-dir ruff mypy
	playwright install chromium

db:  ## يبني قاعدة المحتوى من raw/ (طويل — مرّةً واحدة)
	$(PY) build.py

db-check:  ## سلامة القاعدة وأعدادها وحالة الهجرات والنسخ
	$(PY) dbsafe.py check

db-backup:  ## نسخةٌ حيّة موقَّعةٌ ببصمتها
	$(PY) dbsafe.py backup

db-restore-test:  ## يسترجع آخر نسخةٍ ويتحقّق منها فعلًا (ويوقّع بيانها)
	$(PY) dbsafe.py restore-test

migrate-check:  ## بروفةُ الهجرات على نسخةٍ من القاعدة الحقيقية — لا تمسّها
	$(PY) dbsafe.py migrate-check

migrate-guard:  ## هل يجوز تشغيل هجرةٍ هادمة الآن؟
	$(PY) dbsafe.py guard

db-safe-migrate:  ## التسلسل الآمن كاملًا قبل أي هجرةٍ هادمة
	@set -e; \
	$(PY) dbsafe.py check; \
	$(PY) dbsafe.py backup; \
	$(PY) dbsafe.py restore-test; \
	$(PY) dbsafe.py migrate-check; \
	$(PY) dbsafe.py guard; \
	echo; echo "التسلسل تمّ. الهجرة الهادمة لم تُطبَّق بعد — هذا قرارٌ يدويّ:"; \
	echo "  FALAH_ALLOW_DESTRUCTIVE=1 $(PY) -m falah.migrate"

migrate:  ## يطبّق الهجرات الآمنة
	$(PY) -m falah.migrate

migrate-plan:  ## يقول ماذا ستفعل الهجرات ولا يفعل
	$(PY) -m falah.migrate --plan

dev:  ## يشغّل الخادم بعاملٍ داخليّ (تطوير)
	PORT=$(PORT) FALAH_INLINE_WORKER=1 $(PY) app.py

serve:  ## يشغّل الخادم بلا عامل (كما في الإنتاج)
	PORT=$(PORT) FALAH_INLINE_WORKER=0 $(PY) app.py

worker:  ## يشغّل عامل التصيير منفصلًا
	$(PY) worker.py

status:  ## حالة الطابور
	$(PY) worker.py --status

lint:  ## ruff
	ruff check .

typecheck:  ## mypy
	mypy .

contract:  ## يولّد API.md من الشيفرة
	$(PY) api_contract.py

deps:  ## فحص ثغرات الاعتماديات (يلزمه شبكة)
	@if ! command -v pip-audit >/dev/null 2>&1; then \
	  echo "BLOCKED: pip-audit غير مثبَّت — pip install pip-audit"; exit 1; fi
	pip-audit -r requirements.txt --progress-spinner off

security:  ## فحص الأسرار والإعداد
	$(PY) security_scan.py

test:  ## اختبارات الوحدة والتكامل
	$(PY) tests.py

audit:  ## الفحص الشامل (يلزمه خادمٌ يعمل على $(APP))
	APP=$(APP) API=$(APP) $(PY) audit.py

ui:  ## فحص الواجهة في متصفّح (يلزمه خادمٌ يعمل)
	APP=$(APP) $(PY) ui_audit.py

failure:  ## اختبار الكسر المتعمَّد (يشغّل خوادمه بنفسه)
	$(PY) failure_test.py

leak:  ## فحص تسريب الأخطاء والسجلّ (يشغّل خادمه بنفسه)
	$(PY) leak_test.py

isolation:  ## حدود المستخدم والملفّات: أ ← موردُ ب (يشغّل خادمه بنفسه)
	$(PY) isolation_test.py

authz:  ## طبقة الإذن: can() وحدها، واكتمالُ الجدول، وأ ← موردُ ب حيًّا
	$(PY) authz_test.py

rbac:  ## الأدوار والصلاحيات وسجلّ التدقيق — مصفوفةٌ وتصعيدٌ وحقنُ أعطال
	$(PY) rbac_test.py

roles:  ## يعرض الأدوار في القاعدة وصلاحياتِ كلٍّ منها
	$(PY) -m falah.roles list

docker:  ## يبني صورة الحاوية
	docker build -t falah:local .

# ═══════════ بوّابة الجودة ═══════════
# أمرٌ واحد يشغّل الترتيب نفسه الذي في `.github/workflows/ci.yml`. يقف عند
# أول سقوطٍ حرج ويطبع: ماذا · لماذا · بأي أمر · في أي ملفّ · وما الإصلاح.
# وما لم يُشغَّل يُقال عنه BLOCKED لا PASS.
gate:  ## بوّابة الجودة كاملةً — تقف عند أول سقوطٍ وتشرحه
	$(PY) gate.py

gate-all:  ## البوّابة كاملةً بلا توقّف — لتُري كلَّ ما سقط
	$(PY) gate.py --keep-going

gate-list:  ## يعرض البوّابات وحرجَها
	$(PY) gate.py --list

clean:  ## يحذف المؤقّتات والذاكرات (لا يمسّ القواعد ولا الصادرات)
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache .mypy_cache
	@echo "نُظّفت المؤقّتات. القواعد والصادرات لم تُمسّ."
