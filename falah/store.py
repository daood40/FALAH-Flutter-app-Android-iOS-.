"""قاعدة بيانات التطبيق — المستخدمون ومشاريعهم، منفصلةً عن قاعدة المحتوى.

مبدأ الفصل: `falah.db` نصوصٌ موثّقة تُقرأ ولا تُكتب، و`app.db` بيانات
المستخدمين تُكتب ولا تمسّ النصوص. لا جدول هنا يحفظ نصَّ آيةٍ أو حديث —
يحفظ *إشارةً* إليه وبصمته، فيبقى النصّ في مصدره الواحد.
"""
import os, sqlite3, time

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users(
  id         INTEGER PRIMARY KEY,
  email      TEXT UNIQUE NOT NULL,
  name       TEXT,
  watermark  TEXT,                       -- علامة القناة على البطاقة
  pw_hash    BLOB NOT NULL,
  pw_salt    BLOB NOT NULL,
  pw_iter    INTEGER NOT NULL,
  status     TEXT NOT NULL DEFAULT 'active',   -- active | suspended
  verified_at INTEGER,                    -- وقت تأكيد البريد، إن أُكِّد
  created_at INTEGER NOT NULL,
  last_login INTEGER
);

CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY,           -- يُحفظ مجزَّأً: تسريب القاعدة لا يمنح دخولًا
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  seen_at    INTEGER,
  agent      TEXT
);
CREATE INDEX IF NOT EXISTS ix_sess_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS projects(
  id         INTEGER PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title      TEXT NOT NULL,
  kind       TEXT NOT NULL DEFAULT 'series',   -- card | series | video
  skin       TEXT NOT NULL DEFAULT 'parch',
  ratio      TEXT NOT NULL DEFAULT 'square',
  watermark  TEXT,
  note       TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  archived   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_proj_user ON projects(user_id, archived, updated_at DESC);

CREATE TABLE IF NOT EXISTS project_items(
  id         INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  pos        INTEGER NOT NULL,
  kind       TEXT NOT NULL,              -- quran | hadith | enc
  ref        TEXT NOT NULL,              -- JSON: موضع النصّ في قاعدة المحتوى
  fp         TEXT NOT NULL,              -- بصمة النصّ وقت الإضافة — قفل المصدر
  checks     TEXT,                       -- "25/25" وقت الإضافة
  added_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_item_proj ON project_items(project_id, pos);

CREATE TABLE IF NOT EXISTS exports(
  id         INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  fmt        TEXT NOT NULL,              -- png | mp4 | carousel
  path       TEXT NOT NULL,
  ratio      TEXT, skin TEXT,
  checks     TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_exp_user ON exports(user_id, created_at DESC);

-- سجلٌّ لما جرى: مَن أنشأ ومتى دخل وماذا صدَّر. للمساءلة لا للتتبّع.
CREATE TABLE IF NOT EXISTS events(
  id      INTEGER PRIMARY KEY,
  user_id INTEGER,
  action  TEXT NOT NULL,
  detail  TEXT,
  at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ev_user ON events(user_id, at DESC);

-- حدُّ المحاولات: مفتاحٌ (فعل + هدف) وعدّادٌ في نافذةٍ زمنية
CREATE TABLE IF NOT EXISTS throttle(
  key   TEXT PRIMARY KEY,
  count INTEGER NOT NULL,
  start INTEGER NOT NULL
);

-- ═══════════ الاشتراك والحصص ═══════════
-- خطّةٌ واحدة نافذة لكل مستخدم. المزوّد يُسجَّل كما هو (آبل، جوجل، بطاقة،
-- منحة، إحالة) فيُعرف من أين جاء الحقّ، ويُلغى من حيث جاء.
CREATE TABLE IF NOT EXISTS subscriptions(
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan        TEXT NOT NULL,                    -- free | creator | studio
  status      TEXT NOT NULL,                    -- active | grace | expired | refunded | canceled
  provider    TEXT NOT NULL,                    -- apple | google | card | grant | referral
  provider_id TEXT,                             -- المعرّف الأصلي عند المزوّد
  period      TEXT,                             -- month | year | days
  started_at  INTEGER NOT NULL,
  expires_at  INTEGER,                          -- NULL = بلا انتهاء (المجاني)
  renews      INTEGER NOT NULL DEFAULT 0,       -- هل يُجدَّد تلقائيًّا عند المزوّد
  canceled_at INTEGER,
  note        TEXT,
  created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sub_user ON subscriptions(user_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS ix_sub_prov ON subscriptions(provider, provider_id)
  WHERE provider_id IS NOT NULL;

-- سجلّ الإيصالات كما وردت من المتجر — لا يُعدَّل، ويُرجع إليه عند النزاع
CREATE TABLE IF NOT EXISTS receipts(
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  provider    TEXT NOT NULL,
  provider_id TEXT,
  kind        TEXT NOT NULL,                    -- purchase | renew | cancel | refund | expire
  payload     TEXT,                             -- الإيصال كما ورد
  at          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_rc_user ON receipts(user_id, at DESC);

-- الاستهلاك: سطرٌ لكل مستخدمٍ في كل شهرٍ لكل نوعِ عمل
CREATE TABLE IF NOT EXISTS usage(
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  period  TEXT NOT NULL,                        -- YYYY-MM
  metric  TEXT NOT NULL,                        -- cards | videos | projects
  used    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(user_id, period, metric)
);

-- ═══════════ الإحالات ═══════════
CREATE TABLE IF NOT EXISTS referral_codes(
  code       TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_rc_owner ON referral_codes(user_id);

-- إحالةٌ واحدة لكل مدعوٍّ أبدًا. المكافأة لا تُصرف عند التسجيل بل عند
-- أول عملٍ حقيقيّ — فلا يُكافأ حسابٌ فارغ.
CREATE TABLE IF NOT EXISTS referrals(
  id           INTEGER PRIMARY KEY,
  code         TEXT NOT NULL,
  referrer_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invitee_id   INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  status       TEXT NOT NULL DEFAULT 'pending', -- pending | qualified | rewarded | rejected
  reason       TEXT,                            -- سبب الرفض إن رُفض
  created_at   INTEGER NOT NULL,
  qualified_at INTEGER,
  rewarded_at  INTEGER
);
CREATE INDEX IF NOT EXISTS ix_ref_by ON referrals(referrer_id, status);

-- ═══════════ استعادة كلمة المرور وتأكيد البريد ═══════════
-- الرمز يُخزَّن مجزَّأً: تسريب القاعدة لا يمنح استعادة
CREATE TABLE IF NOT EXISTS tokens(
  token_hash TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL,                     -- reset | verify
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at    INTEGER
);
CREATE INDEX IF NOT EXISTS ix_tok_user ON tokens(user_id, kind);

-- ═══════════ طابور المهامّ الثقيلة ═══════════
-- التصيير يستغرق ثوانيَ (بطاقةٌ ≈ ٣ث، مقطعٌ ≈ ٢٦ث)، فلا يُحبس فيه طلبُ
-- المستخدم. يوضع العمل هنا، ويردّ الخادم فورًا برقمه، ويتولّاه عاملٌ
-- منفصل. الجدول نفسه هو الطابور — لا وسيطَ خارجيّ ما لم يثبت القياس لزومه.
CREATE TABLE IF NOT EXISTS jobs(
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL,                  -- export | video
  payload      TEXT NOT NULL,                  -- JSON: ما يلزم لإعادة بناء العمل
  state        TEXT NOT NULL DEFAULT 'queued', -- queued|running|done|failed|canceled
  attempts     INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 2,
  progress     INTEGER NOT NULL DEFAULT 0,     -- 0..100
  step         TEXT,                           -- وصفٌ عربيّ لما يجري الآن
  error        TEXT,
  result       TEXT,                           -- JSON: نفس ردّ المسار القديم
  worker       TEXT,
  reserved     TEXT,                           -- JSON: الحصّة المحجوزة، تُردّ عند الفشل
  created_at   INTEGER NOT NULL,
  started_at   INTEGER,
  finished_at  INTEGER,
  heartbeat    INTEGER                         -- نبضٌ لكشف العامل المتوقّف
);
CREATE INDEX IF NOT EXISTS ix_jobs_queue ON jobs(state, created_at);
CREATE INDEX IF NOT EXISTS ix_jobs_user  ON jobs(user_id, created_at DESC);
"""


HERE   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DB = os.environ.get("FALAH_APP_DB", os.path.join(HERE, "app.db"))

def connect(path=None):
    c = sqlite3.connect(path or APP_DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init(path=None):
    c = connect(path)
    c.executescript(SCHEMA)
    c.commit()
    return c

def now():
    return int(time.time())

def log(c, user_id, action, detail=None):
    c.execute("INSERT INTO events(user_id,action,detail,at) VALUES(?,?,?,?)",
              (user_id, action, detail, now()))
