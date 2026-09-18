/**
 * Vue3 前端无头渲染检查（用本机已装的 Chrome，不下载浏览器）
 *
 * 为什么需要它：
 *   `curl` 只能拿到 SPA 的外壳 HTML；`vite build` 只能证明"能编译"。
 *   本脚本真正**在浏览器里渲染每个路由**，断言关键内容出现，并收集控制台报错——
 *   这是"页面真的能打开、没有运行时报错"的证据。
 *
 * 前置：① 后端已启动（scripts/run_api.ps1）② 前端已启动（npm run dev）③ 本机装了 Chrome
 * 运行：npm run check:render
 *      自定义地址：URL=http://127.0.0.1:4173 npm run check:render
 */
import fs from 'node:fs'
import puppeteer from 'puppeteer-core'

const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  process.env.LOCALAPPDATA + '\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
]
const CHROME = process.env.CHROME_PATH || CHROME_CANDIDATES.find((p) => p && fs.existsSync(p))
const URL = (process.env.URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const API = process.env.API || 'http://127.0.0.1:8000'
const SHOT_DIR = 'screenshots'
const shots = process.env.SHOTS !== '0'

if (!CHROME) {
  console.error('❌ 找不到 Chrome/Edge，可用 CHROME_PATH 环境变量指定')
  process.exit(2)
}
if (shots) fs.mkdirSync(SHOT_DIR, { recursive: true })

// 以登录态检查（同时覆盖"未登录游客态"的断言）
const u = 'rendercheck' + Math.floor(Math.random() * 1e6)
const reg = await fetch(API + '/api/auth/register', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: u, password: 'pw123456', nickname: '渲染检查' }),
})
if (!reg.ok) {
  console.error('❌ 后端不可用（注册失败）：请先启动 scripts/run_api.ps1')
  process.exit(2)
}
const { token } = await reg.json()

// 公司详情路由需要「真实存在的公司ID」：从接口取第一家，避免把 ID 写死在脚本里
let companyId = ''
try {
  const rc = await fetch(API + '/api/companies?size=1')
  companyId = (await rc.json()).公司?.[0]?.公司ID || ''
} catch { /* 后端不可用会由断言/错误计数暴露 */ }

const ROUTES = [
  ['home', ['人岗匹配推荐', '热门职位', '区域：', '薪资：', '学历：', '排序：']],
  ['companies', ['公司广场', '在招职位', '热门企业', '最活跃企业', '口径说明', '规模分档']],
  ...(companyId
    ? [['company/' + companyId,
        ['在招职位', '岗位大类分布', '技能需求', '招聘者', '相似公司', '数据来源']]]
    : []),
  ['resume', ['简历输入', '解析这份文本', '上传 PDF 简历']],
  ['jobs', ['职位推荐', '开始匹配']],
  ['clusters', ['岗位聚类', 'K=9']],
  ['chat', ['智能问答', '提问']],
  ['profile', ['个人中心', '我的简历', '我的收藏', '匹配历史', '问答记录', '账号设置']],
]

const errors = []
const browser = await puppeteer.launch({
  executablePath: CHROME, headless: 'shell',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
})
const page = await browser.newPage()
await page.setViewport({ width: 1440, height: 950 })
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message))
page.on('requestfailed', (r) => errors.push('REQFAIL: ' + r.url()))
page.on('response', (r) => { if (r.status() >= 400) errors.push('HTTP ' + r.status() + ' ' + r.url()) })

// 注入令牌 → 等价于"已登录用户刷新页面"
await page.evaluateOnNewDocument((t) => localStorage.setItem('zq_token', t), token)

console.log('='.repeat(72))
console.log('Vue3 无头渲染检查 ｜ ' + URL + ' ｜ Chrome: ' + CHROME)
console.log('='.repeat(72))

let failed = 0
for (const [route, expects] of ROUTES) {
  await page.goto(`${URL}/#/${route}`, { waitUntil: 'networkidle2', timeout: 60000 })
  await new Promise((r) => setTimeout(r, 1600))
  const info = await page.evaluate(() => ({
    text: document.body.innerText,
    links: Array.from(document.querySelectorAll('.zq-nav a')).map((a) => a.textContent.trim()),
    els: document.querySelectorAll('*').length,
    title: document.title,
  }))
  const missing = expects.filter((t) => !info.text.includes(t))
  if (shots) await page.screenshot({ path: `${SHOT_DIR}/${route.replace(/\//g, '_')}.png`, fullPage: true })
  console.log(`\n--- /#/${route} ---`)
  console.log(`  导航=[${info.links.join(' | ')}] ｜ DOM 元素=${info.els} ｜ 标题="${info.title}"`)
  if (missing.length) {
    failed++
    console.log('  ❌ 缺少关键文本：', missing)
  } else {
    console.log('  ✅ 关键文本齐全')
  }
}

console.log('\n' + '='.repeat(72))
console.log(`路由 ${ROUTES.length} 个 ｜ 失败 ${failed} ｜ 控制台 error ${errors.length}`)
errors.slice(0, 10).forEach((e) => console.log('   ❌ ' + String(e).slice(0, 180)))
if (shots) console.log('截图输出：web/' + SHOT_DIR + '/')
console.log('='.repeat(72))

await browser.close()
process.exit(failed || errors.length ? 1 : 0)
