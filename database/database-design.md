# 双语电子书生成系统 · 数据库设计文档

> 项目名：双语电子书生成系统（Bilingual E-Book Studio）
> 版本：v1.6 ｜ 2026-11-02
> 数据库：SQLite（SQLAlchemy ORM）
> 依赖：SQLite ≥ 3.35（支持 JSON 函数、WAL 模式）

---

## 1. 总览

### 1.1 数据库选型

| 维度 | 选型 | 理由 |
|------|------|------|
| 数据库 | SQLite 3.x | 课设零部署成本、单文件便携、并发量小完全够用 |
| ORM | SQLAlchemy 2.x | Python FastAPI 生态成熟，自动映射 |
| 日志模式 | WAL（Write-Ahead Logging） | DDL 头部 `PRAGMA journal_mode=WAL;` 开启；读不阻塞写、写不阻塞读，提升并发读写 |
| 外键 | `PRAGMA foreign_keys=ON;` | SQLite 默认不强制外键，且**按连接生效**：建库脚本只影响当次会话，应用侧须在每个连接上执行（SQLAlchemy 用 `event.listens_for(engine, "connect")` 注册），否则级联删除会静默失效 |

### 1.2 表关系总述

本系统共 **11 张表**：

| 类别 | 表名 | 说明 |
|------|------|------|
| 核心表（3） | `users` | 用户表（含管理员角色、积分余额） |
| | `books` | 书籍任务表 |
| | `segments` | 段落表（book 的子表） |
| 缓存表（1） | `translation_cache` | 翻译缓存表（松耦合，无外键） |
| 积分表（3） | `point_logs` | 积分明细流水表（v1.4 新增） |
| | `checkins` | 签到记录表（v1.4 新增） |
| | `system_config` | 系统配置表（v1.4 新增：签到/兑换比例/风控阈值/官方API 密钥） |
| 反馈表（1） | `feedbacks` | 用户反馈表（v1.4 新增） |
| 风控表（1） | `risk_alerts` | 风控告警表（v1.5 新增） |
| 独立表（2） | `notices` | 公告表（无外键） |
| | `logs` | 系统日志表（无外键） |

**关系：**
- `users` 1:N `books` → `segments`（级联删除）
- `users` 1:N `point_logs`（积分明细归属用户，级联删除）
- `users` 1:N `checkins`（签到记录归属用户，级联删除）
- `users` 1:N `feedbacks`（反馈归属用户，级联删除）
- `users` 1:N `risk_alerts`（风控告警归属用户，级联删除）
- `translation_cache` 松耦合，按 `(source_hash, src_lang, tgt_lang)` 唯一命中查询，不参与级联
- `notices` / `logs` / `system_config` 独立，无外键

---

## 2. 逐表结构

### 2.1 users 表

用户表，存储注册用户与管理员。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTOINCREMENT | — | 用户 ID |
| email | TEXT | NOT NULL, UNIQUE | — | 登录凭证（邮箱格式） |
| password_hash | TEXT | NOT NULL | — | bcrypt 加盐哈希 |
| nickname | TEXT | NULL | NULL | 可选昵称 |
| points | INTEGER | NOT NULL | 50 | 积分余额（v1.4 新增，可扣至负值） |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 注册时间 |
| last_login_at | DATETIME | NULL | NULL | 登录时更新 |
| role | TEXT | NOT NULL | `'user'` | `'user'` / `'admin'`（区分管理控制台） |
| is_active | BOOLEAN | NOT NULL | 1 | 启用状态（禁用后登录被拒） |
| ban_reason | TEXT | NULL | NULL | 封号原因（v1.5 新增，区分风控封号/手动封号，空 = 正常） |

**索引：**
- `UNIQUE(email)` — 唯一约束兼索引

**说明：**
- 积分余额采用**冗余字段**直接存于 `users.points`，避免每次查询余额都要聚合流水；明细留痕在 `point_logs`，二者通过应用层事务保证一致性。

### 2.2 books 表

