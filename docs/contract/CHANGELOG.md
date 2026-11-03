# 契约变更记录

破坏性变更（字段改名 / 删除 / 语义变化）必须在此登记，并在 PR 描述中标注 `[BREAKING]`。

## v1.6.0 — 2026-11-02

### 新增
- 全量契约首次固化为 `openapi.json`（47 路径 / 53 操作 / 15 Schema）
- 管理端补齐：积分管理 5 个、反馈 2 个、风控 3 个、API 接入 2 个
- `books` 增加 `progress`、`char_count`、`cached_segments`、`started_at`、`finished_at`
- `translation_cache` 增加 `engine`，并纳入唯一键

### 变更
- `feedbacks.status` 统一为 `pending` / `done`（原设计文档写作 `processed`）
- 积分说明字段统一为 `description`（原设计文档写作 `reason`）
- 签到日期统一为 `checkin_date`（原设计文档写作 `date`）
- 积分余额由独立 `points` 表改为 `users.points` 冗余列 + `point_logs` 流水

### 已知取舍
- `GET /books/{id}/download?format=pdf` 返回业务码 `4001`：PDF 由前端打印导出，
  服务端不引入中文字体依赖（详见 `docs/error-codes.md`）

## v1.5.0 — 2026-09-28

- 新增风控：单次超限 / 短时高频 / 单日累计三条规则，命中自动封号并生成告警
- 管理端新增「风控中心」：解封 / 确认封号 / 封号并扣分

## v1.4.0 — 2026-09-20

- 新增积分体系（签到、余额、明细、管理员增删/批量）与官方引擎（消耗积分免密钥）
- 新增用户反馈与奖励/扣分/封号处理

## v1.3.0 — 2026-09-10

- 新增公告（预设 + 自定义类型）与管理控制台 7 模块

## v1.2.0 — 2026-09-01

- 确定 BYOK 模式：翻译密钥由用户自带，平台不持有

## v1.1.0 — 2026-08-25

- 同步原型交互，冻结首批接口
