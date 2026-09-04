# كتالوجُ الصلاحيات

> مولَّدٌ من الشيفرة بـ`python3 perms_report.py`. **لا يُحرَّر باليد.**

**38 صلاحيةً ⟷ 38 زوجًا (مورِد، فعل)** — تقابلٌ تامٌّ في الاتجاهين. واسمُ الصلاحية هو الزوجُ نفسُه، فلا يمكن أن توجد عمليةٌ بلا صلاحية.

## النطاقات

| النطاق | ما يعنيه |
|---|---|
| `PUBLIC` | بلا جلسةٍ ولا مورِد — والمجهولُ يملك الصلاحية |
| `AUTH` | جلسةٌ فقط — لا رقمَ مورِدٍ يأتي من الطلب |
| `SELF` | صاحبُ الجلسة نفسُه لا غير |
| `OWNER` | **مالكٌ مقروءٌ من القاعدة** يُقارَن بصاحب الجلسة |
| `ANY` | لا يقيّده نطاق — والصلاحيةُ الإدارية هي الحاسمة، وفوقها حارسُ التسلسل |

## الجدول

«أدنى دورٍ يملكها» يكفي: التسلسلُ محسوبٌ بالضمّ (`anonymous ⊂ user ⊂ moderator ⊂ admin ⊂ super_admin`)، فما يملكه الأدنى يملكه من فوقه.

**وكلُّ منعٍ يُسجَّل `security.denied`** أيًّا كان المورِد — فلا يُعاد في كل سطر. وعمودُ «تُسجَّل؟» يذكر أحداثَ **النجاح** لهذه العملية بعينها.

| الصلاحية | المورِد | الفعل | النطاق | أدنى دورٍ يملكها | تُسجَّل؟ | حدُّ معدّل | المسار |
|---|---|---|---|---|---|---|---|
| `account.delete` | account | delete | `SELF` | `user` | ✔ `account.deleted` | — | `POST /app/account/delete` |
| `account.update` | account | update | `SELF` | `user` | ✔ `account.updated` · `password.changed` | — | `POST /app/verify/request` · `POST /app/profile` · `POST /app/password` |
| `agent.create` | agent | create | `AUTH` | `user` | — | — | `POST /app/agent/build` |
| `agent.read` | agent | read | `AUTH` | `user` | — | `agent` (قبليّ · لكل مستخدم) | `POST /app/agent` |
| `audit.list` | audit | list | `AUTH` | `moderator` | ✔ `audit.read` | — | `GET /app/admin/audit` |
| `catalogue.read` | catalogue | read | `PUBLIC` | `anonymous` | — | — | `GET /app/config` · `GET /app/plans` · `GET /app/me` |
| `content.list` | content | list | `PUBLIC` | `anonymous` | — | — | — (قاعدةٌ عامّة) |
| `content.read` | content | read | `PUBLIC` | `anonymous` | — | — | — (قاعدةٌ عامّة) |
| `credential.update` | credential | update | `PUBLIC` | `anonymous` | ✔ `password.reset` | — | `POST /app/password/forgot` · `POST /app/password/reset` · `POST /app/verify/confirm` |
| `export.list` | export | list | `AUTH` | `user` | — | — | `GET /app/exports` |
| `export_file.download` | export_file | download | `OWNER` | `user` | — | `file` (قبليّ · لكل مستخدم) | `GET /app/file` |
| `job.cancel` | job | cancel | `OWNER` | `user` | — | — | `POST /app/jobs/cancel` |
| `job.list` | job | list | `AUTH` | `user` | — | — | `GET /app/jobs` |
| `job.read` | job | read | `OWNER` | `user` | — | — | `GET /app/jobs/{id}` |
| `limits.read` | limits | read | `AUTH` | `user` | — | — | `GET /app/limits` |
| `project.create` | project | create | `AUTH` | `user` | ✔ `project.created` | — | `POST /app/projects/create` |
| `project.delete` | project | delete | `OWNER` | `user` | ✔ `project.deleted` | — | `POST /app/projects/delete` |
| `project.list` | project | list | `AUTH` | `user` | — | — | `GET /app/projects` |
| `project.read` | project | read | `OWNER` | `user` | — | — | `GET /app/projects/{id}` |
| `project.render` | project | render | `OWNER` | `user` | ✔ `export.created` · `export.completed` · `export.failed` | `export`/`video` (داخل المعالِج — يُعدّ العملَ المقبول) | `POST /app/export` · `POST /app/video` |
| `project.update` | project | update | `OWNER` | `user` | — | — | `POST /app/projects/update` |
| `project_item.create` | project_item | create | `OWNER` | `user` | — | — | `POST /app/items/add` |
| `project_item.delete` | project_item | delete | `OWNER` | `user` | — | — | `POST /app/items/remove` |
| `project_item.update` | project_item | update | `OWNER` | `user` | — | — | `POST /app/items/reorder` · `POST /app/items/accept-drift` |
| `referral.read` | referral | read | `SELF` | `user` | — | — | `GET /app/referrals` |
| `registration.create` | registration | create | `PUBLIC` | `anonymous` | ✔ `account.created` | `register` (قبليّ · لكل عنوان) | `POST /app/register` |
| `service.read` | service | read | `PUBLIC` | `anonymous` | — | — | — (قاعدةٌ عامّة) |
| `session.create` | session | create | `PUBLIC` | `anonymous` | ✔ `login.success` · `login.failure` | `login` (قبليّ · لكل عنوان) | `POST /app/login` |
| `session.delete` | session | delete | `PUBLIC` | `anonymous` | ✔ `logout` | — | `POST /app/logout` |
| `subscription.grant` | subscription | grant | `ANY` | `admin` | ✔ `subscription.granted` | — | `POST /app/subscription/grant` |
| `subscription.read` | subscription | read | `SELF` | `user` | — | — | `GET /app/entitlements` |
| `subscription.update` | subscription | update | `SELF` | `user` | ✔ `subscription.canceled` · `subscription.store_event` | — | `POST /app/subscription/cancel` · `POST /app/subscription/store-event` |
| `unknown.read` | unknown | read | `AUTH` | `user` | — | — | — (قاعدةٌ عامّة) |
| `user.list` | user | list | `AUTH` | `moderator` | — | — | `GET /app/admin/users` |
| `user.read` | user | read | `ANY` | `moderator` | — | — | `GET /app/admin/users/{id}` |
| `user.update` | user | update | `ANY` | `admin` | ✔ `user.suspended` · `user.reactivated` | — | `POST /app/admin/users/status` |
| `user_role.read` | user_role | read | `AUTH` | `admin` | — | — | `GET /app/admin/roles` |
| `user_role.update` | user_role | update | `ANY` | `super_admin` | ✔ `role.changed` | — | `POST /app/admin/users/role` |

