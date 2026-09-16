import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '../api'
import { TOKEN_KEY } from '../api/client'
import type { ApiUser } from '../api/types'

/** 登录态（令牌 + 用户），令牌存 localStorage，刷新后自动恢复 */
export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
  const user = ref<ApiUser | null>(null)

  const isLogged = () => !!token.value

  function apply(t: string, u: ApiUser) {
    token.value = t
    user.value = u
    localStorage.setItem(TOKEN_KEY, t)
  }

  async function login(username: string, password: string) {
    const r = await api.login(username, password)
    apply(r.token, r.用户)
    return r
  }

  async function register(p: { username: string; password: string; nickname?: string; role?: string }) {
    const r = await api.register(p)
    apply(r.token, r.用户)
    return r
  }

  async function fetchMe() {
    if (!token.value) return null
    try {
      const r = await api.me()
      user.value = r.用户
      return r.用户
    } catch {
      token.value = ''
      localStorage.removeItem(TOKEN_KEY)
      return null
    }
  }

  async function doLogout() {
    try { await api.logout() } catch { /* 忽略 */ }
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
  }

  return { token, user, isLogged, login, register, fetchMe, doLogout }
})
