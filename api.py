#!/usr/bin/env python3
"""FALAH — خادم المحتوى. مكتبة قياسية فقط.

    python3 api.py          →  http://localhost:8080/health

المسارات
  GET /health                                          حالة الخدمة والأعداد
  GET /sources                                         سجل المصادر وحالة تراخيصها
  GET /topics                                          فهرس الموضوعات (لسؤال الوكيل)
  GET /topics/{id}?kind=quran|hadith&limit=20          مقترحات جاهزة للبطاقة
  GET /quran/search?q=&limit=                          بحث بلا تشكيل
  GET /quran/ayah?surah=&ayah=&to=                     الآية بمرجعها
  GET /hadith/search?q=&limit=&card_only=1
  GET /hadith?book=bukhari&no=1                        الحديث بمتنه وتخريجه
  GET /card?kind=quran&surah=94&ayah=5&to=6&tafsir=1&translation=1
  GET /card?kind=hadith&book=bukhari&no=1              ← البطاقة بعد ٢٥ فحصًا
  GET /card?…&require_jami=1                           تشديد: لا يخرج إلا ما شهد له الأعظمي
  GET /reciters                                        القرّاء مرتَّبين بالروايات
  GET /audio?surah=&ayah=[&reciter=]                   روابط التلاوة لكل قارئ
  GET /enc/search?q=&card_only=1                       بحث في الموسوعة
  GET /enc?id=                                         حديث بشرحه وفوائده وترجماته
  GET /card?kind=enc&id=                               بطاقة من الموسوعة بعد الفحص
  GET /verify?text=[&surah=&ayah=]                     فحص البصمة وحده
  GET /review?kind=quran|hadith&limit=                 كل ما حُجب ولماذا
"""
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from falah import content_routes as CR

# طبقةُ النطاق نزلت إلى `falah/cards.py`، وتُعاد تسميتُها هنا كما كانت —
# فـ`api.quran_card` وأخواتها تبقى عاملةً في `render.py` و`build.py`
# و`falah/projects.py` وحزم الاختبار، بلا تغييرِ نداءٍ واحد.
from falah.cards import (AR, DB, GRADE_EN, arabic_num, backoff, conn,  # noqa: F401
                         enc_card, hadith_card, quran_card)
# وهذه كانت في فضاء أسماء `api` كذلك، ويستوردها منه `audit.py` وغيره.
# تُعاد تسميتُها كما كانت — فلا يُكسر مستوردٌ قائمٌ بحجّة «إعادة تنظيم».
from falah import verify as V                                       # noqa: F401
from falah.audio import audio_url                                   # noqa: F401
from falah.matn import matn_sane                                    # noqa: F401
from falah.text import fingerprint, search_variants, searchable     # noqa: F401

# ───────────────────────── الخادم ─────────────────────────
# ما بقي هنا هو HTTP وحده: يقرأ المسار، ويفتح اتصالًا، وينادي الجدول،
# ويكتب الردّ. الحكمُ والبناءُ والاستعلامُ كلُّها تحته لا فيه.

class H(BaseHTTPRequestHandler):
    server_version = "FALAH/1.0"

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *a): pass

    def do_GET(self):
        u = urlparse(self.path)
        c = conn()
        try:
            obj, code = CR.dispatch(c, u.path.rstrip("/") or "/", parse_qs(u.query))
            self._send(obj, code)
        except (ValueError, TypeError, OverflowError):
            # رقمٌ غير رقم، أو حقلٌ ناقص — خطأ في الطلب لا في الخادم.
            #
            # و`OverflowError` معها وإن لم ترثها: أعدادُ بايثون بلا سقف،
            # فـ`int("9"*40)` تنجح ثم تفيض عند ربطها بـSQLite. فكان رقمٌ
            # من أربعين خانةً في `?surah=` يُخرج ٥٠٠ لأيِّ زائرٍ بلا جلسة.
            # كُشف بجولةٍ عدائيّةٍ على خادمٍ حيّ — راجع `qa/rounds/`.
            self._send({"error": "قيمةٌ غير صالحة في الطلب"}, 400)
        except Exception as e:
            # لا يُسرَّب أثر التنفيذ إلى الخارج؛ يُسجَّل عندنا ويُختصر عندهم
            print("ERR", type(e).__name__, e, flush=True)
            self._send({"error": "خطأ داخلي"}, 500)
        finally:
            c.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"FALAH content API → http://localhost:{port}/health", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
