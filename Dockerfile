FROM python:3.11-slim

# ffmpeg للفيديو، وكروميوم للتصيير — كلاهما لازمٌ للتصدير لا للقراءة
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg fonts-liberation libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
      libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
      libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 sqlite3 curl \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && playwright install chromium

WORKDIR /app
COPY falah/ falah/
COPY fonts/ fonts/
COPY build.py api.py app.py worker.py render.py video.py carousel.py batch.py \
     templates.py icons.py tests.py export_snapshot.py \
     falah-app.html falah-agent.html manifest.webmanifest sw.js README.md ./
COPY icons/ icons/

# القاعدة تُبنى وقت الصورة إن وُجد الخام، أو تُركَّب كحجم خارجي
COPY raw/ raw/
RUN python3 build.py && python3 tests.py && rm -rf raw

# app.db والصادرات على حجمٍ خارجي كي تبقى بعد تحديث الصورة
VOLUME ["/data"]
ENV FALAH_APP_DB=/data/app.db PORT=8080
EXPOSE 8080
# فحص الحاوية = الحياة (`/healthz`): سؤالٌ رخيصٌ لا يلمس قاعدةً، وسقوطه
# يعني عمليةً ميتةً تستحقّ إعادة تشغيل. أما الجاهزية (`/readyz`) فتُسأل من
# الموازِن: سقوطها يعني سحبَ الحركة لا قتلَ الحاوية. و`/health` إحصاءٌ
# للقاعدة — كان يُستدعى كل ٣٠ ثانية بلا داعٍ.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8080/healthz || exit 1
CMD ["python3","app.py"]
