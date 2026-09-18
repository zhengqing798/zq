/** 展示层格式化小工具（多个页面共用） */

/** 千分位 */
export const fmtNum = (n?: number) => (n || 0).toLocaleString('en-US')

const _k = (v: number) =>
  v % 1000 === 0 ? String(v / 1000) : (v / 1000).toFixed(1)

/** 元/月 → 「10-15K」（招聘网站常见写法）；缺一侧时写「以内/以上」 */
export function fmtSalaryK(lo?: number, hi?: number): string {
  const l = lo || 0
  const h = hi || 0
  if (!l && !h) return '薪资面议'
  if (!l) return _k(h) + 'K以内'
  if (!h) return _k(l) + 'K以上'
  if (l === h) return _k(l) + 'K'
  return _k(l) + '-' + _k(h) + 'K'
}

/** 公司首字头像的稳定配色：同一公司 ID 永远同色，不同公司尽量分散 */
const PALETTE = [
  ['#00a6a7', '#12c2b4'], ['#3b82f6', '#60a5fa'], ['#8b5cf6', '#a78bfa'],
  ['#f59e0b', '#fbbf24'], ['#ef4444', '#f87171'], ['#10b981', '#34d399'],
  ['#06b6d4', '#22d3ee'], ['#ec4899', '#f472b6'],
]

export function logoBg(id: string): string {
  let h = 0
  for (const ch of id || '') h = (h * 31 + ch.charCodeAt(0)) % 9973
  const [a, b] = PALETTE[h % PALETTE.length]
  return `linear-gradient(135deg, ${a}, ${b})`
}

/** 公司名首字（去掉「（）」等前缀噪声后取第一个非空字符） */
export const logoChar = (name: string) => (name || '?').trim().slice(0, 1)
