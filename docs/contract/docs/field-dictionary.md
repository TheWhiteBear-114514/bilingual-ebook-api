# 字段字典（对应数据库 v1.6 · 11 张表）

> 与 `数据库设计/er-diagram.svg`、`database.sql` 保持一致。
> 接口返回的 JSON 字段一律 **snake_case**，与数据库列名相同，前端不做二次改名。

## users

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int | 主键 |
| email | str | 唯一，登录凭证 |
| password_hash | str | bcrypt，永不出现在响应中 |
| nickname | str? | 昵称 |
| points | int | 积分余额（冗余列，与 point_logs 同事务维护） |
| role | `user` / `admin` | 角色 |
| is_active | bool | 禁用后登录返回 403 |
| ban_reason | str? | `积分风控` = 风控自动封号；空 = 正常 |
| created_at / last_login_at | datetime | — |

## books

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int | 主键 |
| user_id | int | FK → users，级联删除 |
| title | str | 书名 |
| source_ext | `txt` / `epub` / `pdf` | 上传格式 |
| source_lang / target_lang | str | 语言码 `zh/en/ja/ko/fr/de` |
| engine | `baidu` / `youdao` / `deepl` / `official` | 翻译引擎 |
| status | `pending` / `processing` / `ready` / `failed` | 状态机 |
| progress | int 0–100 | 前端轮询进度条 |
| char_count | int? | 源文字符数（今日翻译量统计） |
| cached_segments | int | 命中缓存段数 |
| source_path / epub_path / pdf_path | str? | 文件路径（不对外暴露） |
| error_msg | str? | 失败原因 |
| created_at / started_at / finished_at | datetime | 耗时 = finished − started |

**响应附加字段**（非数据库列，服务端计算）：`segment_count`、`failed_segments`、`epub_url`、`pdf_url`、`user`（仅管理端）。

## segments

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int | 主键 |
| book_id | int | FK → books |
| seq | int | 段落序号，从 1 起；`UNIQUE(book_id, seq)` |
| source_text | str | 原文 |
| translated_text | str? | 译文；失败回退时为 `null` |
| is_failed | bool | `true` 表示翻译失败、保留原文 |

## translation_cache

| 字段 | 类型 | 说明 |
|---|---|---|
| source_hash | str | 原文 MD5（32 位） |
| src_lang / tgt_lang | str | 语言对 |
| engine | str | **缓存键的一部分**：不同引擎译文不可复用 |
| translated_text | str | 译文 |
| hit_count | int | 命中次数 |

唯一键：`(source_hash, src_lang, tgt_lang, engine)`

## point_logs

| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | int | FK → users |
| delta | int | 正数增加 / 负数扣减，不允许 0 |
| balance_after | int | 变动后余额快照，可直接对账 |
| type | 枚举 | `checkin` `register` `translate` `feedback_reward` `feedback_penalty` `admin_adjust` `admin_bulk` `risk_penalty` |
| ref_id | int? | 关联业务 ID（book / feedback / risk_alert） |
| description | str? | 人可读说明 |

## checkins

| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | int | FK → users |
| checkin_date | date | `YYYY-MM-DD`，`UNIQUE(user_id, checkin_date)` |
| reward | int | 当日奖励快照 |

## system_config

| key | 默认值 | 说明 |
|---|---|---|
| checkin_reward | 10 | 签到奖励 |
| register_reward | 50 | 注册奖励 |
| token_per_point | 1000 | 1 积分 = 多少 tokens |
| official_api_enabled | 1 | 官方引擎开关 |
| official_api_key | — | 平台密钥（接口永不返回明文） |
| risk_max_single / risk_max_freq / risk_max_daily | 500 / 10 / 2000 | 风控阈值 |

## feedbacks

| 字段 | 类型 | 说明 |
|---|---|---|
| type | `bug` / `suggest` / `experience` / `other` | 类型 |
| title / body | str | 标题与详情 |
| contact | str? | 联系方式 |
| status | `pending` / `done` | 状态 |
| reward | int | 处理奖励积分 |
| handled_at | datetime? | 处理时间 |

## risk_alerts

| 字段 | 类型 | 说明 |
|---|---|---|
| rule | `single` / `freq` / `daily` | 命中规则 |
| detail | str | 异常详情 |
| status | `pending` / `resolved` | 复核状态 |
| resolve | `unban` / `confirm` / null | 复核结论 |
| handled_at | datetime? | 处理时间 |

## notices

| 字段 | 类型 | 说明 |
|---|---|---|
| type | 预设或自定义 | `maintenance` / `update` / `system` / 自定义字符串 |
| title / body | str | 标题（≤60 字）/ 正文 |
| is_active | bool | 停用保留记录 |
| views | int | 浏览量 |
| updated_at | datetime | 由触发器维护 |

## logs

| 字段 | 类型 | 说明 |
|---|---|---|
| level | `INFO` / `WARN` / `ERROR` | 级别 |
| module | str | `auth` `upload` `task` `translate` `engine` `user` `cache` `notice` `point` `feedback` `official` `risk` `system` |
| message | str | 人类可读消息 |