书籍任务表，记录每次上传生成的任务。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTOINCREMENT | — | 任务 ID |
| user_id | INTEGER | NOT NULL, FK → users.id ON DELETE CASCADE | — | 所属用户 |
| title | TEXT | NOT NULL | — | 书名（缺省取文件名/书内标题） |
| source_ext | TEXT | NOT NULL | — | 上传格式：`txt` / `epub` / `pdf` |
| source_lang | TEXT | NOT NULL | — | 源语言码（`en`/`ja`/`fr`/`zh`/`de`/`ko`） |
| target_lang | TEXT | NOT NULL | — | 目标语言码 |
| engine | TEXT | NOT NULL | — | 翻译引擎：`baidu`/`youdao`/`deepl`/`official`（v1.4 新增 `official` 官方引擎） |
| status | TEXT | NOT NULL, 索引, CHECK | `'pending'` | `pending` → `processing` → `ready` / `failed` |
| source_path | TEXT | NULL | NULL | 上传源文件路径（重试 / 重新解析依赖，v1.6 新增） |
| char_count | INTEGER | NULL | NULL | 源文字符数，支撑「今日翻译量」统计（v1.6 新增） |
| progress | INTEGER | NOT NULL, CHECK 0–100 | 0 | 处理进度，管理端进度条数据源（v1.6 新增） |
| cached_segments | INTEGER | NOT NULL | 0 | 命中翻译缓存的段数，用于计算命中率（v1.6 新增） |
| epub_path | TEXT | NULL | NULL | EPUB 生成后写入的文件路径 |
| pdf_path | TEXT | NULL | NULL | PDF 生成后写入的文件路径 |
| error_msg | TEXT | NULL | NULL | `failed` 状态时存储可读原因 |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 提交时间 |
| started_at | DATETIME | NULL | NULL | 开始处理时间（v1.6 新增） |
| finished_at | DATETIME | NULL | NULL | 处理结束时间，`finished_at - started_at` 即耗时（v1.6 新增） |

**索引：**
- `INDEX idx_books_status (status)` — 管理端任务筛选
- `INDEX idx_books_user_created (user_id, created_at)` — 书架分页

### 2.3 segments 表

段落表，存储书籍逐段翻译单元。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTOINCREMENT | — | 段落 ID |
| book_id | INTEGER | NOT NULL, FK → books.id ON DELETE CASCADE, 索引 | — | 所属书籍 |
| seq | INTEGER | NOT NULL | — | 段落序号，从 1 起 |
| source_text | TEXT | NOT NULL | — | 原文 |
| translated_text | TEXT | NULL | NULL | 译文；失败回退时为 NULL |
| is_failed | BOOLEAN | NOT NULL | 0 | 1 = 翻译失败保留原文 |

**唯一约束：**
- `UNIQUE(book_id, seq)` — 同一段落序号不重复

**索引：**
- `UNIQUE(book_id, seq)` 已自带 B-Tree 索引，足够支撑「按书取全部分段、顺序渲染」，**不再重复建 `idx_segments_book`**（v1.6 移除冗余索引）

### 2.4 translation_cache 表

翻译缓存表，松耦合性能优化，不参与任何外键约束。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTOINCREMENT | — | 缓存 ID |
| source_hash | TEXT | NOT NULL | — | 原文 MD5 哈希 |
| src_lang | TEXT | NOT NULL | — | 源语言码 |
| tgt_lang | TEXT | NOT NULL | — | 目标语言码 |
| engine | TEXT | NOT NULL, CHECK | — | 引擎维度，`baidu`/`youdao`/`deepl`/`official`（v1.6 新增） |
| translated_text | TEXT | NOT NULL | — | 译文缓存 |
| hit_count | INTEGER | NOT NULL | 0 | 命中计数 |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 缓存创建时间 |

**唯一约束兼索引：**
- `UNIQUE(source_hash, src_lang, tgt_lang, engine)` — 命中查询走此唯一约束，O(1) 查找
- 把 `engine` 纳入缓存键：不同引擎译文质量不同，**不可跨引擎复用**（v1.6 修正）

### 2.5 point_logs 表（v1.4 新增）

积分明细流水表，记录每一笔积分变动，只增不改。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTOINCREMENT | — | 流水 ID |
| user_id | INTEGER | NOT NULL, FK → users.id ON DELETE CASCADE, 索引 | — | 所属用户 |
| delta | INTEGER | NOT NULL | — | 变动值（正 = 增加，负 = 扣减） |
| balance_after | INTEGER | NOT NULL | — | 变动后余额（快照，便于追溯） |
| type | TEXT | NOT NULL | — | 变动类型：`checkin`/`register`/`translate`/`feedback_reward`/`feedback_penalty`/`admin_adjust`/`admin_bulk`/`risk_penalty` |
| ref_id | INTEGER | NULL | NULL | 关联业务 ID（如 book_id / feedback_id / risk_alert_id） |
| description | TEXT | NULL | NULL | 变动说明（如「官方引擎翻译《书名》」） |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 发生时间 |

