#!/usr/bin/env node
/**
 * 零依赖静态 Mock 服务（不装任何包，node server.js 即可）
 * ------------------------------------------------------------
 * 用途：后端没起、或只想调前端 UI 时，提供与 openapi.json 同形状的响应。
 * 数据来自 fixtures/seed.json；进程内存有简单状态（新增/删除/开关会生效）。
 *
 * 注意：下载接口返回 4001（Mock 不生成真实文件），其余接口行为与契约一致。
 */
const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')

const PORT = Number(process.env.MOCK_PORT || 4010)
const HOST = process.env.MOCK_HOST || '127.0.0.1'
const DELAY = Number(process.env.MOCK_DELAY || 120)

const seed = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'seed.json'), 'utf8'))

// 运行期状态（深拷贝，避免污染 fixture）
const state = {
  ...seed,
  books: seed.books.items.map((b) => ({ ...b })),
  nextBookId: 100,
  feedbacks: seed.my_feedback.map((f) => ({ ...f })),
  risk: seed.admin_risk.items.map((r) => ({ ...r })),
  users: seed.admin_users.items.map((u) => ({ ...u })),
  cache: seed.admin_cache.items.map((c) => ({ ...c })),
  notices: seed.admin_notices.map((n) => ({ ...n }))
}

const routes = []
const route = (method, pattern, handler) => routes.push({ method, pattern, handler })

const ok = (data = null) => ({ code: 0, message: 'ok', data })
const fail = (code, message) => ({ code, message, data: null })

const summary = (b) => ({
  ...b,
  segment_count: b.segment_count ?? 10,
  failed_segments: b.failed_segments ?? 1,
  epub_url: `/api/books/${b.id}/download?format=epub`,
  pdf_url: `/api/books/${b.id}/download?format=pdf`
})

/* ---------------- 认证 ---------------- */
route('POST', /^\/api\/auth\/login$/, () => ok(state.auth))
route('POST', /^\/api\/auth\/register$/, () => ok(state.auth))
route('GET', /^\/api\/auth\/me$/, () => ok(state.auth.user))
route('POST', /^\/api\/admin\/login$/, () => ok(state.admin_auth))

/* ---------------- 元数据 ---------------- */
route('GET', /^\/api\/engines$/, () => ok(state.engines))
route('GET', /^\/api\/languages$/, () => ok(state.languages))
route('GET', /^\/api\/notices$/, () => ok(state.notices.filter((n) => n.is_active)))
route('GET', /^\/api\/health$/, () => ok({ status: 'ok', version: '1.6.0-mock' }))

/* ---------------- 书籍 ---------------- */
route('GET', /^\/api\/books$/, (ctx) => {
  const page = Number(ctx.query.get('page') || 1)
  const size = Number(ctx.query.get('size') || 12)
  const start = (page - 1) * size
  return ok({
    total: state.books.length,
    page,
    size,
    items: state.books.slice(start, start + size).map(summary)
  })
})

route('POST', /^\/api\/books$/, () => {
  const id = ++state.nextBookId
  const book = {
    id,
    title: 'Mock 新书',
    source_ext: 'txt',
    source_lang: 'en',
    target_lang: 'zh',
    engine: 'official',
    status: 'processing',
    progress: 35,
    char_count: 8200,
    cached_segments: 1,
    segment_count: 10,
    failed_segments: 0,
    error_msg: null,
    created_at: new Date().toISOString().slice(0, 19),
    started_at: new Date().toISOString().slice(0, 19),
    finished_at: null
  }
  state.books.unshift(book)
  // 简单推进：3 秒后完成
  setTimeout(() => {
    book.status = 'ready'
    book.progress = 100
    book.finished_at = new Date().toISOString().slice(0, 19)
  }, 3000)
  return ok(summary(book))
})

route('GET', /^\/api\/books\/(\d+)$/, (ctx) => {
  const id = Number(ctx.match[1])
  if (id === 1) {
    return ok(state.book_detail)
  }
  const book = state.books.find((b) => b.id === id)
  if (!book) return fail(404, '任务不存在')
  return ok({ ...summary(book), segments: state.book_detail.segments })
})

route('POST', /^\/api\/books\/(\d+)\/retry$/, () => ok({ ...state.books[0], status: 'processing', progress: 5 }))
route('DELETE', /^\/api\/books\/(\d+)$/, (ctx) => {
  state.books = state.books.filter((b) => b.id !== Number(ctx.match[1]))
  return ok(true)
})
route('GET', /^\/api\/books\/(\d+)\/download$/, () =>
  fail(4001, 'Mock 服务不生成文件，请连接真实后端下载 EPUB')
)

/* ---------------- 积分 ---------------- */
route('GET', /^\/api\/points$/, () => ok(state.points))
route('GET', /^\/api\/points\/rate$/, () => ok(state.point_rate))
route('GET', /^\/api\/points\/logs$/, () => ok(state.point_logs))
route('POST', /^\/api\/points\/checkin$/, () => ok(state.checkin))

/* ---------------- 反馈 ---------------- */
route('POST', /^\/api\/feedback$/, () => ok(state.my_feedback[0]))
route('GET', /^\/api\/feedback\/my$/, () => ok(state.feedbacks))

/* ---------------- 管理端 ---------------- */
route('GET', /^\/api\/admin\/dashboard$/, () => ok(state.admin_dashboard))

