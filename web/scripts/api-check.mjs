/**
 * Vue3 前端「数据层」联调检查（Node 直连后端，不经过浏览器）
 *
 * 作用：用与前端 axios 完全相同的接口与参数，逐项验证后端契约，
 *       覆盖 6 个页面用到的全部接口（含首页岗位浏览）。
 *       浏览器渲染是否正常由 `npm run check:render` 负责。
 *
 * 前置：后端已启动（scripts/run_api.ps1）
 * 运行：npm run check:api     自定义地址：API=http://127.0.0.1:8000 npm run check:api
 */
const BASE = (process.env.API || 'http://127.0.0.1:8000').replace(/\/$/, '')
let token = ''
const RESUME = `姓名：张伟
期望岗位：测试开发工程师
期望城市：苏州
期望薪资：12000-16000元
最高学历：大专
专业：软件技术
工作年限：3年
是否应届：否

【技能特长】
熟练掌握 Selenium、JMeter、Python、MySQL、Linux，了解 Postman 与 Git

【工作经历】
2022.07-2025.06 某软件公司 测试工程师，负责接口自动化测试与性能测试
`

async function call(method, path, body, auth = true) {
  const h = { 'Content-Type': 'application/json' }
  if (auth && token) h.Authorization = 'Bearer ' + token
  const r = await fetch(BASE + path, {
    method, headers: h, body: body ? JSON.stringify(body) : undefined,
  })
  const text = await r.text()
  let j
  try { j = JSON.parse(text) } catch { j = text }
  return { status: r.status, j }
}

let pass = 0
let fail = 0
const ok = (cond, msg) => {
  if (cond) { pass++; console.log('  ✅ ' + msg) } else { fail++; console.log('  ❌ ' + msg) }
}

console.log('='.repeat(72))
console.log('前端数据层联调 ｜ ' + BASE)
console.log('='.repeat(72))

// ---------- 首页：岗位浏览 ----------
let r = await call('GET', '/api/jobs/stats', null, false)
ok(r.status === 200 && r.j.总体.岗位总数 === 8836,
  `GET /api/jobs/stats → ${r.j.总体.岗位总数} 岗 / ${r.j.总体.公司数} 公司 / ${r.j.总体.城市数} 城 / ${r.j.按大类.length} 大类`)
ok(r.j.按大类.reduce((a, b) => a + b.数量, 0) === 8836, '分类合计 = 岗位总数（无遗漏）')

r = await call('GET', '/api/jobs?page=1&size=20', null, false)
ok(r.status === 200 && r.j.岗位.length === 20 && r.j.总页数 === 442,
  `GET /api/jobs → 第 1 页 20 条 / 共 ${r.j.总页数} 页`)
ok(!!r.j.岗位[0].岗位名称 && !!r.j.岗位[0].公司, `岗位卡字段完整：${r.j.岗位[0].岗位名称}｜${r.j.岗位[0].公司}`)

r = await call('GET', '/api/jobs?city=苏州&category=测试&size=5', null, false)
ok(r.status === 200 && r.j.总数 === 360, `筛选（苏州 + 测试）→ ${r.j.总数} 个`)
r = await call('GET', '/api/jobs?sort=salary_desc&size=5', null, false)
ok(r.j.岗位[0].薪资上限 >= r.j.岗位[4].薪资上限, `按薪资降序 → 首条 ${r.j.岗位[0].薪资}`)
r = await call('GET', '/api/jobs/J0001', null, false)
ok(r.status === 200 && !!r.j.职位描述, `GET /api/jobs/J0001 → ${r.j.岗位名称}（含职位描述）`)

// ---------- 健康 / 用户 ----------
r = await call('GET', '/api/health', null, false)
ok(r.j.匹配引擎?.岗位数 === 8836 && r.j.RAG检索?.卡片数 === 8852,
  `GET /api/health → 匹配 ${r.j.匹配引擎.岗位数} 岗 / 知识卡 ${r.j.RAG检索.卡片数} / 权重 ${r.j.匹配引擎.权重版本}`)

const u = 'apicheck' + Math.floor(Math.random() * 1e6)
r = await call('POST', '/api/auth/register', { username: u, password: 'pw123456', nickname: '联调' }, false)
ok(r.status === 200 && !!r.j.token, `POST /api/auth/register → ${r.j.用户?.username}（${r.j.用户?.role_label}）`)
token = r.j.token
r = await call('GET', '/api/auth/me')
ok(r.j.用户?.nickname === '联调', `GET /api/auth/me → ${r.j.用户.nickname}`)
r = await call('PUT', '/api/user/profile', { nickname: '改过的昵称' })
ok(r.j.用户.nickname === '改过的昵称', `PUT /api/user/profile → ${r.j.用户.nickname}`)

