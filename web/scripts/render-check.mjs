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
  // 首页 = 推荐页（热门分类轮播 / 地区推荐 / 高薪岗位 / 热门岗位 / 热门企业 / 热门技能）
  ['home', ['热门分类', '地区推荐', '高薪岗位推荐', '热门岗位推荐', '热门企业', '热门技能']],
  ['login', ['人岗匹配推荐系统', '登录', '注册', '先以游客身份逛逛']],
  ['jobs', ['热门职位：', '区域：', '薪资：', '学历：', '排序：']],
  ['match', ['岗位推荐', '使用简历', '开始匹配']],
  ['companies', ['公司广场', '在招职位', '热门企业', '最活跃企业',
                 '在招职位数：', '排序：', '技能需求：', '热招职位：']],
  ...(companyId
    ? [['company/' + companyId,
        ['在招职位', '岗位大类分布', '技能需求', '招聘者', '相似公司']]]
    : []),
  ['profile', ['个人中心', '我的简历', '粘贴简历正文', '上传 PDF 简历',
               '我的收藏', '匹配历史', '账号设置']],
  ['chat', ['智能问答', '提问']],
]

/**
 * 必须**不出现**的内容（防止"删了但没删干净"）：
 * 每个路由的断言 + `*` 全局断言（对每个路由都检查）
 */
const FORBIDDEN = {
  // 2026-09-18 改版：顶部只剩 首页/岗位/公司(+登录后 岗位推荐)；「职位推荐」旧名、
  // 「问答记录」页签、已删的公司页口径面板等都不该再出现。
  // 注意：这里用「🏢 岗位聚类」（旧导航项）而不是裸的「岗位聚类」——
  // 首页底部「数据来源」会如实列出 data/processed/岗位聚类_标签.csv 这个文件名，属正当出处。
  // 2026-09-18 追加：页面上不再放任何「口径 / 数据来源 / 数据规模」描述文字（接口与文档保留）。
  '*': ['🏢 岗位聚类', 'ClusterList', '职位推荐', '问答记录',
        '口径说明', '数据来源', '每个结论都带', '按岗位数排序', '排序（在线优先）',
        '按在招职位数排序', '可追溯到数据文件', '如实说明', 'PBKDF2',
        '8,836 岗位 / 500 简历'],
  home: ['职位分类导航面板',
         // 首页上不允许出现任何"这个推荐是怎么来的"描述性文字
         '排序', '口径', '随机抽取', '数据来源', '来源：'],
  companies: ['口径说明'],
  // 登录页左栏品牌面板已删除：以下文案若回流即报错
  login: ['PBKDF2', '8,836 个真实岗位', '游客也能体验全部核心功能', '六维加权匹配（',
          // 本系统面向求职者：注册界面的角色选择（角色 / 求职者 / 企业）已删除
          '角色', '求职者', '企业'],
}

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
    // 全量 DOM 文本（含隐藏元素）：反向断言用它，隐藏页签里的被删字段也逃不掉
    domText: document.body.textContent || '',
    links: Array.from(document.querySelectorAll('.zq-nav a')).map((a) => a.textContent.trim()),
    els: document.querySelectorAll('*').length,
    title: document.title,
  }))
  const missing = expects.filter((t) => !info.text.includes(t))
  const forbidden = [...(FORBIDDEN[route] || []), ...(FORBIDDEN['*'] || [])]
  const leaked = forbidden.filter((t) => (info.text + info.domText).includes(t))
  if (shots) await page.screenshot({ path: `${SHOT_DIR}/${route.replace(/\//g, '_')}.png`, fullPage: true })
  console.log(`\n--- /#/${route} ---`)
  console.log(`  导航=[${info.links.join(' | ')}] ｜ DOM 元素=${info.els} ｜ 标题="${info.title}"`)
  if (missing.length || leaked.length) {
    failed++
    if (missing.length) console.log('  ❌ 缺少关键文本：', missing)
    if (leaked.length) console.log('  ❌ 不该出现的内容（已删除的模块又出现了）：', leaked)
  } else {
    console.log('  ✅ 关键文本齐全，无遗留内容')
  }
}