**索引：**
- `INDEX idx_point_logs_user_created (user_id, created_at DESC)` — 用户积分明细查询、按时间倒序

### 2.6 checkins 表（v1.4 新增）

签到记录表，记录用户每日签到。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTOINCREMENT | — | 签到 ID |
| user_id | INTEGER | NOT NULL, FK → users.id ON DELETE CASCADE | — | 所属用户 |
| checkin_date | DATE | NOT NULL | — | 签到日期（`YYYY-MM-DD`） |
| reward | INTEGER | NOT NULL | — | 当日签到奖励积分（快照，后台可改不影响历史） |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 签到时间 |

**唯一约束：**
- `UNIQUE(user_id, checkin_date)` — 同一用户每日只能签到一次

**索引：**
- `INDEX idx_checkins_date (checkin_date)` — 管理端统计「今日签到人次」

### 2.7 system_config 表（v1.4/v1.5 新增）

系统配置表，键值对存储全局可配置项（积分规则、兑换比例、风控阈值、官方 API 密钥）。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| key | TEXT | PK | — | 配置键名（唯一） |
| value | TEXT | NOT NULL | — | 配置值（字符串存储，读取时按类型解析） |
| updated_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 最后修改时间 |

**预置配置键：**

| key | 默认值 | 说明 |
|-----|--------|------|
| `checkin_reward` | `10` | 每日签到奖励积分 |
| `register_reward` | `50` | 新用户注册奖励积分 |
| `token_per_point` | `1000` | 1 积分可兑换的 token 数 |
| `official_api_enabled` | `1` | 官方 API 引擎开关 |
| `official_api_key` | — | 官方 API 密钥（服务端持有，不对外返回） |
| `risk_max_single` | `500` | 风控：单次翻译消耗上限（积分） |
| `risk_max_freq` | `10` | 风控：5 分钟内请求次数阈值 |
| `risk_max_daily` | `2000` | 风控：单日累计消耗上限（积分） |

**说明：**
- 采用键值对设计，新增配置无需改表结构。
- 官方 API 密钥属**平台资产**（区别于 BYOK 用户密钥即用即弃），存于此表且**仅服务端可读写**，任何接口不返回其明文。

### 2.8 feedbacks 表（v1.4 新增）

用户反馈表，收集使用反馈与 Bug 提交。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTOINCREMENT | — | 反馈 ID |
| user_id | INTEGER | NOT NULL, FK → users.id ON DELETE CASCADE, 索引 | — | 提交用户 |
| type | TEXT | NOT NULL | — | 类型：`bug`/`suggest`/`experience`/`other` |
| title | TEXT | NOT NULL | — | 反馈标题 |
| body | TEXT | NOT NULL | — | 反馈详情 |
| contact | TEXT | NULL | NULL | 联系方式（可选） |
| status | TEXT | NOT NULL | `'pending'` | `pending`（待处理）/ `done`（已处理） |
| reward | INTEGER | NOT NULL | 0 | 处理奖励积分（0 = 无奖励） |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 提交时间 |
| handled_at | DATETIME | NULL | NULL | 处理时间 |

**索引：**
- `INDEX idx_feedbacks_status (status)` — 管理端按状态筛选

### 2.9 risk_alerts 表（v1.5 新增）

风控告警表，记录积分异常消耗命中事件。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTOINCREMENT | — | 告警 ID |
| user_id | INTEGER | NOT NULL, FK → users.id ON DELETE CASCADE, 索引 | — | 涉事用户 |
| rule | TEXT | NOT NULL | — | 命中规则：`single`/`freq`/`daily` |
| detail | TEXT | NOT NULL | — | 异常详情（如「5 分钟内 18 次请求」） |
| status | TEXT | NOT NULL | `'pending'` | `pending`（待处理）/ `resolved`（已处理） |
| resolve | TEXT | NULL | NULL | 处理结果：`unban`（解封）/ `confirm`（确认封号） |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 触发时间 |
| handled_at | DATETIME | NULL | NULL | 处理时间 |

