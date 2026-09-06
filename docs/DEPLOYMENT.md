# النشرُ والتشغيل — دليلٌ عمليّ

> **حالةُ هذه الوثيقة:** شيفرةُ النشر كاملةٌ ومُتحقَّقٌ منها (`docker build`
> ينجح، والحاويةُ تقلع وتُعلن `healthy`). وما يبقى خارجَها **خادمٌ ونطاقٌ
> يملكهما المالك** — لا نقصٌ برمجيّ.

---

## ١ · ما تحتاجه قبل البدء

| | الحدُّ الأدنى | لماذا |
|---|---|---|
| الذاكرة | **٤ ج.ب** | كروميوم للتصيير + ffmpeg للمقاطع |
| المعالج | نواتان | العاملُ يصيّر بينما الخادمُ يستقبل |
| القرص | ٢٠ ج.ب | صورةٌ ٢٫٩ ج.ب + قاعدةُ محتوًى + صادرات + نسخ |
| النظام | أيُّ توزيعةٍ فيها Docker ≥ ٢٤ | — |
| النطاق | مسجَّلٌ باسمك | الشهادةُ التلقائيّةُ تحتاج DNS يشير للخادم |

**والمنفذان ٨٠ و٤٤٣ مفتوحان** — لولا الأوّل لا تصدر شهادةُ Let's Encrypt.

---

## ٢ · النطاق

سجِّل في مزوّد DNS:

```
A     falah.example.com      →  <عنوان خادمك>
AAAA  falah.example.com      →  <عنوانك السادس>   (إن وُجد)
```

وتحقّق قبل أن تُقلع (الانتشارُ يستغرق دقائقَ إلى ساعات):

```bash
dig +short falah.example.com
```

لا تُقلع قبل أن يعيد عنوانَ خادمك: Let's Encrypt يحدُّ محاولاتِ الإصدار
الفاشلة، فمحاولةٌ مبكّرةٌ تُعطّلك ساعاتٍ بلا سبب.

---

## ٣ · الإقلاع الأوّل

```bash
git clone <مستودعك> /opt/falah && cd /opt/falah

# (١) ملفُّ البيئة — من القالب، ثم يُقفل
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env          # ← لا تتجاوزها
nano deploy/.env
```

**املأ في `deploy/.env`:**

| المتغيّر | القيمة |
|---|---|
| `FALAH_DOMAIN` | نطاقك |
| `FALAH_ORIGIN` | `https://` + نطاقك |
| `FALAH_SECRET_KEY` | **سرٌّ عشوائيٌّ طويل** — يُعمّي اعتماداتِ النشر |
| `FALAH_INVITE` | رمزُ دعوةٍ إن أردت إطلاقًا مغلقًا (اتركه فارغًا للفتح) |
| `FALAH_SMTP_*` | مزوّدُ البريد |

مفتاحٌ عشوائيّ:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

> ⚠ `FALAH_SECRET_KEY` **يُعمّي رموزَ حسابات النشر**. تغييرُه لاحقًا يجعل
> الحساباتِ المربوطةَ غيرَ قابلةٍ للفكّ، فيُعاد ربطُها. ثبِّته من أوّل يوم.

```bash
# (٢) الإقلاع
cd deploy
FALAH_DOMAIN=falah.example.com docker compose up -d

# (٣) التحقّق — لا تمضِ قبل أن ترى ready:true
curl -fsS https://falah.example.com/healthz
curl -fsS https://falah.example.com/readyz
```

**و`readyz` سيقول `pending_migrations: ["003:jobs_state_guard"]`.** هذا
متوقَّع، والخطوةُ التالية تعالجه.

---

## ٤ · الهجرة ٠٠٣ — الطريقُ الوحيدُ المسموح

الهجرةُ ٠٠٣ **هادمة**: تعيد بناءَ جدول المهامّ لتضيف قيدًا على الحالة.

```bash
docker compose exec app make db-safe-migrate
```

