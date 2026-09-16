import axios from 'axios'
import { ElMessage } from 'element-plus'

/**
 * 统一的 HTTP 客户端。
 *
 * · 开发期走 Vite 代理（/api → http://127.0.0.1:8000），因此 baseURL 留空即可；
 *   生产/容器里可用 VITE_API_BASE 指定（如 Docker compose 中的 http://api:8000）。
 * · 请求拦截器自动带上 Bearer 令牌；401 时清登录态并跳登录页。
 */
const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 300000,
})

export const TOKEN_KEY = 'zq_token'

client.interceptors.request.use((cfg) => {
  const t = localStorage.getItem(TOKEN_KEY)
  if (t) cfg.headers.Authorization = 'Bearer ' + t
  return cfg
})

client.interceptors.response.use(
  (r) => r,
  (err) => {
    const res = err?.response
    const detail = res?.data?.detail
    let msg = '请求失败'
    if (typeof detail === 'string') msg = detail
    else if (detail && typeof detail === 'object') msg = detail.error || JSON.stringify(detail)
    else if (res?.data?.error) msg = res.data.error
    else if (err?.message) msg = err.message

    if (res?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      if (!location.hash.includes('/login')) location.hash = '#/login'
      ElMessage.warning('登录已失效，请重新登录')
    } else {
      ElMessage.error(msg)
    }
    return Promise.reject(new Error(msg))
  },
)

export default client