**索引：**
- `INDEX idx_risk_alerts_status (status)` — 管理端风控中心待处理筛选

**说明：**
- 触发时自动执行 `users.is_active=0` + `users.ban_reason='积分风控'`，告警记录生成后通知管理员人工复核。
- `rule` 取值对应 `system_config` 中的三条阈值：`single`↔`risk_max_single`、`freq`↔`risk_max_freq`、`daily`↔`risk_max_daily`。

### 2.10 notices 表

公告表，独立无外键。用户端只读启用项，管理端 CRUD。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTOINCREMENT | — | 公告 ID |
| type | TEXT | NOT NULL | — | `maintenance` / `update` / `system` / 自定义 |
| title | TEXT | NOT NULL | — | 标题（≤60 字） |
| body | TEXT | NOT NULL | — | 正文（多段落） |
| is_active | BOOLEAN | NOT NULL | 1 | 停用保留记录，可重新启用 |
| views | INTEGER | NOT NULL | 0 | 浏览量 |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 发布时间 |
| updated_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 最后修改时间 |

**索引：**
- `INDEX idx_notices_active_created (is_active, created_at)` — 用户端公告栏只查启用项倒序

### 2.11 logs 表

系统日志表，独立无外键。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTOINCREMENT | — | 日志 ID |
| level | TEXT | NOT NULL | — | `INFO` / `WARN` / `ERROR` |
| module | TEXT | NOT NULL | — | `system`/`auth`/`engine`/`user`/`task`/`cache`/`notice`/`upload`/`translate`/`point`/`feedback`/`official`/`risk` |
| message | TEXT | NOT NULL | — | 日志消息 |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 创建时间 |

**索引：**
- `INDEX idx_logs_level_created (level, created_at DESC)` — 级别筛选 + 时间倒序
- `INDEX idx_logs_module (module)` — 模块筛选

---

## 3. 状态机

### 3.1 books.status 流转

```
上传成功 → pending → processing → ready
                            ↘ failed（error_msg 记原因）
```

| 状态 | 说明 | 转换 |
|------|------|------|
| `pending` | 上传成功，等待处理 | `pending` → `processing` |
| `processing` | 正在解析/翻译/生成 | `processing` → `ready` / `failed` / `pending`（取消） |
| `ready` | 生成完成 | 终态，可下载 |
| `failed` | 处理失败 | `failed` → `processing`（retry，仅非解析类失败） |

### 3.2 积分生命周期（v1.4/v1.5）

```
注册奖励 → 签到 → 官方引擎翻译消耗 → 反馈奖励/扣分 → 管理员增删/清空/批量 → 风控扣分
```

- 每一笔变动均写入 `point_logs`（只增不改），`users.points` 实时维护当前余额。
- 官方引擎翻译：先校验余额充足 → 扣减积分 → 写 `point_logs(type='translate')` → 执行翻译。
- 余额不足返回错误码 `3002`（积分不足）。

### 3.3 风控告警流转（v1.5）

```
检测到异常消耗（命中 single/freq/daily 任一规则）
  → 自动封号（users.is_active=0, ban_reason='积分风控'）
  → 生成 risk_alerts（status='pending'）
  → 通知管理员（导航角标 + 概览横幅）
  → 管理员复核：
      ├─ 解除封号（误判）→ is_active=1, ban_reason=NULL, risk_alerts.resolve='unban'
      ├─ 确认封号 → risk_alerts.resolve='confirm'
      └─ 封号 + 扣分 → 同确认，另写 point_logs(type='risk_penalty')
```

---

## 4. 索引设计

| # | 索引 | 表 | 对应查询场景 |
|---|------|-----|-------------|
| 1 | `UNIQUE(email)` | users | 登录校验、注册查重 |
| 2 | `idx_books_user_created (user_id, created_at)` | books | 书架分页 |
| 3 | `idx_books_status (status)` | books | 管理端任务筛选 |
| 4 | `idx_books_user_status (user_id, status)` | books | 书架按状态筛选（v1.6 新增） |
| 5 | `UNIQUE(source_hash, src_lang, tgt_lang)` | translation_cache | 缓存命中查询 |
| 6 | `idx_point_logs_user_created (user_id, created_at DESC)` | point_logs | 积分明细查询 |
| 7 | `UNIQUE(user_id, checkin_date)` | checkins | 每日签到查重 |
| 8 | `idx_checkins_date (checkin_date)` | checkins | 今日签到人次统计 |
| 9 | `idx_feedbacks_status (status)` | feedbacks | 反馈状态筛选 |
| 10 | `idx_risk_alerts_status (status)` | risk_alerts | 风控告警筛选 |
| 11 | `idx_notices_active_created (is_active, created_at)` | notices | 用户端公告栏 |
| 12 | `idx_logs_level_created (level, created_at DESC)` | logs | 日志筛选 |
| 13 | `idx_logs_module (module)` | logs | 模块筛选 |

