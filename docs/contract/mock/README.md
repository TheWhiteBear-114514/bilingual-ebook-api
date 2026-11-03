# Mock 服务

给前端用的假后端，两种方式二选一。

## 方式一：自带静态 Mock（推荐，零依赖）

```bash
node server.js
# Mock API 已启动： http://127.0.0.1:4010/api
```

- 数据在 `fixtures/seed.json`，字段与 `openapi.json` 一致
- 支持增删改：新建书籍 3 秒后自动变 `ready`；禁用用户、复核告警、清空缓存都会改内存状态
- 重启进程即恢复初始数据

环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `MOCK_PORT` | 4010 | 端口 |
| `MOCK_HOST` | 127.0.0.1 | 监听地址 |
| `MOCK_DELAY` | 120 | 每个请求的模拟延迟（ms） |

前端接入：

```ini
# bilingual-ebook-web/.env.local
VITE_USE_MOCK=false
VITE_API_BASE=http://127.0.0.1:4010/api
```

## 方式二：Prism（从 openapi.json 生成，支持动态响应）

```bash
npm install
npm run mock:prism      # http://127.0.0.1:4011
```

Prism 严格按契约校验请求，适合验证「前端传参是否符合契约」。

## 两者区别

| | 静态 Mock | Prism |
|---|---|---|
| 依赖 | 无（Node 自带） | 需要 npm install |
| 数据 | 固定 fixture，可增删改 | 按 Schema 动态生成 |
| 用途 | 演示 / 调 UI | 契约合规性验证 |

## 已知限制

- `GET /books/{id}/download` 返回 `4001`：Mock 不生成真实 EPUB，需要文件时请连后端
- 登录不校验密码，任何密码都返回演示账号
