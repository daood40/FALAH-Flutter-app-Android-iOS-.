# عقد الـAPI

> مولَّدٌ من الشيفرة بـ`python3 api_contract.py`. لا يُحرَّر باليد.

## طبقة المحتوى — قراءةٌ عامّة

| METHOD | PATH | AUTH | INPUT | OUTPUT | ERRORS |
|---|---|---|---|---|---|
| GET | `/audio` | عامّ | surah, ayah, reciter | روابط التلاوة | 400 |
| GET | `/card` | عامّ | kind وموضع النصّ | البطاقة بعد ٢٥ فحصًا | 400 · 404 · محجوبٌ بسببه |
| GET | `/chapter/hadiths` | عامّ | book, chapter | أحاديث الباب | 400 |
| GET | `/chapters` | عامّ | book | الأبواب | 400 |
| GET | `/enc` | عامّ | id | من الموسوعة | 404 |
| GET | `/enc/search` | عامّ | q | نتائج | 400 |
| GET | `/hadith` | عامّ | book, no | الحديث | 400 · 404 |
| GET | `/hadith/search` | عامّ | q, card_only | نتائج | 400 |
| GET | `/health` | عامّ | — | إحصاء القاعدة | — |
| GET | `/options` | عامّ | — | مادّة الوكيل | — |
| GET | `/quran/ayah` | عامّ | surah, ayah, to, tafsir, translation | الآية بسياقها | 400 · 404 |
| GET | `/quran/search` | عامّ | q, card_only | نتائج | 400 استعلامٌ فارغ |
| GET | `/reciters` | عامّ | — | القرّاء برواياتهم | — |
| GET | `/review` | عامّ | kind | المحجوب وسببه | — |
| GET | `/series` | عامّ | topic, count | سلسلةٌ مقترحة | 400 |
| GET | `/sources` | عامّ | — | المصادر وحال تراخيصها | — |
| GET | `/template` | عامّ | ref | قالبٌ واحد | 404 |
| GET | `/templates` | عامّ | kind, limit | قوالب جاهزة | 400 |
| GET | `/topics` | عامّ | — | فهرس الموضوعات | — |
| GET | `/topics/{id}` | عامّ | kind, limit | مقترحات الموضوع | 404 |
| GET | `/verify` | عامّ | text, surah, ayah | نتيجة الفحوص | 400 |
| GET | `/healthz` | عامّ | — | {live} | — |
| GET | `/readyz` | عامّ | — | {ready, content_db, app_db, queue, pending_migrations} | 503 غير جاهز |
| GET | `/privacy` | عامّ | — | سياسة الخصوصيّة (HTML) | 404 غير منشورة |
| GET | `/terms` | عامّ | — | شروط الاستخدام (HTML) | 404 غير منشورة |

## التطبيق — قراءة

