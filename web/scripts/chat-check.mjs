/**
 * 智能问答真实性检查（`npm run check:chat`）
 *
 * 为什么需要它：
 *   `/api/chat` 默认走结果缓存（命中就完全不出网），所以"看起来像固定答案"很容易被误解成"没调模型"。
 *   本脚本用 **use_cache=false** 连问 N 个**不在缓存里的新问题**，逐条断言：
 *     · 缓存命中 = false（说明真的走了模型）
 *     · tokens.prompt > 0（说明确实是模型在生成）
 *     · 工具轨迹非空（说明先检索后回答，不是凭记忆作答）
 *     · 来源非空（答案可溯源）
 *   并把每次用了哪些工具、几轮、多久、多少 token 打出来，作为"真的调了 DeepSeek API"的可复现证据。
 *
 * 前置：后端已启动（scripts/run_api.ps1）且 .env 里有可用的 DEEPSEEK_API_KEY。
 * 用法：npm run check:chat           # 默认 5 个问题
 *       npm run check:chat -- 3      # 只问前 3 个
 */
const API = process.env.API || 'http://127.0.0.1:8000'

/** 新问题（刻意不用示例问题/评估问题，避免命中缓存） */
const QUESTIONS = [
  '按公司统计一下，在招岗位最多的 5 家公司是哪几家？各招多少个？',
  '苏州的岗位按经验要求是怎么分布的？各段多少个？',
  '要求硕士学历的岗位有多少个？顺便说说它们的薪资中位数。',
  '厦门有哪些 Python 相关的岗位？举 3 个例子并说明薪资。',
  '求职者最常被要求掌握哪些技能？给个前 8 名。',
]

const only = Number(process.argv[2] || 0) || QUESTIONS.length
const pad = (s, n) => {
  const w = [...String(s)].reduce((a, c) => a + (c.charCodeAt(0) > 255 ? 2 : 1), 0)
  return String(s) + ' '.repeat(Math.max(0, n - w))
}

let bad = 0
const toolTally = {}
console.log('='.repeat(84))
console.log('智能问答真实性检查 ｜ ' + API + ' ｜ 强制 use_cache=false（每次都是真实调用）')
console.log('='.repeat(84))

// 先确认后端就绪
try {
  const h = await (await fetch(API + '/api/health')).json()
  console.log(`后端就绪 ｜ Agent 构建: ${h['启动预加载耗时秒']?.['agent'] ?? '懒加载（首次提问时构建）'}`)
} catch {
  console.error('❌ 后端不可用：请先运行 scripts/run_api.ps1')
  process.exit(2)
}

let hist = []
let linkAnswers = 0
for (const [i, question] of QUESTIONS.slice(0, only).entries()) {
  const t0 = Date.now()
  let j
  try {
    const r = await fetch(API + '/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, use_cache: false, history: hist.slice(-4) }),
    })
    j = await r.json()
    if (!r.ok) throw new Error(j?.detail?.error || j?.error || 'HTTP ' + r.status)
  } catch (e) {
    bad++
    console.log(`\n❌ Q${i + 1} ${question}\n   调用失败：${e.message}`)
    continue
  }
  const secs = ((Date.now() - t0) / 1000).toFixed(1)
  const tokens = (j.tokens?.prompt || 0) + (j.tokens?.completion || 0)
  const tools = j.工具轨迹 || []
  tools.forEach((t) => { toolTally[t.工具] = (toolTally[t.工具] || 0) + 1 })

  const checks = [
    ['非缓存', j.缓存命中 === false, `缓存命中=${j.缓存命中}${j.缓存时间 ? '（' + j.缓存时间 + '）' : ''}`],
    ['真调模型', (j.tokens?.prompt || 0) > 0, `prompt ${j.tokens?.prompt ?? 0} + completion ${j.tokens?.completion ?? 0}`],
    ['有工具轨迹', tools.length > 0, tools.map((t) => t.工具).join(' → ') || '（无）'],
    ['有来源', (j.来源 || []).length > 0, `${(j.来源 || []).length} 条`],
    ['回答非空', (j.回答 || '').length > 30, `${(j.回答 || '').length} 字`],
  ]
  // 岗位页链接：提到了具体岗位的回答应当带 /#/job/Jxxxx（前端会渲染成可点链接）
  const hasLink = /(?:#\/|\/#\/)job\/J\d{4}/.test(j.回答 || '')
  if (hasLink) linkAnswers++
  const failed = checks.filter(([, ok]) => !ok)
  if (failed.length) bad++

  console.log(`\n${failed.length ? '❌' : '✅'} Q${i + 1}：${question}`)
  console.log(`   回答：${(j.回答 || '').replace(/\n/g, ' ').slice(0, 110)}…`)
  console.log(`   ${pad('检查项', 12)}${checks.map(([n, ok]) => (ok ? '✅' : '❌') + n).join('  ')}`)
  console.log(`   ${pad('运行', 12)}模型=${j.模型} ｜ ${j.轮数} 轮 ｜ ${j.耗时秒}s（服务端）/${secs}s（端到端）｜ ${tokens} tokens ｜ prompt ${j.prompt版本}`)
  if (hasLink) {
    const m = (j.回答 || '').match(/(?:#\/|\/#\/)job\/(J\d{4})/g) || []
    console.log(`   ${pad('岗位链接', 12)}✅ ${m.length} 个：${[...new Set(m)].slice(0, 4).join('、')}`)
  }
  checks.filter(([n]) => n === '有工具轨迹' || n === '有来源')
    .forEach(([, , extra]) => console.log(`   ${pad('', 12)}${extra}`))
  if (failed.length) console.log(`   ❌ 未通过：${failed.map(([n]) => n).join('、')}`)

  hist.push({ role: 'user', content: question }, { role: 'assistant', content: j.回答 })
}

console.log('\n' + '='.repeat(84))
const newTools = ['company_query', 'home_stats', 'generic_agg']
const usedNew = newTools.filter((t) => toolTally[t])
console.log('工具使用统计：' + (Object.entries(toolTally).map(([k, v]) => `${k}×${v}`).join(' ｜ ') || '（无）'))
console.log(`新工具是否被用上：${usedNew.length ? '✅ ' + usedNew.join('、') : '❌ 三个新工具都没被调用'}`)
console.log(`岗位页链接（/#/job/Jxxxx）：${linkAnswers}/${only} 条回答带链接 ${linkAnswers ? '✅' : '❌'}`)
console.log(`结果：${only - bad}/${only} 个问题通过${bad ? ' ❌' : ' ✅'}`)
console.log('='.repeat(84))
process.exit(bad || !usedNew.length || !linkAnswers ? 1 : 0)
