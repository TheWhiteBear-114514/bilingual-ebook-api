# 双语书工厂 · 接口契约（Bilingual E-Book Studio Contract）

前后端唯一的接口真源。`openapi.json` 由后端 FastAPI 应用生成，任何接口改动都必须先在这里体现。

配套仓库：`bilingual-ebook-web`（Vue 3 前端）、`bilingual-ebook-api`（FastAPI 后端）。

---

## 一、这个仓库解决什么问题

课程项目最容易出的事故是「前端按 A 字段写、后端按 B 字段返回」，联调时互相甩锅。
把契约独立成仓库后：

1. 接口先在这里定稿（评审通过才写代码）
2. 前端对着 `openapi.json` 的 Mock 开发，不必等后端
3. 后端实现完，用脚本校验「实现是否偏离契约」
4. 答辩时可以直接展示 `/docs` 与契约仓库的对应关系

---

## 二、文件说明

| 文件 | 用途 |
|---|---|
| `openapi.json` | **唯一真源**：53 个操作、47 个路径、15 个 Schema |
| `docs/error-codes.md` | 业务错误码表（前后端共用） |
| `docs/field-dictionary.md` | 字段字典（对应数据库 v1.6 的 11 张表） |
| `CHANGELOG.md` | 契约变更记录，破坏性变更必须登记 |
| `scripts/check_spec.py` | 校验后端实现与契约是否一致 |
| `scripts/validate_spec.py` | 离线校验契约自身结构（零依赖） |
| `mock/server.js` | **零依赖 Mock 服务**，`node mock/server.js` 直接跑 |
| `mock/fixtures/seed.json` | Mock 数据（字段与契约一致） |
| `.github/workflows/contract-check.yml` | CI：契约结构校验 + 后端漂移检查 |

---

## 三、通用约定

### 3.1 统一响应包裹

```json
{ "code": 0, "message": "ok", "data": {} }
```

- `code === 0` 表示成功，其余为业务错误码（见 `docs/error-codes.md`）
- HTTP 状态码仍保持语义（400/401/403/404/409/413/422/500）
- 文件下载接口（EPUB）直接返回二进制流，不套包裹

### 3.2 鉴权

```
Authorization: Bearer <JWT>
```

- 登录后签发，有效期 7 天
- 除注册 / 登录 / 公告 / 引擎目录 / 下载外均需携带
- 管理员接口额外校验 `role='admin'`

### 3.3 分页

列表接口统一接受 `page`（默认 1）、`size`（默认 12，上限 100），返回：

```json
{ "total": 42, "page": 1, "size": 12, "items": [] }
```

### 3.4 时间

统一 `YYYY-MM-DDTHH:MM:SS`（ISO 8601，无时区后缀，服务端本地时间）。
前端 `new Date(str.replace(' ', 'T'))` 可直接解析。

---

## 四、怎么用

### 4.1 在线查看

```bash
# 方式一：Redoc 静态页（无需后端）
npx @redocly/cli preview-docs openapi.json

# 方式二：导入 Swagger Editor
# https://editor.swagger.io/ → File → Import File
```

### 4.2 Mock 服务（前端不必等后端）

**方式一：仓库自带的零依赖 Mock**（推荐）

```bash
node mock/server.js          # http://127.0.0.1:4010/api
```

数据在 `mock/fixtures/seed.json`，字段与契约一致，支持增删改（新建书 3 秒后变 ready、可禁用用户、可复核告警）。
前端把 `VITE_USE_MOCK=false`、`VITE_API_BASE=http://127.0.0.1:4010/api` 即可联调。

**方式二：Prism**（严格按契约校验请求）

```bash
cd mock && npm install && npm run mock:prism   # http://127.0.0.1:4011
```

详见 `mock/README.md`。

### 4.3 校验后端是否偏离契约

```bash
python scripts/check_spec.py --api ../bilingual-ebook-api
```

脚本会重新导出后端当前实现的 OpenAPI，与 `openapi.json` 做规范化比对，
输出新增 / 删除 / 变更的路径清单；CI 中可直接作为门禁。

### 4.4 CI 自动化

仓库同时提供两套配置，按你使用的平台删掉另一份即可：

| 平台 | 文件 | Job |
|---|---|---|
| GitHub | `.github/workflows/contract-check.yml` | `validate-spec` / `drift-check` |
| GitLab | `.gitlab-ci.yml` | `validate-spec` / `drift-check` |

两个 Job 的职责：

| Job | 内容 |
|---|---|
| `validate-spec` | `python scripts/validate_spec.py`：结构、operationId 唯一性、`$ref` 可解析 |
| `drift-check` | 检出后端仓库 → 装依赖 → `check_spec.py` 比对实现与契约 |

启用 `drift-check`：

- GitHub：**Settings → Variables** 添加 `BACKEND_REPO = 用户名/bilingual-ebook-api`
- GitLab：**Settings → CI/CD → Variables** 添加 `BACKEND_REPO_URL = 组名/bilingual-ebook-api`

未配置时该 Job 自动跳过，不会误报失败。

---

## 五、变更流程

1. 在 `openapi.json` 中修改（或从后端重新导出后人工审阅）
2. 在 `CHANGELOG.md` 登记：日期 / 版本 / 破坏性变更说明
3. 前端与后端各自跟进，`check_spec.py` 通过才算联调完成
4. 打 tag：`v1.6.0`

---

## 六、当前覆盖

| 模块 | 操作数 |
|---|---|
| 认证（注册 / 登录 / me / 管理员登录） | 4 |
| 元数据（引擎 / 语言 / 公告） | 3 |
| 书籍（上传 / 列表 / 详情 / 重试 / 删除 / 下载） | 6 |
| 积分（余额 / 明细 / 签到 / 兑换比例） | 4 |
| 反馈（提交 / 我的反馈） | 2 |
| 管理端（概览 / 用户 / 任务 / 缓存 / 引擎 / API / 积分 / 反馈 / 风控 / 公告 / 日志） | 33 |
| 系统（健康检查） | 1 |

> 说明：早期任务书「28 个接口」的口径已随 v1.4 / v1.5 功能扩展失效，以本仓库的 52 个操作为准。
