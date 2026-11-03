-- ============================================================
-- 双语电子书生成系统 · SQLite DDL + 种子数据
-- 项目名：双语电子书生成系统（Bilingual E-Book Studio）
-- 版本：v1.6（与设计文档 v1.6 对齐）
-- 生成日期：2026-11-02
-- 依赖：SQLite >= 3.35
-- 用法：sqlite3 book.db < database.sql
-- ------------------------------------------------------------
-- 注意：PRAGMA foreign_keys 是「按连接」生效的，不是写进库文件的属性。
--      本脚本只对当前连接开启；应用侧必须在每个连接上执行，
--      SQLAlchemy 示例：
--        from sqlalchemy import event
--        @event.listens_for(engine, "connect")
--        def _fk_on(dbapi_conn, _):
--            dbapi_conn.execute("PRAGMA foreign_keys=ON")
--      WAL 模式则会持久化到库文件。
-- ============================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- 建表语句（11 张表）
-- ============================================================

-- 1. 用户表（含管理员角色、积分余额、封号原因）
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    nickname      TEXT,
    points        INTEGER NOT NULL DEFAULT 50,          -- 积分余额（可扣至负值）
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at DATETIME,
    role          TEXT    NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin')),
    is_active     BOOLEAN NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    ban_reason    TEXT                                  -- 空=正常；'积分风控'=风控自动封号
);

-- 2. 书籍任务表
CREATE TABLE IF NOT EXISTS books (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT    NOT NULL,
    source_ext      TEXT    NOT NULL CHECK (source_ext IN ('txt','epub','pdf')),
    source_lang     TEXT    NOT NULL,
    target_lang     TEXT    NOT NULL,
    engine          TEXT    NOT NULL CHECK (engine IN ('baidu','youdao','deepl','official')),
    status          TEXT    NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','processing','ready','failed')),
    source_path     TEXT,                                -- 上传源文件路径（重试/重解析依赖）
    char_count      INTEGER,                             -- 源文字符数（统计「今日翻译量」）
    progress        INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    cached_segments INTEGER NOT NULL DEFAULT 0,          -- 命中翻译缓存的段数
    epub_path       TEXT,
    pdf_path        TEXT,
    error_msg       TEXT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at      DATETIME,
    finished_at     DATETIME
);

-- 3. 段落表（book 的子表）
CREATE TABLE IF NOT EXISTS segments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id         INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,                    -- 段落序号，从 1 起
    source_text     TEXT    NOT NULL,
    translated_text TEXT,                                -- 失败回退时为 NULL
    is_failed       BOOLEAN NOT NULL DEFAULT 0 CHECK (is_failed IN (0,1)),
    UNIQUE(book_id, seq)
);

-- 4. 翻译缓存表（松耦合，无外键）
--    engine 是缓存键的一部分：不同引擎的译文质量不同，不可跨引擎复用
CREATE TABLE IF NOT EXISTS translation_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_hash     TEXT    NOT NULL,                    -- 原文 MD5（32 位十六进制）
    src_lang        TEXT    NOT NULL,
    tgt_lang        TEXT    NOT NULL,
    engine          TEXT    NOT NULL CHECK (engine IN ('baidu','youdao','deepl','official')),
    translated_text TEXT    NOT NULL,
    hit_count       INTEGER NOT NULL DEFAULT 0 CHECK (hit_count >= 0),
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_hash, src_lang, tgt_lang, engine)
);

-- 5. 积分明细流水表（只增不改）
CREATE TABLE IF NOT EXISTS point_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    delta         INTEGER NOT NULL CHECK (delta <> 0),
    balance_after INTEGER NOT NULL,                      -- 变动后余额快照
    type          TEXT    NOT NULL CHECK (type IN (
                      'checkin','register','translate','feedback_reward',
                      'feedback_penalty','admin_adjust','admin_bulk','risk_penalty')),
    ref_id        INTEGER,                               -- book_id / feedback_id / risk_alert_id
    description   TEXT,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 6. 签到记录表
