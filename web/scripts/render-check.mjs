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

// 岗位详情路由需要「真实存在的岗位ID」：从接口取第一条
let jobId = ''
try {
  const rj = await fetch(API + '/api/jobs?size=1')
  jobId = (await rj.json()).岗位?.[0]?.岗位ID || ''
} catch { /* 后端不可用会由断言暴露 */ }

const ROUTES = [
  // 首页 = 推荐页（热门分类轮播 / 地区推荐 / 高薪岗位 / 热门岗位 / 热门企业 / 热门技能）
  ['home', ['热门分类', '地区推荐', '高薪岗位推荐', '热门岗位推荐', '热门企业', '热门技能']],
  ['login', ['人岗匹配推荐系统', '登录', '注册', '先以游客身份逛逛']],
  ['jobs', ['热门职位：', '区域：', '薪资：', '学历：', '排序：']],
  ...(jobId
    ? [['job/' + jobId, ['岗位ID', '技能标签', '职位描述', '公司', '该公司其他在招岗位']]]
    : []),
  ['match', ['岗位推荐', '使用简历', '重新推荐', '优先：', '综合评分', '技能匹配',
             '地理位置', '工作经验', '城市：', '最低匹配分：']],
  ['companies', ['公司广场', '在招职位', '热门企业', '最活跃企业',
                 '在招职位数：', '排序：', '技能需求：', '热招职位：']],
  ...(companyId
    ? [['company/' + companyId,
        ['在招职位', '岗位大类分布', '技能需求', '招聘者', '相似公司']]]
    : []),
  ['profile', ['个人中心', '我的简历', '粘贴简历正文', '上传 PDF 简历',
               '我的收藏', '账号设置']],
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
  '*': ['🏢 岗位聚类', 'ClusterList', '职位推荐', '问答记录', '匹配历史',
        '口径说明', '数据来源', '每个结论都带', '按岗位数排序', '排序（在线优先）',
        '按在招职位数排序', '可追溯到数据文件', '如实说明', 'PBKDF2',
        // 岗位推荐页顶部那 5 个指标卡 + 「返回条数」控件已按反馈删除，不允许回流
        '推荐岗位数', '打分范围', '匹配权重版本', '全量打分耗时', '当前筛选后条数', '返回条数',
        // 个人中心顶部那 4 个统计卡已按反馈删除
        '收藏岗位', '匹配次数', '提问次数',
        '8,836 岗位 / 500 简历'],
  match: ['还没有简历'],
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

// 智能问答已改成全局悬浮球：/#/chat 不再有页面
await page.goto(`${URL}/#/chat`, { waitUntil: 'networkidle2', timeout: 60000 })
await new Promise((r) => setTimeout(r, 1200))
const chatGone = page.url().includes('/home')
console.log(`\n--- /#/chat（已改悬浮球） ---`)
if (chatGone) {
  console.log('  ✅ 独立问答页已移除，兜底路由回首页')
} else {
  failed++
  console.log(`  ❌ 问答页仍可达（当前 URL=${page.url()}）`)
}

// ---------------- 智能问答悬浮球：存在 / 可拖动 / 可点开 ----------------
await page.goto(`${URL}/#/home`, { waitUntil: 'networkidle2', timeout: 60000 })
await new Promise((r) => setTimeout(r, 1500))
console.log(`\n--- 智能问答悬浮球 ---`)
const ballAt = async () => page.$eval('.ball', (e) => {
  const r = e.getBoundingClientRect()
  return { x: Math.round(r.left), y: Math.round(r.top) }
}).catch(() => null)

const b0 = await ballAt()
if (!b0) {
  failed++
  console.log('  ❌ 页面上找不到悬浮球')
} else {
  console.log(`  初始位置 (${b0.x}, ${b0.y})`)
  // ① 单击打开小对话框
  await page.click('.ball')
  await new Promise((r) => setTimeout(r, 700))
  const hasInput = !!(await page.$('.chat-panel input'))
  const hasSamples = (await page.$$('.chat-panel .tag')).length > 0
  if (hasInput && hasSamples) {
    console.log('  ✅ 单击悬浮球 → 弹出小对话框（含输入框与示例问题）')
  } else {
    failed++
    console.log('  ❌ 对话框没弹出或缺少输入框')
  }
  // ①b 「重新回答」按钮：必须存在，且在还没提问时是禁用状态（避免误导）
  const regen = await page.evaluate(() => {
    const b = Array.from(document.querySelectorAll('.chat-panel .phead button'))
      .find((x) => x.innerText.includes('重新回答'))
    return b ? { found: true, disabled: b.disabled } : { found: false }
  })
  if (regen.found && regen.disabled) {
    console.log('  ✅ 有「🔄 重新回答」按钮，且未提问时禁用')
  } else {
    failed++
    console.log(`  ❌ 重新回答按钮异常：${JSON.stringify(regen)}`)
  }

  // ② 拖动：位置变化 + 位置持久化 + 拖动不会误关对话框
  await page.mouse.move(b0.x + 27, b0.y + 27)
  await page.mouse.down()
  await page.mouse.move(b0.x - 220, b0.y - 300, { steps: 12 })
  await page.mouse.up()
  await new Promise((r) => setTimeout(r, 500))
  const b1 = await ballAt()
  const saved = await page.evaluate(() => localStorage.getItem('zq_chat_ball'))
  const stillOpen = !!(await page.$('.chat-panel input'))
  const movedFar = b1 && Math.abs(b1.x - b0.x) > 80 && Math.abs(b1.y - b0.y) > 80
  if (movedFar && saved && stillOpen) {
    console.log(`  ✅ 可拖动：(${b0.x}, ${b0.y}) → (${b1.x}, ${b1.y})，位置已存 localStorage，且未误关对话框`)
  } else {
    failed++
    console.log(`  ❌ 拖动异常：新位置=${JSON.stringify(b1)} ｜ localStorage=${saved} ｜ 对话框仍在=${stillOpen}`)
  }
  // ②b 视口被临时改小再恢复：位置不能被永久压到角落
  //     （截图工具、切开发者工具设备、手机旋转都会触发 resize；这条曾经真的踩到过）
  if (movedFar) {
    await page.setViewport({ width: 800, height: 600 })
    await new Promise((r) => setTimeout(r, 500))
    await page.setViewport({ width: 1440, height: 950 })
    await new Promise((r) => setTimeout(r, 600))
    const b2 = await ballAt()
    const restored = b2 && Math.abs(b2.x - b1.x) < 3 && Math.abs(b2.y - b1.y) < 3
    if (restored) {
      console.log(`  ✅ 视口改小再恢复后位置不变：(${b1.x}, ${b1.y}) → (${b2.x}, ${b2.y})`)
    } else {
      failed++
      console.log(`  ❌ 视口变化把位置弄丢了：拖动后 (${b1.x}, ${b1.y}) → 恢复后 ${JSON.stringify(b2)}`)
    }
  }

  // ③ 收起后再点开（开关正常）—— 表头有两个按钮（重新回答 / 收起），按文字找
  await page.evaluate(() => {
    const b = Array.from(document.querySelectorAll('.chat-panel .phead button'))
      .find((x) => x.innerText.includes('收起'))
    if (b) b.click()
  })
  await new Promise((r) => setTimeout(r, 600))
  const closed = !(await page.$('.chat-panel'))
  await page.click('.ball')
  await new Promise((r) => setTimeout(r, 600))
  const reopened = !!(await page.$('.chat-panel input'))
  if (closed && reopened) {
    console.log('  ✅ 收起 / 再次点开都正常')
  } else {
    failed++
    console.log(`  ❌ 开关异常：收起后=${closed}，再点开=${reopened}`)
  }
  // ④ 悬浮球是全局的：切到别的页面仍然在，且沿用拖动后的位置
  await page.goto(`${URL}/#/companies`, { waitUntil: 'networkidle2', timeout: 60000 })
  await new Promise((r) => setTimeout(r, 1200))
  const onOther = await ballAt()
  const keptPos = onOther && b1 && Math.abs(onOther.x - b1.x) < 3 && Math.abs(onOther.y - b1.y) < 3
  if (onOther && keptPos) {
    console.log('  ✅ 其他页面同样存在，且沿用拖动后的位置')
  } else {
    failed++
    console.log(`  ❌ 其他页面异常：${JSON.stringify(onOther)}`)
  }
}

// 点岗位 → 必须跳到独立详情页（每个岗位有自己的 URL），而不是弹右侧抽屉
await page.goto(`${URL}/#/jobs`, { waitUntil: 'networkidle2', timeout: 60000 })
await new Promise((r) => setTimeout(r, 1600))
console.log(`\n--- 岗位列表点岗位 → 独立 URL ---`)
await page.click('.jcard')
await new Promise((r) => setTimeout(r, 1800))
const jobUrlOk = /#\/job\/J\d{4}$/.test(page.url())
const drawerGone = !(await page.$('.el-drawer'))
const detailText = await page.evaluate(() => document.body.innerText)
if (jobUrlOk && drawerGone && detailText.includes('职位描述')) {
  console.log(`  ✅ 跳到 ${page.url().replace(URL, '')}，页面有职位描述，且没有弹出抽屉`)
} else {
  failed++
  console.log(`  ❌ 跳转异常：URL=${page.url().replace(URL, '')} ｜ 抽屉存在=${!drawerGone}`)
}

// 岗位列表「默认排序」= 打乱：每次进页面顺序不同，且翻页不重复（种子随机保证）
console.log(`\n--- 岗位默认排序（随机） ---`)
const firstNames = async () => {
  await page.goto(`${URL}/#/jobs`, { waitUntil: 'networkidle2', timeout: 60000 })
  await new Promise((r) => setTimeout(r, 1600))
  return page.$$eval('.jcard .jname', (e) => e.map((x) => x.innerText.trim()))
}
const listA = await firstNames()
await page.goto(`${URL}/#/home`, { waitUntil: 'networkidle2', timeout: 60000 })
await new Promise((r) => setTimeout(r, 800))
const listB = await firstNames()
if (listA.length && listB.length && listA[0] !== listB[0]) {
  console.log(`  ✅ 两次进入顺序不同（「${listA[0]}」 vs 「${listB[0]}」）`)
} else {
  failed++
  console.log(`  ❌ 默认排序没变化：${listA[0]} / ${listB[0]}`)
}
await page.evaluate(() => {
  const b = Array.from(document.querySelectorAll('.el-pager li')).find((x) => x.innerText.trim() === '2')
  if (b) b.click()
})
await new Promise((r) => setTimeout(r, 1600))
const page2 = await page.$$eval('.jcard .jname', (e) => e.map((x) => x.innerText.trim()))
const overlap = listB.filter((x) => page2.includes(x))
if (page2.length && overlap.length === 0) {
  console.log(`  ✅ 翻页不重复（第 1 页与第 2 页无交集，第 2 页首条「${page2[0]}」）`)
} else {
  failed++
  console.log(`  ❌ 翻页出现重复岗位 ${overlap.length} 条`)
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
