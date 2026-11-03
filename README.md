# 双语书工厂 · 后端 API（Bilingual E-Book Studio API）

FastAPI + SQLAlchemy + SQLite，实现设计文档 §6 的全部接口（用户端 + 管理端）。

配套仓库：`bilingual-ebook-web`（用户端）、`bilingual-ebook-admin`（管理端）、`bilingual-ebook-design`（原型与数据库设计）。
接口契约放在本仓库 `docs/contract/`。

---

## 一、技术栈

| 层 | 选型 |
|---|---|
| Web | FastAPI 0.115（自动生成 OpenAPI 文档 `/docs`） |
| ORM | SQLAlchemy 2.x（类型注解式模型） |
| 数据库 | SQLite（WAL 模式，`PRAGMA foreign_keys` 按连接开启） |
| 认证 | JWT（PyJWT，7 天）+ bcrypt 密码哈希 |
| 文件 | 上传落 `storage/uploads/<user>/<book>/`，成品落 `storage/output/` |
| 翻译 | 抽象 Translator 层：mock / 百度 / 有道 / DeepL / 官方 |
| EPUB | 标准库 `zipfile` 生成（mimetype 首条且不压缩） |

---

## 二、快速开始

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

python start.py                 # http://127.0.0.1:8000
```

- 交互式文档：<http://127.0.0.1:8000/docs>
- 健康检查：`GET /api/health`

首次启动会自动执行 `database/database.sql`（与《数据库设计》v1.6 完全一致的 11 表 DDL + 种子数据），
因此开箱即有 3 个账号、2 本书、3 条公告、8 条日志、2 条风控告警。

### 演示账号

| 账号 | 密码 | 角色 |
|---|---|---|
| `admin@book.app` | `admin123` | 管理员 |
| `demo@book.app` | `demo123` | 普通用户（138 积分） |
| `chen@mail.cn` | `user123` | 已被风控封号（登录返回 403，用于演示解封） |

---

## 三、目录结构（课堂脚手架分层）

```
api/
└── v1/                 # 路由层：auth / books / meta / points / feedback / admin
app/
├── factory.py          # 应用工厂：创建 FastAPI 实例并装配各层
├── routes.py           # 路由注册
├── exceptions.py       # 统一异常处理
├── middleware.py       # 中间件注册
└── config.py           # 配置出口（等价 config.config_unified）
config/
└── config_unified.py   # 环境变量配置
core/
├── database.py         # 引擎 / 会话 / Base / 建库与种子
├── security.py         # bcrypt + JWT
└── permissions.py      # 当前用户、管理员校验、ApiError
models/
├── base.py             # Declarative Base
└── entities.py         # 11 张表实体
repository/             # 数据访问层：user / book / point / notice / feedback / risk / cache / log
schemas/
├── entities.py         # 请求/响应模型
└── response.py         # 统一响应包裹
service/
├── dependencies.py     # 依赖注入出口
├── translator.py       # 翻译引擎适配层
├── pipeline.py         # 解析 → 分句 → 翻译 → EPUB
├── epub.py             # EPUB 生成
├── points.py           # 积分账务
├── risk.py             # 风控规则
└── audit.py            # 审计日志
middleware/
├── audit_middleware.py # 访问审计
└── security_headers.py # 安全响应头
utils/
├── response.py         # ok() / 分页
├── response_code.py    # 业务码常量
└── logger.py           # 日志
database/               # 数据库脚本（DDL + 设计文档 + ER 图）
docker/  deploy/        # Dockerfile / compose / nginx
tests/                  # 冒烟测试
start.py                # 启动入口
```

---

## 四、核心行为

### 4.1 生成流程

`POST /api/books`（multipart）→ 建任务 → 后台线程跑管线：

1. 校验格式 / 大小 / 引擎密钥（缺失 → `3001`）
2. 官方引擎先校验并扣积分（不足 → `3002`），随后做风控检查
3. 解析（txt / epub 直接提取；pdf 可选 `pypdf`，扫描版 → `422`）
4. 逐段翻译：先查 `translation_cache`（hash + 语言对 + **引擎** 四元组），命中即复用
5. 单段失败 → `is_failed=1`，**不中断全书**；全书失败才置 `failed`
6. 生成 EPUB 写到 `storage/output/...`，`status=ready`

前端通过 `GET /api/books/{id}` 轮询 `progress`（0–100）。

### 4.2 积分与风控

- 每笔变动同时写 `users.points` 与 `point_logs`（同一事务，`balance_after` 为快照）
- 风控三条规则：单次超限 / 5 分钟高频 / 单日累计
- 命中 → `is_active=0` + `ban_reason='积分风控'` + 生成 `risk_alerts(pending)` + WARN 日志
- 管理员复核：解封 / 确认封号（可附加扣分）

### 4.3 PDF 的取舍

服务端不引入中文字体依赖，`format=pdf` 返回业务码 `4001`，
前端结果页用「打印 → 另存为 PDF」导出（与设计文档一致，也避免了字体版权问题）。

---

## 五、接口一览

| 分类 | 接口 |
|---|---|
| 认证 | `POST /api/auth/register`、`/login`、`GET /auth/me`、`POST /admin/login` |
| 元数据 | `GET /api/engines`、`/languages`、`/notices` |
| 书籍 | `POST /api/books`、`GET /books`、`GET /books/{id}`、`POST /books/{id}/retry`、`DELETE /books/{id}`、`GET /books/{id}/download` |
| 积分 | `GET /api/points`、`/points/logs`、`POST /points/checkin`、`GET /points/rate` |
| 反馈 | `POST /api/feedback`、`GET /feedback/my` |
| 管理端 | `dashboard`、`users`(4)、`tasks`(4)、`cache`(3)、`engines`(2)、`official-api`(2)、`points`(5)、`feedback`(2)、`risk`(3)、`notices`(5)、`logs` |

完整字段以 `/docs` 为准。

---

## 六、切换到真实翻译

`.env` 中设置：

```ini
TRANSLATOR_MODE=real
```

- **BYOK**：用户在页面填写自己申请的百度 / 有道 / DeepL 密钥，随请求传输、不落库
- **官方引擎**：`OFFICIAL_API_KEY` 走 DeepL 接口

`TRANSLATOR_MODE=mock` 时不会发出任何外部请求，内置示例词典保证演示效果。

---

## 七、测试

```bash
pip install pytest
pytest -q
```

`tests/test_smoke.py` 覆盖：健康检查 → 注册登录 → 上传生成 → 轮询完成 → 下载 EPUB → 积分/签到 → 管理员登录与概览。

---

## 八、已知限制

- PDF 由前端打印生成（见 4.3）
- 任务在进程内线程执行，未接 Celery；服务重启会丢失进行中的任务
- 未实现刷新令牌与登出黑名单
- 生产部署需替换 `SECRET_KEY`、关闭 `/docs`、用 Nginx 反代并挂 HTTPS

## 九、接口契约（docs/contract）

接口的唯一真源放在 `docs/contract/`：

| 文件 | 说明 |
|---|---|
| `openapi.json` | 46 路径 / 52 操作 / 15 Schema，由本服务导出 |
| `docs/error-codes.md` | 业务错误码（3001 / 3002 / 4001 / 5001） |
| `docs/field-dictionary.md` | 与 database/ 一致的字段字典 |
| `mock/server.js` | 零依赖 Mock 服务，`node docs/contract/mock/server.js` |
| `scripts/validate_spec.py` | 离线校验契约结构 |
| `scripts/check_spec.py` | 校验实现是否偏离契约 |

```bash
python docs/contract/scripts/validate_spec.py docs/contract/openapi.json
python docs/contract/scripts/check_spec.py --api .
```

---

> 设计与数据库资料归档在 `bilingual-ebook-design` 仓库；本仓库内的 `database/` 为便于检查的副本，建库即读取该文件。