| METHOD | PATH | AUTH | INPUT | OUTPUT | ERRORS |
|---|---|---|---|---|---|
| GET | `/app/admin/audit` | صلاحية audit.list | limit, offset, action, actor, result | {total, events[]} — وقراءتُه نفسُها تُسجَّل | 401 · 403 |
| GET | `/app/admin/metrics` | صلاحية metrics.read | — | {uptime_s, counters[], timers[], queue} — لقطةٌ من الذاكرة. الوسومُ معدودةٌ مسبقًا (مسارٌ مُعمَّمٌ · طريقةٌ · رمز) فلا معرّفَ مستخدمٍ ولا طلبٍ فيها | 401 · 403 |
| GET | `/app/admin/roles` | صلاحية user_role.read | — | {roles, assignable, permissions} | 401 · 403 |
| GET | `/app/admin/users` | صلاحية user.list | limit, offset, role | {total, users[]} — أعمدةٌ مسمّاة بلا اشتقاقِ كلمةِ مرورٍ ولا ملح | 401 · 403 |
| GET | `/app/admin/users/{id}` | صلاحية user.read | — | {user} | 401 · 403 · 404 |
| GET | `/app/config` | عامّ | — | {invite_required, origin} | — |
| GET | `/app/entitlements` | جلسة | — | الخطّة والحدود والمستهلَك | 401 |
| GET | `/app/exports` | جلسة | — | آخر ٥٠ تصديرًا | 401 |
| GET | `/app/file` | جلسة+ملكية | p | الملفّ نفسه | 401 · 404 خارج مجلّدك |
| GET | `/app/jobs` | جلسة | — | مهامّه وإحصاء الطابور والحدود | 401 |
| GET | `/app/jobs/{id}` | جلسة+ملكية | — | {state, progress, step, result, error, retry_after} | 401 · 400 ليست مهمّتك |
| GET | `/app/limits` | جلسة | — | حدود الطابور والموارد | 401 |
| GET | `/app/me` | عامّ | الكعكة | {user} أو {user:null} — و`user.role` **قراءةٌ فقط** | — |
| GET | `/app/plans` | عامّ | — | الخطط وما لا يُباع | — |
| GET | `/app/projects` | جلسة | — | مشاريع صاحب الجلسة | 401 |
| GET | `/app/projects/{id}` | جلسة+ملكية | — | المشروع بعناصره مفحوصةً الآن | 401 · 400 ليس مشروعك |
| GET | `/app/publish/accounts` | مصادَق | — | الحساباتُ المربوطة — بلا أسرار، تلميحٌ من أربعةِ محارف | — |
| GET | `/app/publish/attempts` | مصادَق | — | سجلُّ محاولات النشر — بلا أسرار | — |
| GET | `/app/publish/providers` | مصادَق | — | كلُّ منصّةٍ بحالتها: ready | not_implemented | — |
| GET | `/app/referrals` | جلسة | — | رمز الإحالة وحصادها | 401 |
| GET | `/app/schedules` | جلسة | — | {schedules[]} | 401 |
| GET | `/app/schedules/{id}` | جلسة · مالكٌ | — | {schedule, runs[]} — تاريخُ التنفيذ لا آخرُ قيمة | 401 · 404 |

## التطبيق — كتابة