## الأدوار

| الدور | عددُ الصلاحيات | ما يزيده على ما قبله |
|---|---:|---|
| `anonymous` | 8 | `catalogue.read` · `content.list` · `content.read` · `credential.update` · `registration.create` · `service.read` · `session.create` · `session.delete` |
| `user` | 31 | `account.delete` · `account.update` · `agent.create` · `agent.read` · `export.list` · `export_file.download` · `job.cancel` · `job.list` · `job.read` · `limits.read` · `project.create` · `project.delete` · `project.list` · `project.read` · `project.render` · `project.update` · `project_item.create` · `project_item.delete` · `project_item.update` · `referral.read` · `subscription.read` · `subscription.update` · `unknown.read` |
| `moderator` | 34 | `audit.list` · `user.list` · `user.read` |
| `admin` | 37 | `subscription.grant` · `user.update` · `user_role.read` |
| `super_admin` | 38 | `user_role.update` |

## ما يفحصه هذا الجدولُ آليًّا

- **لا صلاحيةَ ميتة**: كلُّ صلاحيةٍ لها زوجٌ في `POLICY` ومسارٌ أو قاعدةٌ عامّة.
- **لا عمليةَ بلا صلاحية**: كلُّ زوجٍ في `POLICY` له صلاحيةٌ باسمه.
- **لا صلاحيةَ لا يبلغها دور**: كلُّ صلاحيةٍ في حزمةِ دورٍ واحدٍ على الأقلّ.

وهذه الثلاثةُ ثوابتُ بوّابةٍ في `invariants.py` (`NEW_OPERATION_WITHOUT_PERMISSION`) — لا مراجعةٌ بشرية.

