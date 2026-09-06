# دفعُ المشروع إلى مستودعك — من هاتفك

## لماذا لم أدفعه أنا

حاولتُ، وسُدَّ الطريقان:

```
GitHub API   → 403  "GitHub access to this repository is not enabled for this session"
git push     → "Invalid username or token"
```

الرمزُ المتاح لي في هذه الجلسة **مقصورٌ على مستودعاتٍ مُلحَقةٍ بها مسبقًا**،
ومستودعُك ليس منها. وهذا ليس عطبًا في الشيفرة ولا في مستودعك — قيدُ بيئةٍ.
ولن أدّعيَ أنني دفعتُه وأنا لم أفعل.

**وأمامك طريقان: الأوّل أسرع إن أتاحه تطبيقُك، والثاني يعمل قطعًا.**

---

## الطريقُ الأوّل: تُلحِق المستودعَ بالجلسة

رسالةُ الخطأ نفسُها تقول: `Use add_repo to request access`. فإن وجدتَ في
تطبيق Claude خيارًا لإضافة مستودع GitHub أو منح صلاحيّةٍ عليه، فعّله على
`daood40/FALAH-Flutter-app-Android-iOS-` ثم قل لي «أُلحق» — وأدفعه في دقيقة.

وإن لم تجد الخيار، فالطريقُ الثاني.

---

## الطريقُ الثاني: Termux — يعمل قطعًا

وأنت محتاجٌ إلى Termux على كلِّ حالٍ لتوليد مفتاح الرفع، فلا تخسر شيئًا.

### ١ · ثبّت Termux

من **F-Droid** لا من متجر Play (نسخةُ Play قديمةٌ ومهجورة):
<https://f-droid.org/packages/com.termux/>

### ٢ · جهّزه

```bash
pkg update && pkg upgrade -y
pkg install git -y
termux-setup-storage        # يطلب إذنَ الوصول إلى التخزين — اقبله
```

### ٣ · انقل الحزمة

نزّل `falah.bundle` من هذه المحادثة (٢٫٩ م.ب)، ثم:

```bash
cd ~
cp /sdcard/Download/falah.bundle .
ls -lh falah.bundle          # تأكّد أنها وصلت
```

### ٤ · فُكَّها — وفيها التاريخُ كلُّه

```bash
git clone falah.bundle FALAH
cd FALAH
git log --oneline | head -5
```

يجب أن ترى ٣١ التزامًا و٢٩٥ ملفًّا. الحزمةُ ليست نسخةً مسطَّحةً من الملفّات
— هي المستودعُ بتاريخه كاملًا.

### ٥ · اربطه بمستودعك وادفعه

**انسخ الرابطَ من زرِّ `Code` الأخضر في صفحة مستودعك** — لا تكتبه يدويًّا،
فالاسمُ فيه شرطاتٌ ونقطةٌ يسهل الخطأُ فيها:

```bash
git remote remove origin
git remote add origin https://github.com/daood40/<الاسم-كما-نسختَه>.git
git branch -M main
git push -u origin main
```

سيسألك عن اسم المستخدم وكلمة المرور:

- **Username:** `daood40`
- **Password:** ⚠ **ليست كلمةَ مرور حسابك** — GitHub لم يعد يقبلها.
  تحتاج **Personal Access Token**.

### ٦ · رمزُ الدخول (مرّةً واحدة)

من الهاتف: `github.com` ← صورتُك ← **Settings** ← **Developer settings** ←
**Personal access tokens** ← **Tokens (classic)** ← **Generate new token**

- **Note:** `termux-falah`
- **Expiration:** ٩٠ يومًا
- **Scopes:** ✅ **`repo` وحدَه** — لا تعطِه أكثر ممّا يلزم

انسخ الرمزَ فورًا (لن يظهر ثانيةً)، والصقه مكانَ كلمة المرور.

> ولئلّا يسألك في كلِّ مرّة:
> ```bash
> git config --global credential.helper store
> ```
> يحفظه في `~/.git-credentials` على هاتفك بنصٍّ صريح. مقبولٌ لجهازك، ولا
> تفعله على جهازٍ يشاركك فيه أحد.

---

## إن اشتكى من تعارض

لو أنشأتَ المستودعَ ومعه `README` أو `.gitignore`، فسيرفض الدفعَ. والحلُّ
**دمجُ ما هناك** لا محوُه:

```bash
git pull origin main --allow-unrelated-histories
git push -u origin main
```

> ❌ **ولا تستعمل `git push --force`** إلا إن كنتَ متأكّدًا أنّ المستودعَ
> فارغٌ تمامًا: القوّةُ تمحو ما هناك بلا رجعة.

---

## بعد الدفع — أهمُّ خطوة

افتح تبويب **Actions** في مستودعك. سيبدأ خطُّ التكامل وحدَه:

| الوظيفة | ماذا تفعل |
|---|---|
| `static` | ثغراتٌ · lint · أنواعٌ · أسرارٌ · عقدُ API |
| `tests` | ١٤٦٦ فحصًا للخادم |
| `flutter` | تحليلٌ · ٧٧ اختبارًا على خادمٍ حيّ · بناءُ APK |
| `build` | صورةُ الحاوية + دخانٌ عليها |
| `QUALITY_GATE` | الحكمُ النهائيّ |

وحين تنتهي، انزل إلى **Artifacts** أسفل صفحة التشغيلة وستجد:

**`falah-android-staging-apk`** ← نزّله، فُكَّ الـzip، وثبّت الـAPK على
هاتفك. **هذا أوّلُ تشغيلٍ حقيقيٍّ للتطبيق على جهازك.**

> و`falah-android-production-aab` لن يظهر بعد — يحتاج أسرارَ التوقيع.
> راجع [`RELEASE_SIGNING.md`](RELEASE_SIGNING.md).

---

## ⚠ قبل أن تجعل المستودعَ عامًّا

**اجعله خاصًّا (Private) الآن.** وقبل أيِّ فتحٍ للعموم:

1. احسم رخصةَ التفسير الميسّر (§٤ في `LAUNCH_CHECKLIST.md`).
2. تأكّد أنّ `deploy/.env` ليس فيه — `git ls-files | grep .env` يجب أن
   يعيد `deploy/.env.example` **فقط**.
3. أضف ملفَّ رخصةٍ للشيفرة نفسِها.