| METHOD | PATH | AUTH | INPUT | OUTPUT | ERRORS |
|---|---|---|---|---|---|
| POST | `/app/account/delete` | جلسة+CSRF | confirm='حذف' | {ok, gone} | 400 بلا تأكيد |
| POST | `/app/admin/users/role` | صلاحية user_role.update | user, role, reason | {user} — وتُنهى جلساتُ الهدف | 400 دورٌ مجهول · 403 حارسُ التسلسل · 404 |
| POST | `/app/admin/users/status` | صلاحية user.update | user, status, reason | {user} | 400 · 403 · 404 |
| POST | `/app/agent` | جلسة+CSRF | answers | السؤال التالي أو الخطّة | 404 |
| POST | `/app/agent/build` | جلسة+CSRF | answers | 201 {project, added} | 400 |
| POST | `/app/export` | جلسة+ملكية | project | **202** {job, cards} — ويعيد المهمّة القائمة إن كان الطلب مكرَّرًا | 400 فارغ/حدّ · 409 محجوب أو منحرف |
| POST | `/app/items/accept-drift` | جلسة+ملكية | project, id | {ok} | 400 |
| POST | `/app/items/add` | جلسة+ملكية | project, kind, ref | 201 {id} | 400 محجوبٌ أو مكرَّر |
| POST | `/app/items/remove` | جلسة+ملكية | project, id | {ok} | 400 |
| POST | `/app/items/reorder` | جلسة+ملكية | project, order[] | {ok} | 400 |
| POST | `/app/jobs/cancel` | جلسة+ملكية | id | {job} | 400 بدأت فلا تُلغى |
| POST | `/app/login` | عامّ+CSRF | email, password | {user} + كعكة | 400 بيانات خاطئة · محاولاتٌ كثيرة |
| POST | `/app/logout` | جلسة+CSRF | — | {ok} | — |
| POST | `/app/password` | جلسة+CSRF | old, new | {ok} + إنهاء الجلسات | 400 |
| POST | `/app/password/forgot` | عامّ+CSRF | email | {ok} (لا يكشف وجود الحساب) | — |
| POST | `/app/password/reset` | رمز+CSRF | token, password | {ok} | 400 رمزٌ منتهٍ |
| POST | `/app/profile` | جلسة+CSRF | name, watermark | {user} | 401 |
| POST | `/app/projects/create` | جلسة+CSRF | title, kind, skin, ratio, watermark | 201 {id} | 400 حصّة المشاريع |
| POST | `/app/projects/delete` | جلسة+ملكية | id | {ok} | 400 |
| POST | `/app/projects/update` | جلسة+ملكية | id + الحقول | {ok} | 400 |
| POST | `/app/publish/connect` | مصادَق | provider, secret, label | الحسابُ المربوط + تلميح | 400 منصّةٌ غيرُ منفَّذةٍ أو اعتمادٌ قصير |
| POST | `/app/publish/disconnect` | مالك | account | {disconnected} | 404 ليس حسابَك |
| POST | `/app/register` | عامّ+CSRF | email, password, name, watermark, invite, ref | 201 {user, entitlements} | 400 · 403 دعوة |
| POST | `/app/schedules/create` | جلسة · مالكُ المشروع | project, kind, title, recurrence, tz, at_minute, day_of | {schedule} — الجدولةُ في الخادم لا في العميل، و`tz` اسمُ منطقةٍ لا إزاحةٌ تنزاح بالتوقيت الصيفيّ | 400 · 401 · 404 |
| POST | `/app/schedules/delete` | جلسة · مالك | id | {deleted} | 401 · 404 |
| POST | `/app/schedules/status` | جلسة · مالك | id, status=active|paused | {schedule} — والاستئنافُ من الآن لا من الماضي | 400 · 401 · 404 |
| POST | `/app/schedules/update` | جلسة · مالك | id + الحقولُ المعدَّلة | {schedule} — ويُعاد حسابُ الاستحقاق | 400 · 401 · 404 |
| POST | `/app/subscription/cancel` | جلسة+CSRF | — | {subscription, entitlements} | 400 |
| POST | `/app/subscription/grant` | صلاحية subscription.grant | user, plan, days, note | {subscription} | 401 · 403 |
| POST | `/app/subscription/store-event` | جلسة+CSRF | provider, event | {subscription} بعد سؤال المتجر | **402** إيصالٌ لم يثبت |
| POST | `/app/verify/confirm` | رمز+CSRF | token | {ok} | 400 |
| POST | `/app/verify/request` | جلسة+CSRF | — | {ok} | 401 |
| POST | `/app/video` | جلسة+ملكية | project, item, reciter | **202** {job} | 400 · 404 · 409 |

## ملاحظاتٌ تحكم كل المسارات

- كل طلب كتابةٍ يشترط ترويسة `X-FALAH: 1`، و`Origin` المطابق إن حُدِّد `FALAH_ORIGIN`.
- الجلسة كعكة `falah_sid` — HttpOnly · SameSite=Strict · Secure خلف HTTPS.
- «ملكية» تعني أن الصفَّ يُقرأ بشرط `user_id` — رقمٌ مخمَّن لا يكشف عمل غيره.
- كل مسارٍ يُقرَّر إذنُه في `falah/authz.py` بصلاحيةٍ اسمُها `<مورِد>.<فعل>` ونطاقٍ (OWNER · SELF · ANY). ولا اسمَ دورٍ في شرطٍ واحد.
- **`X-FALAH-ADMIN` أُلغي في P1.2**: الإدارةُ بدورٍ على حسابٍ حقيقيّ. وأوّلُ `super_admin` يُصنع بـ`python3 -m falah.roles grant <بريد> super_admin`.
- الأفعالُ الحسّاسة تُسجَّل في `audit_logs` — يُلحق ولا يُعدَّل ولا يُحذف، ولا سرَّ فيه.
- الخطأ الداخليّ يردّ `{"error": "خطأ داخلي"}` ويُسجَّل تفصيله عندنا؛ ونصّ الاستثناء لا يُرسل.
- `/app/export` و`/app/video` **لا تُصيّران داخل الطلب**: تردّان ٢٠٢ وتُستطلع المهمّة على `/app/jobs/<id>`.