route('GET', /^\/api\/admin\/users$/, () => ok({ total: state.users.length, items: state.users }))
route('PUT', /^\/api\/admin\/users\/(\d+)\/status$/, (ctx) => {
  const u = state.users.find((x) => x.id === Number(ctx.match[1]))
  if (u) {
    u.is_active = !u.is_active
    u.ban_reason = u.is_active ? null : '管理员手动禁用'
  }
  return ok(u)
})
route('POST', /^\/api\/admin\/users\/(\d+)\/reset-password$/, () => ok({ temp_password: 'Tmp8F3a9c2' }))
route('DELETE', /^\/api\/admin\/users\/(\d+)$/, (ctx) => {
  state.users = state.users.filter((u) => u.id !== Number(ctx.match[1]))
  return ok(true)
})

route('GET', /^\/api\/admin\/tasks$/, () => ok(state.admin_tasks))
route('POST', /^\/api\/admin\/tasks\/(\d+)\/cancel$/, () => ok({ ...state.admin_tasks.items[0], status: 'failed' }))
route('POST', /^\/api\/admin\/tasks\/(\d+)\/retry$/, () => ok({ ...state.admin_tasks.items[1], status: 'processing', progress: 5 }))
route('DELETE', /^\/api\/admin\/tasks\/(\d+)$/, () => ok(true))

route('GET', /^\/api\/admin\/cache$/, () =>
  ok({ total: state.cache.length, hits: state.admin_cache.hits, hit_rate: state.admin_cache.hit_rate, items: state.cache })
)
route('DELETE', /^\/api\/admin\/cache\/(\d+)$/, (ctx) => {
  state.cache = state.cache.filter((c) => c.id !== Number(ctx.match[1]))
  return ok(true)
})
route('DELETE', /^\/api\/admin\/cache$/, () => {
  state.cache = []
  return ok(true)
})

route('GET', /^\/api\/admin\/engines$/, () => ok(state.admin_engines))
route('PUT', /^\/api\/admin\/engines\/([\w-]+)\/status$/, () => ok(true))

route('GET', /^\/api\/admin\/official-api$/, () => ok(state.admin_official))
route('PUT', /^\/api\/admin\/official-api$/, () => ok(true))

route('GET', /^\/api\/admin\/points$/, () =>
  ok({ total: state.users.length, items: state.users.map((u) => ({ ...u, log_count: 3 })) })
)
route('POST', /^\/api\/admin\/points\/(adjust|clear|bulk)$/, () => ok({ points: 100, affected: 2 }))
route('PUT', /^\/api\/admin\/points\/config$/, () => ok(true))

route('GET', /^\/api\/admin\/feedback$/, () => ok(state.admin_feedback))
route('POST', /^\/api\/admin\/feedback\/(\d+)\/handle$/, () => ok({ ...state.admin_feedback.items[0], status: 'done' }))

route('GET', /^\/api\/admin\/risk\/alerts$/, () =>
  ok({ total: state.risk.length, items: state.risk })
)
route('PUT', /^\/api\/admin\/risk\/config$/, () => ok(true))
route('POST', /^\/api\/admin\/risk\/(\d+)\/resolve$/, (ctx) => {
  const r = state.risk.find((x) => x.id === Number(ctx.match[1]))
  if (r) {
    r.status = 'resolved'
    r.resolve = 'unban'
  }
  return ok(r)
})

route('GET', /^\/api\/admin\/notices$/, () => ok(state.notices))
route('POST', /^\/api\/admin\/notices$/, () => ok({ ...state.notices[0], id: 99, title: 'Mock 新公告' }))
route('PUT', /^\/api\/admin\/notices\/(\d+)$/, () => ok(state.notices[0]))
route('PUT', /^\/api\/admin\/notices\/(\d+)\/status$/, () => ok(state.notices[0]))
route('DELETE', /^\/api\/admin\/notices\/(\d+)$/, () => ok(true))

route('GET', /^\/api\/admin\/logs$/, (ctx) => {
  const level = ctx.query.get('level')
  const items = level && level !== 'all'
    ? state.admin_logs.items.filter((l) => l.level === level)
    : state.admin_logs.items
  return ok({ total: items.length, items })
})

/* ---------------- 服务器 ---------------- */
const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`)
  const send = (status, payload) => {
    const body = JSON.stringify(payload)
    res.writeHead(status, {
      'Content-Type': 'application/json; charset=utf-8',
      'Content-Length': Buffer.byteLength(body),
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type',
      'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
    })
    res.end(body)
  }

  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type',
      'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
    })
    return res.end()
  }

  const hit = routes.find((r) => r.method === req.method && r.pattern.test(url.pathname))
  setTimeout(() => {
    if (!hit) {
      console.log(`404 ${req.method} ${url.pathname}`)
      return send(404, fail(404, `Mock 未实现：${req.method} ${url.pathname}`))
    }
    const match = url.pathname.match(hit.pattern)
    try {
      const payload = hit.handler({ match, query: url.searchParams, req })
      send(200, payload)
    } catch (err) {
      send(500, fail(5001, err.message))
    }
  }, DELAY)
})

server.listen(PORT, HOST, () => {
  console.log(`Mock API 已启动： http://${HOST}:${PORT}/api`)
  console.log(`健康检查：        http://${HOST}:${PORT}/api/health`)
  console.log('前端联调：把 VITE_API_BASE 设为上面的 /api 地址（VITE_USE_MOCK=false）')
})