CREATE TABLE IF NOT EXISTS checkins (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    checkin_date DATE    NOT NULL,                       -- YYYY-MM-DD
    reward       INTEGER NOT NULL CHECK (reward >= 0),
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, checkin_date)
);

-- 7. 系统配置表（键值对）
CREATE TABLE IF NOT EXISTS system_config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 8. 用户反馈表
CREATE TABLE IF NOT EXISTS feedbacks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       TEXT    NOT NULL CHECK (type IN ('bug','suggest','experience','other')),
    title      TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    contact    TEXT,
    status     TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done')),
    reward     INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handled_at DATETIME
);

-- 9. 风控告警表
CREATE TABLE IF NOT EXISTS risk_alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rule       TEXT    NOT NULL CHECK (rule IN ('single','freq','daily')),
    detail     TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','resolved')),
    resolve    TEXT    CHECK (resolve IS NULL OR resolve IN ('unban','confirm')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handled_at DATETIME
);

-- 10. 公告表（独立，无外键）
CREATE TABLE IF NOT EXISTS notices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT    NOT NULL,                         -- maintenance / update / system / 自定义
    title      TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    views      INTEGER NOT NULL DEFAULT 0 CHECK (views >= 0),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 11. 系统日志表（独立，无外键）
CREATE TABLE IF NOT EXISTS logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    level      TEXT    NOT NULL CHECK (level IN ('INFO','WARN','ERROR')),
    module     TEXT    NOT NULL,
    message    TEXT    NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 索引设计
-- ============================================================
-- 注：segments 的 UNIQUE(book_id, seq) 已自带索引，不再重复建 idx_segments_book