---

## 5. 外键与级联策略

| 关系 | 外键 | 级联策略 | 说明 |
|------|------|----------|------|
| books.user_id → users.id | ON DELETE CASCADE | 删用户 → 级联删 books | 文件目录清理由应用层负责 |
| segments.book_id → books.id | ON DELETE CASCADE | 删 books → 级联删 segments | 同上 |
| point_logs.user_id → users.id | ON DELETE CASCADE | 删用户 → 级联删积分流水 | 用户删除后流水无意义 |
| checkins.user_id → users.id | ON DELETE CASCADE | 删用户 → 级联删签到记录 | 同上 |
| feedbacks.user_id → users.id | ON DELETE CASCADE | 删用户 → 级联删反馈 | 同上 |
| risk_alerts.user_id → users.id | ON DELETE CASCADE | 删用户 → 级联删告警 | 同上 |
| translation_cache | 无外键 | 不参与级联 | 缓存独立存在 |
| notices / logs / system_config | 无外键 | 不参与级联 | 独立生命周期 |

---

## 6. 查询设计（接口 → SQL 映射）

### 6.1 用户端接口（15 个）

| # | 接口 | 对应 SQL |
|---|------|----------|
| 1 | `POST /api/auth/register` | `INSERT INTO users (email, password_hash, nickname, role, points) VALUES (?, ?, ?, 'user', (SELECT value FROM system_config WHERE key='register_reward'))`<br>`INSERT INTO point_logs (user_id, delta, balance_after, type, description) VALUES (?, ?, ?, 'register', '新用户注册奖励')` |
| 2 | `POST /api/auth/login` | `SELECT * FROM users WHERE email=? AND password_hash=? AND is_active=1` |
| 3 | `POST /api/books` | `INSERT INTO books (user_id, title, source_ext, source_lang, target_lang, engine, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')`<br>`INSERT INTO segments (book_id, seq, source_text, translated_text, is_failed) VALUES (?, ?, ?, NULL, 0)` |
| 4 | `GET /api/books` | `SELECT * FROM books WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?` |
| 5 | `GET /api/books/{id}/download` | `SELECT epub_path, pdf_path, status FROM books WHERE id=? AND user_id=?` |
| 6 | `POST /api/books/{id}/retry` | `UPDATE books SET status='processing' WHERE id=? AND status='failed'` |
| 7 | `GET /api/engines` | 静态配置 + `SELECT value FROM system_config WHERE key='official_api_enabled'`（判断官方引擎是否可用） |
| 8 | `GET /api/languages` | 静态配置（引擎支持的语言对），不查库 |
| 9 | `GET /api/notices` | `SELECT id, title, type, body, created_at FROM notices WHERE is_active=1 ORDER BY created_at DESC` |
| 10 | `GET /api/points` | `SELECT points FROM users WHERE id=?` |
| 11 | `GET /api/points/logs` | `SELECT * FROM point_logs WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?` |
| 12 | `POST /api/points/checkin` | `INSERT INTO checkins (user_id, checkin_date, reward) VALUES (?, date('now'), (SELECT value FROM system_config WHERE key='checkin_reward'))`<br>`UPDATE users SET points = points + reward WHERE id=?`<br>`INSERT INTO point_logs (user_id, delta, balance_after, type, description) VALUES (?, ?, ?, 'checkin', '每日签到')` |
| 13 | `POST /api/feedback` | `INSERT INTO feedbacks (user_id, type, title, body, contact, status) VALUES (?, ?, ?, ?, ?, 'pending')` |
| 14 | `GET /api/feedback/my` | `SELECT * FROM feedbacks WHERE user_id=? ORDER BY created_at DESC` |
| 15 | `GET /api/points/rate` | `SELECT value FROM system_config WHERE key='token_per_point'`（兑换比例查询） |