// 旧地址兼容：/#/resume 应被重定向到个人中心（简历页已并入个人中心）
await page.goto(`${URL}/#/resume`, { waitUntil: 'networkidle2', timeout: 60000 })
await new Promise((r) => setTimeout(r, 1200))
const redirected = page.url().includes('/profile')
const hasResumeInput = (await page.evaluate(() => document.body.innerText)).includes('粘贴简历正文')
console.log(`\n--- /#/resume（旧地址） ---`)
if (redirected && hasResumeInput) {
  console.log('  ✅ 已重定向到个人中心且简历输入可见')
} else {
  failed++
  console.log(`  ❌ 未按预期重定向（当前 URL=${page.url()}）`)
}

// 已删除的模块：/#/clusters 不应再有页面，应由兜底路由送回首页
await page.goto(`${URL}/#/clusters`, { waitUntil: 'networkidle2', timeout: 60000 })
await new Promise((r) => setTimeout(r, 1200))
const clustersGone = page.url().includes('/home')
console.log(`\n--- /#/clusters（已删除的岗位聚类模块） ---`)
if (clustersGone) {
  console.log('  ✅ 页面已移除，兜底路由回首页')
} else {
  failed++
  console.log(`  ❌ 岗位聚类页面仍然可达（当前 URL=${page.url()}）`)
}

// 游客态：必须用**独立无痕上下文**——同浏览器的普通新页面与本页同源、共享 localStorage，
// 会误判成"已登录游客"（第一次写这段就踩了这个坑）。
const guestCtx = browser.createBrowserContext
  ? await browser.createBrowserContext()
  : await browser.createIncognitoBrowserContext()
const guest = await guestCtx.newPage()
await guest.setViewport({ width: 1440, height: 950 })
guest.on('pageerror', (e) => errors.push('GUEST PAGEERROR: ' + e.message))
guest.on('console', (m) => { if (m.type() === 'error') errors.push('GUEST: ' + m.text()) })
await guest.goto(`${URL}/#/home`, { waitUntil: 'networkidle2', timeout: 60000 })
await new Promise((r) => setTimeout(r, 1500))
const gnav = await guest.$$eval('.zq-nav a', (e) => e.map((x) => x.innerText.trim()))
const gtext = await guest.evaluate(() => document.body.innerText)
console.log(`\n--- 游客态 /#/home ---`)
console.log(`  导航=[${gnav.join(' | ')}]`)
const navOk = gnav.length === 3 && !gnav.some((t) => t.includes('岗位推荐'))
if (navOk && gtext.includes('热门分类')) {
  console.log('  ✅ 只有 首页/岗位/公司 三个标签，且首页推荐内容可见')
} else {
  failed++
  console.log('  ❌ 游客导航不应出现「岗位推荐」或首页内容缺失：', gnav)
}
for (const [route, label] of [['match', '岗位推荐'], ['profile', '个人中心']]) {
  await guest.goto(`${URL}/#/${route}`, { waitUntil: 'networkidle2', timeout: 60000 })
  await new Promise((r) => setTimeout(r, 1200))
  const backToLogin = guest.url().includes('/login')
  console.log(`  ${backToLogin ? '✅' : '❌'} 游客访问 /#/${route}（${label}）→ ` +
              (backToLogin ? '被弹回登录页' : '未被拦截：' + guest.url()))
  if (!backToLogin) failed++
}
await guestCtx.close()

console.log('\n' + '='.repeat(72))
console.log(`路由 ${ROUTES.length} 个 ｜ 失败 ${failed} ｜ 控制台 error ${errors.length}`)
errors.slice(0, 10).forEach((e) => console.log('   ❌ ' + String(e).slice(0, 180)))
if (shots) console.log('截图输出：web/' + SHOT_DIR + '/')
console.log('='.repeat(72))

await browser.close()
process.exit(failed || errors.length ? 1 : 0)