// ---------- 简历 → 匹配 → 评分 ----------
r = await call('POST', '/api/resume/parse_text', { resume_text: RESUME }, false)
const resumeId = r.j.resume_id
ok(resumeId?.startsWith('rs_'), `POST /api/resume/parse_text → ${r.j.技能数} 项技能`)
r = await call('POST', '/api/user/resumes', { title: '联调简历', text: RESUME })
const rid = r.j.id
ok(!!rid, `POST /api/user/resumes → id=${rid}`)

r = await call('POST', '/api/match', { resume_id: resumeId, top_n: 5 })
const m = r.j
ok(m.推荐数 === 5 && m.打分范围 === 8836 && m.已存历史 === true,
  `POST /api/match → Top-${m.推荐数}｜${m.打分范围} 岗｜${m.耗时秒}s｜已存历史=${m.已存历史}`)
const j0 = m.推荐[0]
ok(['技能', '经验', '学历', '地域', '薪资', '专业证书'].every((d) => typeof j0[d] === 'number'),
  `六维分齐全：技能 ${j0.技能} / 经验 ${j0.经验} / 地域 ${j0.地域}`)
r = await call('POST', '/api/match', { saved_resume_id: rid, top_n: 3 })
ok(r.j.推荐数 === 3, `POST /api/match(saved_resume_id) → Top-3`)
r = await call('POST', '/api/score', { resume_id: resumeId, job_id: j0.岗位ID })
ok(r.j.模型口径?.可用 === true,
  `POST /api/score → 规则 ${r.j.规则口径.总分} vs 模型 ${r.j.模型口径.T1回归_预测总分}（差 ${r.j.差异}）`)

// ---------- 聚类 / 对话 ----------
r = await call('GET', '/api/cluster/list', null, false)
ok(r.j.簇数 === 9 && r.j.簇.reduce((a, b) => a + b.岗位数, 0) === 8836,
  `GET /api/cluster/list → ${r.j.主方案} / ${r.j.簇数} 簇`)
r = await call('GET', '/api/cluster/profile?name=软件测试', null, false)
ok(r.j.ok === true, `GET /api/cluster/profile → ${r.j.summary}`)
r = await call('POST', '/api/chat', { question: '福州市的Java岗位有多少个？', use_cache: true }, false)
ok(r.status === 200 && !!r.j.回答,
  `POST /api/chat → ${r.j.工具序列}｜${r.j.轮数} 轮｜${r.j.耗时秒}s｜缓存=${r.j.缓存命中}`)

// ---------- 个人中心 ----------
r = await call('POST', '/api/user/favorites', { job_id: j0.岗位ID })
ok(r.status === 200, `POST /api/user/favorites → ${r.j.message}`)
r = await call('GET', '/api/user/favorites')
ok(r.j.收藏?.length === 1 && !!r.j.收藏[0].company,
  `GET /api/user/favorites → ${r.j.收藏[0].job_name}｜${r.j.收藏[0].company}`)
r = await call('GET', '/api/user/matches')
ok(r.j.历史?.length >= 2, `GET /api/user/matches → ${r.j.历史.length} 次`)
r = await call('GET', '/api/user/resumes')
ok(r.j.简历?.length === 1, `GET /api/user/resumes → ${r.j.简历.length} 份`)
r = await call('GET', '/api/user/chats')
ok(Array.isArray(r.j.历史), `GET /api/user/chats → ${r.j.历史.length} 条`)
r = await call('GET', '/api/user/stats')
ok(r.status === 200, `GET /api/user/stats → ${JSON.stringify(r.j.统计)}`)
r = await call('GET', '/api/admin/users')
ok(r.status === 403, `GET /api/admin/users（求职者）→ HTTP ${r.status}（预期 403）`)

// ---------- 登出 ----------
r = await call('POST', '/api/auth/logout')
ok(r.status === 200, 'POST /api/auth/logout → 200')
r = await call('GET', '/api/auth/me')
ok(r.status === 401, `登出后 GET /api/auth/me → HTTP ${r.status}（预期 401）`)

console.log('='.repeat(72))
console.log(`结果：通过 ${pass} ｜ 失败 ${fail} ｜ 覆盖 6 个页面用到的全部接口`)
console.log('='.repeat(72))
process.exit(fail ? 1 : 0)