CREATE INDEX IF NOT EXISTS idx_books_user_created ON books(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_books_status       ON books(status);
CREATE INDEX IF NOT EXISTS idx_books_user_status  ON books(user_id, status);
CREATE INDEX IF NOT EXISTS idx_point_logs_user_created ON point_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_checkins_date      ON checkins(checkin_date);
CREATE INDEX IF NOT EXISTS idx_feedbacks_status   ON feedbacks(status);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_status ON risk_alerts(status);
CREATE INDEX IF NOT EXISTS idx_notices_active_created ON notices(is_active, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_level_created ON logs(level, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_module        ON logs(module);

-- ============================================================
-- 触发器：notices.updated_at 自动维护
-- ============================================================
CREATE TRIGGER IF NOT EXISTS trg_notices_updated_at
AFTER UPDATE ON notices
FOR EACH ROW
BEGIN
    UPDATE notices SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

-- ============================================================
-- 种子数据
-- ============================================================

-- 系统配置（8 条预置键值）
INSERT INTO system_config (key, value) VALUES
('checkin_reward', '10'),
('register_reward', '50'),
('token_per_point', '1000'),
('official_api_enabled', '1'),
('official_api_key', 'sk-official-xxxxxxxxxxxxx'),
('risk_max_single', '500'),
('risk_max_freq', '10'),
('risk_max_daily', '2000');

-- 种子账号（bcrypt cost=10，已用 bcrypt.checkpw 实测校验通过）
INSERT INTO users (email, password_hash, nickname, points, role, is_active, ban_reason, created_at) VALUES
('admin@book.app',
 '$2b$10$EtbdUyTqBmRdScNsRKgN/.YjAjLNT52H4zQ34qCigwdQVGZURTIRC',
 '管理员', 0, 'admin', 1, NULL, '2026-09-18 08:00:00');

INSERT INTO users (email, password_hash, nickname, points, role, is_active, ban_reason, created_at) VALUES
('demo@book.app',
 '$2b$10$aZHqd5Pa3vTrp26xw02TO.22E.m2rjXr2rOdyQRf2XbLolbn7y4Y2',
 '演示用户', 138, 'user', 1, NULL, '2026-09-20 10:12:00');

-- chen 被风控自动封号（与 risk_alerts #1 对应），管理员可在风控中心解封
INSERT INTO users (email, password_hash, nickname, points, role, is_active, ban_reason, created_at) VALUES
('chen@mail.cn',
 '$2b$10$.R2/Vw1wIDRX79Grro2oeOWRedgjLEJUD1jFSitv5YUV6k3LF81J.',
 '陈叙', 50, 'user', 0, '积分风控', '2026-09-22 11:08:00');

-- ============================================================
-- 示例书 1：status='ready'，官方引擎（消耗积分）
-- 用户：demo@book.app（id=2）
-- ============================================================
INSERT INTO books (id, user_id, title, source_ext, source_lang, target_lang, engine, status,
                   source_path, char_count, progress, cached_segments, epub_path, pdf_path,
                   created_at, started_at, finished_at)
VALUES (1, 2, 'Pride and Prejudice', 'epub', 'en', 'zh', 'official', 'ready',
        '/data/uploads/2/1/source.epub', 6240, 100, 2,
        '/data/output/2/1/pride-and-prejudice.epub',
        '/data/output/2/1/pride-and-prejudice.pdf',
        '2026-09-20 15:42:00', '2026-09-20 15:42:05', '2026-09-20 15:43:19');

INSERT INTO segments (book_id, seq, source_text, translated_text, is_failed) VALUES
(1, 1, 'It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.',
  '凡是有钱的单身汉，总想娶位太太，这已经成了一条举世公认的真理。', 0),
(1, 2, 'However little known the feelings or views of such a man may be on his first entering a neighbourhood, this truth is so well fixed in the minds of the surrounding families, that he is considered as the rightful property of some one or other of their daughters.',
  '不管这样一个人的心情或见解在初进一个地区时多么不为人所知，这条真理却总是牢牢记在周围各家各户的心里，他被看作是他们某位女儿的准财产。', 0),
(1, 3, 'My dear Mr. Bennet, said his lady to him one day, have you heard that Netherfield Park is let at last?',
  NULL, 1),
(1, 4, 'Mr. Bennet replied that he had not.',
  '班纳特先生回答说他还没有听说。', 0),
(1, 5, 'But it is announced by Mrs. Long, for she was there this morning in preference to that poor woman next door, and slipped it in to me, sitting beside me as such a secret.',
  '可洛女士已经宣布了这个消息。她今天上午到这里来，没有去隔壁那家穷人那里，坐在我身边像说悄悄话一样告诉了我。', 0),
(1, 6, 'What is his name? asked Mr. Bennet.',
  '他叫什么名字？班纳特先生问。', 0),
(1, 7, 'Bingley.',
  '宾利。', 0),
(1, 8, 'Is he married or single, my dear?',
  '他是已婚还是单身，我亲爱的？', 0),
(1, 9, 'Every one of my girls may have him, for all that I know. First come first served.',
  '据我所知，我的五个女儿谁都可以嫁给他。先来先得。', 0),
(1, 10, 'But I assure you I am by no means so eager as you fancy, to get him for any of them.',
  '可我向你保证，我一点也不像你想象的那样迫切地想让任何一个女儿嫁给他。', 0);

-- ============================================================
-- 示例书 2：status='failed'，BYOK 百度引擎（用户密钥 429，不扣积分）
-- 用户：chen@mail.cn（id=3）
-- ============================================================
INSERT INTO books (id, user_id, title, source_ext, source_lang, target_lang, engine, status,
                   source_path, char_count, progress, cached_segments,
                   error_msg, created_at, started_at, finished_at)
VALUES (2, 3, 'The Great Gatsby', 'epub', 'en', 'zh', 'baidu', 'failed',
        '/data/uploads/3/2/source.epub', 96200, 38, 0,
        '翻译引擎调用 429 限流（用户密钥额度不足）',
        '2026-09-25 22:14:00', '2026-09-25 22:14:04', '2026-09-25 22:16:22');

-- ============================================================
-- 翻译缓存种子（5 条，source_hash = 原文真实 MD5）
-- ============================================================
INSERT INTO translation_cache (source_hash, src_lang, tgt_lang, engine, translated_text, hit_count, created_at) VALUES
('9f7efb37c44201d45bd31b577456e7ae', 'en', 'zh', 'official', '凡是有钱的单身汉，总想娶位太太，这已经成了一条举世公认的真理。', 12, '2026-09-20 15:43:00'),
('0cdbcc4f1af218853fb009ce673cc58c', 'en', 'zh', 'official', '不管这样一个人的心情或见解在初进一个地区时多么不为人所知，这条真理却总是牢牢记在周围各家各户的心里。', 8, '2026-09-20 15:44:00'),
('af8f0cba307591172643bf45accb8ffb', 'fr', 'zh', 'deepl', '小王子独自生活在一颗非常非常小的星球上，那里只有一座火山……', 5, '2026-09-22 14:30:00'),
('81e65afa1ab173957a2ff3af9f74b9f3', 'ja', 'zh', 'youdao', '太阳已经落下，天空染上了一层红晕，风也渐渐停了下来。', 3, '2026-09-23 10:15:00'),
('b20107a8e2f56c98a981e1c6db27c3ac', 'en', 'zh', 'official', '生存还是毁灭，这是一个值得考虑的问题。', 0, '2026-09-24 09:00:00');

-- ============================================================
-- 积分流水种子（与 users.points 严格对账：每笔 balance_after = 累计和）
-- demo：50 → 60 → 70 → 58 → 138；chen：50
-- 只有官方引擎（engine='official'）才扣积分，BYOK 不扣
-- ============================================================
INSERT INTO point_logs (user_id, delta, balance_after, type, ref_id, description, created_at) VALUES
(2,  50,  50, 'register',        NULL, '新用户注册奖励', '2026-09-20 10:12:00'),
(2,  10,  60, 'checkin',         NULL, '每日签到', '2026-09-21 09:12:00'),
(2,  10,  70, 'checkin',         NULL, '每日签到', '2026-09-22 09:30:00'),
(2, -12,  58, 'translate',          1, '官方引擎翻译《Pride and Prejudice》', '2026-09-20 15:43:20'),
(2,  80, 138, 'feedback_reward',    1, '反馈奖励（优质反馈）', '2026-09-24 08:00:00'),
(3,  50,  50, 'register',        NULL, '新用户注册奖励', '2026-09-22 11:08:00');

-- ============================================================
-- 签到记录种子
-- ============================================================
INSERT INTO checkins (user_id, checkin_date, reward, created_at) VALUES
(2, '2026-09-21', 10, '2026-09-21 09:12:00'),
(2, '2026-09-22', 10, '2026-09-22 09:30:00'),
(3, '2026-09-22', 10, '2026-09-22 11:20:00');

-- ============================================================
-- 反馈种子（3 条）
-- ============================================================
INSERT INTO feedbacks (user_id, type, title, body, contact, status, reward, created_at, handled_at) VALUES
(2, 'experience', '双语对照排版很清晰',
 '逐段上下对照的排版方式非常清晰，比双栏舒服多了，赞！', '', 'done', 20, '2026-09-24 08:00:00', '2026-09-24 08:00:00'),
(3, 'suggest', '希望支持更多语言对',
 '目前只有中英日韩法德，能否加入西语、俄语？学小语种的人很需要。', '', 'pending', 0, '2026-09-27 19:40:00', NULL),
(2, 'bug', '上传 PDF 后一直卡在解析中',
 '上传一个 8MB 的 PDF 后，进度条停在「解析分句」不动了。', 'demo@book.app', 'pending', 0, '2026-09-27 20:55:00', NULL);

-- ============================================================
-- 风控告警种子（与 users.is_active / ban_reason 严格对应）
--   #1 chen 命中 freq 规则 → 已自动封号（is_active=0, ban_reason='积分风控'）→ 待复核
--   #2 demo 命中 single 规则 → 请求被前置拦截、未扣费 → 复核为误报 → 已解封
-- ============================================================
INSERT INTO risk_alerts (user_id, rule, detail, status, resolve, created_at, handled_at) VALUES
(3, 'freq',
 '5 分钟内发起 18 次官方引擎翻译请求（阈值 10 次），疑似脚本刷量，已自动封号。',
 'pending', NULL, '2026-09-27 20:44:00', NULL),
(2, 'single',
 '单次翻译请求预估消耗 620 积分（超过单次上限 500），请求被前置拦截，未实际扣费；复核为误报，已解封并恢复账号。',
 'resolved', 'unban', '2026-09-27 19:15:00', '2026-09-27 19:22:00');

-- ============================================================
-- 公告种子（3 条）
-- ============================================================
INSERT INTO notices (type, title, body, is_active, views, created_at, updated_at) VALUES
('maintenance', '计划维护：2026-09-28（周日）23:00–24:00 平台整体升级',
 '为提升双语书生成服务的稳定性，平台将于 2026 年 9 月 28 日（周日）23:00 至 24:00 进行整体升级。

维护期间：文件上传与翻译生成将临时不可用；已生成的双语书可正常查看与下载。

由此带来的不便敬请谅解，感谢支持。',
 1, 486, '2026-09-27 18:30:00', '2026-09-27 18:30:00'),

('update', '新功能：PDF 导出支持自定义页面尺寸与页眉页脚',
 '双语书导出模块已升级：PDF 导出现在支持选择页面尺寸（A5 / A4 / 6 英寸）与自定义页眉页脚文字（书名、页码）。

默认排版仍为「逐段上下对照」，升级对本版本起自动生效，无需额外配置。',
 1, 1203, '2026-09-25 10:12:00', '2026-09-25 10:12:00'),

('system', '安全提示：请妥善保管您的 API Key，平台不保存您的任何密钥',
 '本平台采用 BYOK 模式：翻译使用您自行申请的 API Key，密钥仅在本次翻译请求中生效，服务端不存储、不写入日志。

请勿将密钥分享给他人；如怀疑密钥泄露，请在引擎官网立即停用并重新申请。',
 1, 2210, '2026-09-20 09:00:00', '2026-09-20 09:00:00');

-- ============================================================
-- 系统日志种子（8 条，覆盖多模块与多级别）
-- ============================================================
INSERT INTO logs (level, module, message, created_at) VALUES
('INFO',  'task',      '任务 1 入队（Pride and Prejudice · demo@book.app）', '2026-09-27 21:21:07'),
('INFO',  'translate', '书籍 1 翻译完成：10 段，缓存命中 2 段，失败 1 段', '2026-09-27 21:05:12'),
('INFO',  'upload',    'demo@book.app 上传 Pride and Prejudice.epub（1.8MB）', '2026-09-27 21:02:30'),
('WARN',  'translate', '有道 API 限流（429），指数退避重试 2/3', '2026-09-27 20:47:08'),
('ERROR', 'engine',    'demo@book.app 提供的百度 AppKey 校验失败，已拒绝生成请求（3001）', '2026-09-27 20:44:51'),
('WARN',  'risk',      '风控命中：chen@mail.cn 短时高频触发自动封号，待管理员复核', '2026-09-27 20:44:10'),
('INFO',  'cache',     '定时清理缓存完成：过期 14 条（保留策略 30 天）', '2026-09-27 20:31:19'),
('INFO',  'auth',      'chen@mail.cn 登录成功（IP 112.8.34.102）', '2026-09-27 19:58:44');