> 官方引擎翻译的积分扣减在 `POST /api/books` 内部事务中完成：先校验余额 → `UPDATE users SET points=points-? WHERE id=? AND points>=?` → 写 `point_logs(type='translate')`。

### 6.2 管理端接口（33 个）

| # | 接口 | 对应 SQL |
|---|------|----------|
| 1 | `POST /api/admin/login` | `SELECT * FROM users WHERE email=? AND password_hash=? AND role='admin' AND is_active=1` |
| 2 | `GET /api/admin/dashboard` | 聚合查询（含风控告警计数：`SELECT COUNT(*) FROM risk_alerts WHERE status='pending'`） |
| 3 | `GET /api/admin/users` | `SELECT * FROM users WHERE email LIKE ? OR nickname LIKE ? ORDER BY created_at DESC` |
| 4 | `PUT /api/admin/users/{id}/status` | `UPDATE users SET is_active=CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?` |
| 5 | `POST /api/admin/users/{id}/reset-password` | `UPDATE users SET password_hash=? WHERE id=?` |
| 6 | `DELETE /api/admin/users/{id}` | `DELETE FROM users WHERE id=?`（级联删除关联表） |
| 7 | `GET /api/admin/tasks` | `SELECT * FROM books WHERE status=? ORDER BY created_at DESC` |
| 8 | `POST /api/admin/tasks/{id}/cancel` | `UPDATE books SET status='failed', error_msg='已取消（管理员操作）' WHERE id=?` |
| 9 | `POST /api/admin/tasks/{id}/retry` | `UPDATE books SET status='processing' WHERE id=? AND status='failed'` |
| 10 | `DELETE /api/admin/tasks/{id}` | `DELETE FROM books WHERE id=?` |
| 11 | `GET /api/admin/cache` | `SELECT COUNT(*), SUM(hit_count) FROM translation_cache` |
| 12 | `DELETE /api/admin/cache/{id}` | `DELETE FROM translation_cache WHERE id=?` |
| 13 | `DELETE /api/admin/cache` | `DELETE FROM translation_cache` |
| 14 | `GET /api/admin/engines` | 静态配置 + 聚合统计 |
| 15 | `PUT /api/admin/engines/{id}/status` | 引擎状态存配置表 |
| 16 | `GET /api/admin/notices` | `SELECT * FROM notices ORDER BY created_at DESC` |
| 17 | `POST /api/admin/notices` | `INSERT INTO notices (type, title, body, is_active) VALUES (?, ?, ?, 1)` |
| 18 | `PUT /api/admin/notices/{id}` | `UPDATE notices SET title=?, body=?, type=? WHERE id=?` |
| 19 | `PUT /api/admin/notices/{id}/status` | `UPDATE notices SET is_active=NOT is_active WHERE id=?` |
| 20 | `DELETE /api/admin/notices/{id}` | `DELETE FROM notices WHERE id=?` |
| 21 | `GET /api/admin/logs` | `SELECT * FROM logs WHERE level=? AND message LIKE ? AND module=? ORDER BY created_at DESC` |
| 22 | `GET /api/admin/points` | `SELECT u.*, (SELECT COUNT(*) FROM point_logs pl WHERE pl.user_id=u.id) FROM users u` |
| 23 | `POST /api/admin/points/adjust` | `UPDATE users SET points=points+? WHERE id=?`<br>`INSERT INTO point_logs (user_id, delta, balance_after, type, description) VALUES (?, ?, ?, 'admin_adjust', ?)` |
| 24 | `POST /api/admin/points/clear` | `UPDATE users SET points=0 WHERE id=?`<br>`INSERT INTO point_logs (...) VALUES (..., 'admin_adjust', '管理员清空积分')` |
| 25 | `POST /api/admin/points/bulk` | 批量增减：`UPDATE users SET points=points+? WHERE role='user'`（全量或按筛选）<br>逐人写 `point_logs(type='admin_bulk')` |
| 26 | `PUT /api/admin/points/config` | `UPDATE system_config SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key=?`（签到/注册/兑换比例） |
| 27 | `GET /api/admin/feedback` | `SELECT f.*, u.email, u.nickname, u.points FROM feedbacks f JOIN users u ON f.user_id=u.id ORDER BY f.created_at DESC` |
| 28 | `POST /api/admin/feedback/{id}/handle` | `UPDATE feedbacks SET status='done', reward=?, handled_at=CURRENT_TIMESTAMP WHERE id=?`（奖励/扣分同步写 point_logs 与 users.points） |
| 29 | `GET /api/admin/official-api` | `SELECT * FROM system_config WHERE key IN ('official_api_enabled','token_per_point')`（不返回密钥明文） |
| 30 | `PUT /api/admin/official-api` | `UPDATE system_config SET value=? WHERE key='official_api_key'` / `official_api_enabled` |
| 31 | `GET /api/admin/risk/alerts` | `SELECT r.*, u.email, u.nickname FROM risk_alerts r JOIN users u ON r.user_id=u.id WHERE r.status=? ORDER BY r.created_at DESC` |
| 32 | `PUT /api/admin/risk/config` | `UPDATE system_config SET value=? WHERE key IN ('risk_max_single','risk_max_freq','risk_max_daily')` |
| 33 | `POST /api/admin/risk/{id}/resolve` | `UPDATE risk_alerts SET status='resolved', resolve=?, handled_at=CURRENT_TIMESTAMP WHERE id=?`（解封/确认/封号+扣分） |

