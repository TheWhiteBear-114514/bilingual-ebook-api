# 数据库脚本（v1.6）

| 文件 | 说明 |
|---|---|
| `database.sql` | SQLite DDL + 种子数据：11 张表、10 个索引、枚举 CHECK 约束、`notices.updated_at` 触发器 |
| `database-design.md` | 设计说明：逐表字段、索引策略、级联规则、接口 → SQL 映射、种子数据说明 |
| `er-diagram.svg` | ER 图：11 张表与关系、约束标注 |

## 执行

```bash
sqlite3 book.db < database.sql
```

后端首次启动会自动执行本文件建库并灌入种子数据（见 `app/init_db.py`），无需手动执行。

## 账号

| 账号 | 密码 | 说明 |
|---|---|---|
| `admin@book.app` | `admin123` | 管理员 |
| `demo@book.app` | `demo123` | 普通用户（138 积分） |
| `chen@mail.cn` | `user123` | 已被风控封号，用于演示解封 |