وهذا يفعل بالترتيب: نسخةٌ احتياطيّة ← **بروفةٌ على النسخة** ← تطبيقٌ على
الحيّة ← تحقُّق.

> ❌ **لا تشغّل `python3 -m falah.migrate` مباشرةً على الإنتاج.**
> ❌ **ولا تضع `FALAH_ALLOW_DESTRUCTIVE=1`** — الحارسُ داخل `falah/migrate.py`
> نفسِه ولا يتجاوزه هذا المتغيّر. ووجودُه في أمرٍ تكتبه إشارةٌ إلى أنك
> تلتفّ على حماية.

---

## ٥ · النسخُ الاحتياطيُّ والاسترجاع

### النسخُ آليّ

خدمةُ `backup` تنسخ كلَّ يومٍ في **٣:٠٠** إلى الحجم `falah-backups`، وتحفظ
آخرَ ١٤ نسخة (`FALAH_BACKUP_KEEP`). ولها فحصُ صحّةٍ يصير `unhealthy` إن مرّت
٤٨ ساعةً بلا نسخة — فخدمةٌ «تعمل» ولا تنسخ لا تمرّ صامتة.

```bash
docker compose exec app make db-backup      # نسخةٌ الآن
docker compose logs backup | tail -20
```

### والاسترجاع يُختبر، لا يُفترض

```bash
docker compose exec app make db-restore-test
```

يفكّ آخرَ نسخة، ويطابق بصمتَها، ويفحص السلامةَ والمفاتيحَ الأجنبيّة، ويقارن
**الأعدادَ جدولًا جدولًا**، ثم **يُقلع التطبيقَ على القاعدة المسترجَعة ويطلب
منها طلبًا فعليًّا**.

> نسخةٌ لم تُسترجَع ليست نسخة. أجرِ هذا **بعد أوّل نشرٍ** ثم شهريًّا.

### استرجاعٌ حقيقيّ بعد كارثة

```bash
docker compose stop app worker              # لا يُكتب على القاعدة أثناء الاستبدال
docker compose run --rm -v falah-backups:/b app \
  sh -c 'gunzip -c /b/app-<الطابع>.db.gz > /data/app.db'
docker compose start app worker
curl -fsS https://falah.example.com/readyz  # ready:true
```

### إخراجُ النسخ من الخادم

نسخةٌ على القرص نفسِه ليست نسخةً من عطب القرص:

```bash
docker run --rm -v falah-backups:/b -v "$PWD":/out alpine \
  sh -c 'cp /b/$(ls -1t /b | head -1) /out/'
```

ثم انقلها إلى موضعٍ خارج الخادم.

---

## ٦ · التحديث والتراجع

### التحديث

```bash
cd /opt/falah
git fetch && git log --oneline HEAD..origin/main    # اقرأ ما سيتغيّر
docker compose exec app make db-backup              # نسخةٌ قبل كلِّ تحديث
git pull
docker compose build
docker compose up -d
curl -fsS https://falah.example.com/readyz
```

الصورةُ تتحقّق من نفسها وقت البناء (`verify_image.py`): قاعدةٌ سليمةٌ غيرُ
فارغة، وخادمٌ يقلع ويُعلن جاهزيّته. فصورةٌ معطوبةٌ **لا تُبنى** ولا تصل النشر.

### التراجع

```bash
# (أ) الشيفرةُ وحدها — والقاعدةُ لم تتغيّر
git checkout <الالتزام السابق>
docker compose build && docker compose up -d

# (ب) هجرةٌ غيّرت المخطَّط ⇒ القاعدةُ ترجع كذلك
docker compose stop app worker
# استرجع النسخةَ التي أُخذت قبل التحديث (§٥)
git checkout <الالتزام السابق>
docker compose build && docker compose up -d
```

> **الهجراتُ لا تُعكَس آليًّا.** ولهذا النسخةُ قبل كلِّ تحديثٍ ليست احتياطًا
> زائدًا — هي آليّةُ التراجع نفسُها.

### توسيعُ التصيير