> 注：管理端接口编号到 33 行，其中「管理操作审计写入」随各操作自动触发，非独立接口。

---

## 7. 扩展字段说明

### 7.1 v1.3 遗留 5 个缺口闭环（已保留）

| # | 缺口 | 处理结果 |
|---|------|----------|
| 1 | `books` 无 `engine` | `books.engine TEXT NOT NULL` |
| 2 | `users` 无启用状态 | `users.is_active BOOLEAN DEFAULT 1` |
| 3 | `translation_cache` 无命中统计 | `hit_count` + `created_at` |
| 4 | 无系统日志表 | 新增 `logs` 表 |
| 5 | 无引擎调用统计 | `logs.module='engine'` 聚合 |

### 7.2 v1.4/v1.5 新增字段与表（闭环）

| # | 新增 | 说明 |
|---|------|------|
| 1 | `users.points` | 积分余额冗余字段，实时维护 |
| 2 | `users.ban_reason` | 封号原因标记（区分风控/手动封号） |
| 3 | `point_logs` 表 | 积分明细流水，只增不改 |
| 4 | `checkins` 表 | 签到记录，`UNIQUE(user_id, checkin_date)` 防重复 |
| 5 | `system_config` 表 | 键值对配置（签到/兑换/风控阈值/官方API） |
| 6 | `feedbacks` 表 | 用户反馈 |
| 7 | `risk_alerts` 表 | 风控告警 |
| 8 | `books.engine` 增 `official` | 官方引擎取值 |
| 9 | `books.source_path` | 源文件路径，失败重试 / 重新解析依赖（v1.6） |
| 10 | `books.char_count` | 源文字符数，支撑「今日翻译量」统计（v1.6） |
| 11 | `books.progress` | 0–100 进度，管理端进度条数据源（v1.6） |
| 12 | `books.cached_segments` | 命中缓存段数，用于计算缓存命中率（v1.6） |
| 13 | `books.started_at / finished_at` | 任务起止时间，支撑耗时统计（v1.6） |
| 14 | `translation_cache.engine` | 缓存按引擎分键，避免跨引擎复用译文（v1.6） |
| 15 | 全表枚举 CHECK | `status`/`role`/`engine`/`type`/`level` 等入库即校验（v1.6） |
| 16 | `notices.updated_at` 触发器 | 更新时自动刷新时间戳（v1.6） |

---

## 8. 种子数据说明

### 8.1 种子账号

| 账号 | 邮箱 | 密码 | role | points | is_active | 说明 |
|------|------|------|------|--------|-----------|------|
| 管理员 | `admin@book.app` | `admin123` | `'admin'` | 0 | 1 | 管理控制台登录 |
| 普通用户 1 | `demo@book.app` | `demo123` | `'user'` | 138 | 1 | 用户端原型演示账号 |
| 普通用户 2 | `chen@mail.cn` | `user123` | `'user'` | 50 | 0 | 已被风控自动封号（`ban_reason='积分风控'`），用于演示解封 |

