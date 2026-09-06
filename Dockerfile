FROM python:3.11-slim

# ffmpeg للفيديو، وكروميوم للتصيير — كلاهما لازمٌ للتصدير لا للقراءة
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg fonts-liberation libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
      libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
      libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 sqlite3 curl \
 && rm -rf /var/lib/apt/lists/*
# شهاداتٌ إضافيّةٌ للشبكات التي تعترض TLS (وسيطُ مؤسّسةٍ أو جدارُ حماية).
# المجلَّدُ فارغٌ افتراضيًّا فلا تتغيّر ثقةُ الصورة بشيء؛ ومن وضع فيه `.crt`
# نجح بناؤه من خلف وسيطه. **وليس تخفيفًا للتحقّق**: الشهادةُ تُضاف إلى
# المخزن ولا يُعطَّل التحقّقُ بحال — لا `--trusted-host` ولا `verify=False`.
COPY certs/ /usr/local/share/ca-certificates/falah-extra/
RUN update-ca-certificates \
 && printf '[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n' > /etc/pip.conf
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && playwright install chromium

WORKDIR /app
COPY falah/ falah/
COPY fonts/ fonts/
COPY build.py verify_image.py api.py app.py worker.py render.py video.py carousel.py batch.py \
     templates.py icons.py export_snapshot.py \
     falah-app.html falah-agent.html manifest.webmanifest sw.js README.md ./
COPY icons/ icons/

# `backup.sh` وحدَه من `deploy/`: النسخُ الاحتياطيُّ يُشغَّل **داخل** الحاوية
# حيث القاعدةُ على الحجم، فيلزم أن يكون فيها.
#
# ولا يُكتب `COPY deploy/ deploy/`: المجلّدُ يحوي `.env` بأسرارِ الإنتاج،
# وطبقاتُ الصورة تُقرأ بـ`docker history` ولو حُذف الملفُّ في طبقةٍ تالية.
COPY deploy/backup.sh deploy/

# القاعدة تُبنى وقت الصورة إن وُجد الخام، أو تُركَّب كحجم خارجي
COPY raw/ raw/

# ═══ التحقّقُ من الصورة — لا من المستودع ═══
# كان هنا `python3 tests.py`، وهو خطأٌ في الشكل لا في النيّة: ذلك الملفُّ
# يفحص **المستودع** — يقرأ `Dockerfile` و`ci.yml` و`.gitignore` و`deploy/`.
# فكان يُلزم صورةَ الإنتاج أن تحمل سقالةَ المستودع كلَّها لتفحص نفسها بها،
# ثم يسقط البناءُ لأنّ الصورةَ — بحقٍّ — لا تحمل `Dockerfile`.
#
# فالفصل: `tests.py` يجري على المستودع في خطّ التكامل (وظيفتا static و
# tests)، **ولم يُنقص منه شيء**. وهنا يُفحص ما بُني في هذه الصورة فعلًا:
# قاعدةُ محتوًى سليمةٌ غيرُ فارغة، ثم خادمٌ يقلع ويُعلن جاهزيّته.
RUN python3 build.py && python3 verify_image.py && rm -rf raw

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
