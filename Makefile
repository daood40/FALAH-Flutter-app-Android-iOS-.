# أوامر فلاح — `make` وحدها تعرض القائمة.
#
# القاعدة: كل ما يفعله خطُّ التكامل يمكن تشغيله هنا بالأمر نفسه. فما نجح
# محلّيًّا ينجح هناك، ولا يُكتشف الخطأ بعد الدفع.

.DEFAULT_GOAL := help
SHELL := /bin/bash
PY    ?= python3
PORT  ?= 8080
APP   ?= http://localhost:$(PORT)

.PHONY: help dev worker lint typecheck security contract test audit ui failure gate \
        db migrate migrate-plan status build docker clean install

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

docker:  ## يبني صورة الحاوية
	docker build -t falah:local .

# ═══════════ بوّابة الجودة ═══════════
# نفس ترتيب `.github/workflows/ci.yml` ونفس شروطه. `set -e` يجعل أول
# سقوطٍ يُسقط الأمر كلّه — فلا «بُني بنجاح» فوق اختبارٍ ساقط.
gate:  ## يشغّل بوّابة الجودة كاملةً كما في CI
	@set -e; \
	echo "── ١ · lint ──";      ruff check .; \
	echo "── ٢ · types ──";     mypy .; \
	echo "── ٣ · secrets ──";   $(PY) security_scan.py; \
	echo "── ٤ · api contract ──"; $(PY) api_contract.py --check; \
	echo "── ٥ · migrations ──"; $(PY) -m falah.migrate --status; \
	echo "── ٦ · unit ──";      $(PY) tests.py | tail -3; \
	echo "── ٧ · server ──"; \
	  (fuser -k $(PORT)/tcp 2>/dev/null || true); sleep 1; \
	  FALAH_INLINE_WORKER=0 PORT=$(PORT) setsid nohup $(PY) app.py > /tmp/gate-app.log 2>&1 & \
	  setsid nohup $(PY) worker.py > /tmp/gate-worker.log 2>&1 & \
	  for i in $$(seq 1 60); do curl -fsS $(APP)/healthz >/dev/null 2>&1 && break; sleep 1; done; \
	  curl -fsS $(APP)/readyz | grep -q '"ready": true'; \
	echo "── ٨ · audit ──";     APP=$(APP) API=$(APP) $(PY) audit.py | tail -3; \
	echo "── ٩ · ui ──";        APP=$(APP) $(PY) ui_audit.py | tail -3; \
	echo "── ١٠ · failure ──";   $(PY) failure_test.py | tail -3; \
	echo; echo "QUALITY_GATE = PASS"

clean:  ## يحذف المؤقّتات والذاكرات (لا يمسّ القواعد ولا الصادرات)
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache .mypy_cache
	@echo "نُظّفت المؤقّتات. القواعد والصادرات لم تُمسّ."