**预生成 bcrypt 哈希：**
- `admin123` → `$2b$10$EtbdUyTqBmRdScNsRKgN/.YjAjLNT52H4zQ34qCigwdQVGZURTIRC`
- `demo123` → `$2b$10$aZHqd5Pa3vTrp26xw02TO.22E.m2rjXr2rOdyQRf2XbLolbn7y4Y2`
- `user123` → `$2b$10$.R2/Vw1wIDRX79Grro2oeOWRedgjLEJUD1jFSitv5YUV6k3LF81J.`

### 8.2 示例数据

| 数据类型 | 数量 | 说明 |
|----------|------|------|
| 示例书（ready） | 1 本 | 含 10 条 segments，其中 1 条 `is_failed=1` |
| 示例书（failed） | 1 本 | `error_msg='翻译引擎调用 429 限流'` |
| 翻译缓存 | 5 条 | `hit_count` 不同，`engine` 覆盖 official/deepl/youdao |
| 公告 | 3 条 | 维护/更新/系统通知 |
| 日志 | 8 条 | 覆盖多模块多级别 |
| 积分流水 | 6 条 | 每人 `balance_after` 累计和 = `users.points`，可直接对账 |
| 签到记录 | 若干 | 演示签到历史 |
| 反馈 | 3 条 | 待处理/已处理 |
| 风控告警 | 2 条 | 1 条待处理（chen 已封号）+ 1 条已解封（demo），与 `users.is_active` 严格对应 |
| 系统配置 | 8 条 | 预置默认配置键值 |

---

## 9. 安全设计

| 维度 | 措施 |
|------|------|
| 密码存储 | bcrypt 哈希加盐，明文从不落库 |
| 翻译密钥 | 两类：BYOK 用户密钥（即用即弃不落库）+ 官方 API 密钥（存 `system_config`，仅服务端可读写，接口永不返回明文） |
| JWT | 7 天有效期，登录后签发，前端存 localStorage |
| 上传安全 | 扩展名白名单 + magic number 校验；文件名重命名 UUID 防路径穿越 |
| 限流 | 同 IP 上传 5 次/分钟；翻译 API QPS 限流 2 |
| 积分风控 | 三条规则命中自动封号 + 告警 + 人工复核，阈值后台可配 |
| 管理端 | `role='admin'` 路由级校验；所有管理操作写审计日志 |

---

## 10. 遗留问题

本次设计以设计文档 v1.5 及双端原型为权威依据，数据库设计与原型在数据映射上已一一对应。保留并更新以下遗留问题说明：

1. **接口总数口径**：设计文档第 6 节接口契约随 v1.4/v1.5 扩展后，用户端 15 个 + 管理端 33 个（含积分/反馈/官方API/风控相关接口）。早期任务书「28 个接口」口径已随功能扩展失效，以设计文档实际接口清单为准。

2. **积分余额一致性**：`users.points` 为冗余字段，与 `point_logs` 的聚合结果需通过**应用层事务**保证一致（同事务内扣减/增加余额 + 写流水）。这是「读快、写重」的经典权衡，SQLite 单写者特性下用短事务即可满足课设并发量。

3. **风控自动封号与手动封号的区分**：通过 `users.ban_reason` 字段标记（`'积分风控'` vs 手动封号原因），管理端可据此区分展示，解封时清空该字段。

4. **外键强制与连接级 PRAGMA**：`PRAGMA foreign_keys=ON` 只对当前连接生效，已在本文件 §1.1 与 SQL 头部注明，应用侧必须用 SQLAlchemy `connect` 事件逐连接开启，否则 `ON DELETE CASCADE` 不会执行。

5. **管理端指标的来源**：概览页的「今日翻译量（字符数）」由 `books.char_count` 汇总，「缓存命中率」由 `cached_segments` 与段落总数计算，「任务进度」读 `books.progress` —— 这三项在 v1.5 无字段可依，v1.6 已补齐。

6. **官方 API 密钥存储性质**：存 `system_config` 属平台资产，与 BYOK 用户密钥（即用即弃）性质不同，已在安全设计中单独说明。

其余（5 个缺口字段、种子数据、级联策略）均已闭环，种子数据与双端原型演示一一对应。

---

*文档版本：v1.6 ｜ 生成日期：2026-11-02 ｜ 与设计文档 v1.6、DDL 与双端原型逐字对齐*