```bash
docker compose up -d --scale worker=3       # الخادمُ لا يُمسّ
```

---

## ٧ · المتابعة

| ماذا | كيف |
|---|---|
| حياة | `GET /healthz` ← رخيصٌ، لا يلمس قاعدة |
| جاهزيّة | `GET /readyz` ← القاعدتان والهجراتُ والطابور |
| مقاييس | `GET /app/admin/metrics` ← **يحتاج صلاحيّةَ إدارة** |
| حالةُ الخدمات | `docker compose ps` |
| السجلّ | `docker compose logs -f app worker` |

**وجِّه تنبيهًا خارجيًّا إلى `/readyz`** (UptimeRobot أو ما يشبهه): لا فائدة
من `readyz` لا يسأله أحد. والتنبيهُ على `/healthz` وحده يقول إن العمليّةَ
حيّة ولا يقول إنها تخدم.

**و`/readyz` يردّ ٥٠٣ حين لا يكون جاهزًا** — فيسحب الموازِنُ الحركةَ ولا
يقتل الحاوية. أمّا `/healthz` فسقوطُه يعني عمليّةً ميّتةً تستحقّ إعادةَ تشغيل.

---

## ٨ · الأمن التشغيليّ

- `deploy/.env` بصلاحيّة **٦٠٠**، ولا يدخل git (`.gitignore` و`.dockerignore`).
- **لا سرَّ في `environment:`** داخل `docker-compose.yml` — يُقرأ بـ
  `docker inspect` لأيِّ مستخدمٍ في مجموعة docker. الأسرارُ في `env_file` وحده.
- جدارُ الحماية: افتح ٨٠ و٤٤٣ فقط. ولا تفتح ٨٠٨٠ للخارج.
- SSH بمفتاحٍ لا بكلمة مرور.
- حدِّث النظامَ المضيف دوريًّا؛ الصورةُ تُعاد بناؤها مع كلِّ تحديث.
- افحص الصورةَ قبل النشر: `trivy image falah:latest` (لم يُجرَ بعد).

---

## ٩ · حين يقع خلل

| العَرَض | الفحص | الغالب |
|---|---|---|
| `readyz` ٥٠٣ | `docker compose logs app` | هجرةٌ معلّقة أو قاعدةُ محتوًى مفقودة |
| صادراتٌ عالقة `queued` | `docker compose ps worker` | العاملُ متوقّفٌ أو `unhealthy` |
| «فشل الاتصال» في التطبيق | `curl https://<نطاق>/healthz` | DNS أو الشهادة |
| لا شهادة | `docker compose logs proxy` | ٨٠ مغلقٌ أو DNS لم ينتشر |
| دخولٌ يفشل والكلمةُ صحيحة | ترويسةُ `Set-Cookie` | `FALAH_SECURE=1` بلا HTTPS |
| القرصُ امتلأ | `docker system df` | صادراتٌ قديمة أو نسخٌ متراكمة |

---

## ١٠ · قائمةٌ لأوّل نشر

- [ ] DNS يشير للخادم (`dig +short`)
- [ ] ٨٠ و٤٤٣ مفتوحان
- [ ] `deploy/.env` مملوءٌ وصلاحيّتُه ٦٠٠
- [ ] `FALAH_SECRET_KEY` عشوائيٌّ ومحفوظٌ خارج الخادم
- [ ] `docker compose up -d` والخدماتُ الأربعُ `healthy`
- [ ] `readyz` ← `ready: true`
- [ ] `make db-safe-migrate` ← لا هجرةَ معلّقة
- [ ] `make db-restore-test` ← نجح
- [ ] شهادةُ HTTPS سارية
- [ ] `/privacy` و`/terms` يُفتحان **بلا حساب**
- [ ] حسابٌ تجريبيّ: تسجيل ← دخول ← بطاقة ← تصدير
- [ ] تنبيهٌ خارجيٌّ على `/readyz`
- [ ] نسخةٌ أُخرجت خارج الخادم
