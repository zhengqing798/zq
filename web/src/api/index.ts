import client from './client'
import type {
  ChatHistoryRow, ChatResp, ClusterListResp, ClusterRow, FavoriteRow, HealthResp,
  JobRec, MatchHistoryRow, MatchResp, ParsedResume, ResumeRow, ScoreResp, TokenResp, ApiUser,
} from './types'

/** 后端 27 个接口的前端封装（与 src/api/schemas.py 一一对应） */

// ---------------- 健康检查
export const getHealth = () => client.get<HealthResp>('/api/health').then((r) => r.data)

// ---------------- ① 简历
export const parseResumeText = (resume_text: string) =>
  client.post<ParsedResume>('/api/resume/parse_text', { resume_text }).then((r) => r.data)

export const parseResumePdf = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return client.post<ParsedResume>('/api/resume/parse', fd).then((r) => r.data)
}

// ---------------- ② 匹配（返回全量结果，供列表 + 抽屉详情共用）
export interface MatchPayload {
  resume_id?: string | null
  resume_text?: string | null
  saved_resume_id?: number | null
  top_n: number
}
export const runMatch = (p: MatchPayload) =>
  client.post<MatchResp>('/api/match', p).then((r) => r.data)

// ---------------- ③ 评分（双口径）
export const runScore = (job_id: string, resume_id?: string | null, resume_text?: string | null) =>
  client.post<ScoreResp>('/api/score', { job_id, resume_id, resume_text }).then((r) => r.data)

// ---------------- ④ 聚类
export const getClusterList = () =>
  client.get<ClusterListResp>('/api/cluster/list').then((r) => r.data)
export const getClusterProfile = (name: string) =>
  client.get<{ ok: boolean; summary: string; data: ClusterRow[]; 来源: string[] }>(
    '/api/cluster/profile', { params: { name } }).then((r) => r.data)

// ---------------- ⑤ 对话
export const ask = (question: string, use_cache = true) =>
  client.post<ChatResp>('/api/chat', { question, use_cache }).then((r) => r.data)

// ---------------- ⑥ 用户
export const register = (p: { username: string; password: string; nickname?: string; role?: string }) =>
  client.post<TokenResp>('/api/auth/register', p).then((r) => r.data)
export const login = (username: string, password: string) =>
  client.post<TokenResp>('/api/auth/login', { username, password }).then((r) => r.data)
export const logout = () => client.post('/api/auth/logout').then((r) => r.data)
export const me = () => client.get<{ ok: boolean; 用户: ApiUser }>('/api/auth/me').then((r) => r.data)
export const updateProfile = (p: { nickname?: string; phone?: string; email?: string }) =>
  client.put<{ ok: boolean; 用户: ApiUser }>('/api/user/profile', p).then((r) => r.data)
export const changePassword = (old_password: string, new_password: string) =>
  client.put<{ ok: boolean; message: string }>('/api/user/password', { old_password, new_password })
    .then((r) => r.data)
export const getStats = () =>
  client.get<{ ok: boolean; 统计: Record<string, number>; 用户: ApiUser }>('/api/user/stats')
    .then((r) => r.data)

// ---------------- ⑦ 个人中心
export const listResumes = () =>
  client.get<{ ok: boolean; 简历: ResumeRow[] }>('/api/user/resumes').then((r) => r.data)
export const createResume = (title: string, text: string, is_default?: boolean) =>
  client.post<{ ok: boolean; id: number; message: string }>('/api/user/resumes',
    { title, text, is_default }).then((r) => r.data)
export const updateResume = (id: number, title?: string, text?: string) =>
  client.put(`/api/user/resumes/${id}`, { title, text }).then((r) => r.data)
export const setDefaultResume = (id: number) =>
  client.put(`/api/user/resumes/${id}/default`).then((r) => r.data)
export const deleteResume = (id: number) =>
  client.delete(`/api/user/resumes/${id}`).then((r) => r.data)

export const listFavorites = () =>
  client.get<{ ok: boolean; 收藏: FavoriteRow[] }>('/api/user/favorites').then((r) => r.data)
export const addFavorite = (job_id: string, note = '') =>
  client.post<{ ok: boolean; message: string }>('/api/user/favorites', { job_id, note })
    .then((r) => r.data)
export const removeFavorite = (job_id: string) =>
  client.delete(`/api/user/favorites/${job_id}`).then((r) => r.data)

export const listMatches = () =>
  client.get<{ ok: boolean; 历史: MatchHistoryRow[] }>('/api/user/matches').then((r) => r.data)
export const listChats = () =>
  client.get<{ ok: boolean; 历史: ChatHistoryRow[] }>('/api/user/chats').then((r) => r.data)

export type { JobRec }
