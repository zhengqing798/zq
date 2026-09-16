<template>
  <div>
    <div class="zq-page-title">个人中心</div>
    <div class="zq-page-desc">
      账号：{{ auth.user?.username }} ｜ 角色：{{ auth.user?.role_label }}
      ｜ 注册于 {{ auth.user?.created_at }}
    </div>

    <div class="kpi-row">
      <div class="kpi"><div class="v">{{ stats['简历数'] ?? 0 }}</div><div class="l">我的简历</div></div>
      <div class="kpi"><div class="v">{{ stats['收藏岗位数'] ?? 0 }}</div><div class="l">收藏岗位</div></div>
      <div class="kpi"><div class="v">{{ stats['匹配次数'] ?? 0 }}</div><div class="l">匹配次数</div></div>
      <div class="kpi"><div class="v">{{ stats['提问次数'] ?? 0 }}</div><div class="l">提问次数</div></div>
    </div>

    <el-tabs v-model="tab" style="margin-top:14px">
      <!-- 我的简历 -->
      <el-tab-pane label="📁 我的简历" name="resumes">
        <div class="zq-card pad">
          <el-table :data="resumes" size="default" v-loading="loading">
            <el-table-column prop="title" label="标题" min-width="160">
              <template #default="{ row }">
                <b>{{ row.title }}</b>
                <el-tag v-if="row.is_default" size="small" type="success" effect="light"
                        style="margin-left:6px">默认</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="字数" label="字数" width="90" />
            <el-table-column prop="updated_at" label="更新时间" width="170" />
            <el-table-column label="操作" width="250">
              <template #default="{ row }">
                <el-button link type="primary" @click="useIt(row)">用这份匹配</el-button>
                <el-button link @click="setDef(row)" :disabled="row.is_default">设为默认</el-button>
                <el-button link type="danger" @click="del(row)">删除</el-button>
              </template>
            </el-table-column>
            <el-table-column type="expand" width="40">
              <template #default="{ row }">
                <el-input v-model="row.title" size="small" style="max-width:320px;margin-bottom:8px" />
                <el-input v-model="row.text" type="textarea" :rows="6" />
                <el-button type="primary" size="small" style="margin-top:8px"
                           @click="save(row)">保存修改</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!resumes.length" description="还没有保存的简历：到「📄 简历」页粘贴后点保存" />
        </div>
      </el-tab-pane>

      <!-- 我的收藏 -->
      <el-tab-pane :label="'⭐ 我的收藏' + (favorites.length ? '(' + favorites.length + ')' : '')"
                   name="favs">
        <div class="zq-card pad">
          <el-table :data="favorites" v-loading="loading">
            <el-table-column prop="job_id" label="岗位ID" width="100" />
            <el-table-column prop="job_name" label="岗位名称" min-width="170" />
            <el-table-column prop="company" label="公司" min-width="180" show-overflow-tooltip />
            <el-table-column prop="city" label="城市" width="90" />
            <el-table-column prop="salary" label="薪资" width="150">
              <template #default="{ row }"><span class="salary">{{ row.salary }}</span></template>
            </el-table-column>
            <el-table-column prop="created_at" label="收藏时间" width="170" />
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button link type="danger" @click="unfav(row)">取消收藏</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!favorites.length" description="还没有收藏：在「🎯 职位推荐」点岗位卡片 → 收藏" />
        </div>
      </el-tab-pane>

      <!-- 匹配历史 -->
      <el-tab-pane label="🕘 匹配历史" name="matches">
        <div v-for="h in matches" :key="h.id" class="zq-card pad" style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between">
            <b>{{ h.summary }}</b><span class="muted">{{ h.created_at }}</span>
          </div>
          <div class="muted" style="margin:6px 0">
            简历：{{ h.resume_title }} ｜ 返回 Top-{{ h.top_n }}
          </div>
          <el-tag v-for="x in h.推荐" :key="x.岗位ID" effect="plain"
                  style="margin:0 6px 6px 0" :type="x.排名 <= 3 ? 'success' : 'info'">
            #{{ x.排名 }} {{ x.岗位名称 }}（{{ Number(x.总分 || 0).toFixed(1) }} 分）
          </el-tag>
        </div>
        <el-empty v-if="!matches.length" description="还没有匹配记录：登录后使用「🎯 职位推荐」会自动保存" />
      </el-tab-pane>

      <!-- 问答记录 -->
      <el-tab-pane label="💬 问答记录" name="chats">
        <el-collapse v-for="c in chats" :key="c.id" style="margin-bottom:8px">
          <el-collapse-item :title="c.created_at + ' ｜ ' + c.question +
            (c.tool_seq ? '（' + c.tool_seq + '）' : '')">
            <div class="chat-bubble">{{ c.answer }}</div>
            <div style="margin-top:8px">
              <div v-for="s in c.sources" :key="s"><code>{{ s }}</code></div>
            </div>
          </el-collapse-item>
        </el-collapse>
        <el-empty v-if="!chats.length" description="还没有问答记录：登录后使用「💬 智能问答」会自动保存" />
      </el-tab-pane>

      <!-- 账号设置 -->
      <el-tab-pane label="⚙️ 账号设置" name="setting">
        <div class="zq-card pad" style="max-width:640px">
          <div class="zq-section" style="margin-top:0">修改个人资料</div>
          <el-form :model="pf" label-width="80px">
            <el-form-item label="昵称"><el-input v-model="pf.nickname" /></el-form-item>
            <el-form-item label="手机号"><el-input v-model="pf.phone" /></el-form-item>
            <el-form-item label="邮箱"><el-input v-model="pf.email" /></el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveProfile">保存资料</el-button>
            </el-form-item>
          </el-form>
          <el-divider />
          <div class="zq-section" style="margin-top:0">修改密码</div>
          <el-form :model="pw" label-width="80px">
            <el-form-item label="原密码">
              <el-input v-model="pw.old_password" type="password" show-password /></el-form-item>
            <el-form-item label="新密码">
              <el-input v-model="pw.new_password" type="password" show-password
                        placeholder="至少 6 位" /></el-form-item>
            <el-form-item label="确认">
              <el-input v-model="pw.confirm" type="password" show-password /></el-form-item>
            <el-form-item>
              <el-button type="primary" @click="savePw">修改密码</el-button>
            </el-form-item>
          </el-form>
          <el-alert type="info" :closable="false"
                    title="口令以 PBKDF2-HMAC-SHA256（20 万次迭代 + 每用户随机盐）存储，不保存明文；登录令牌 7 天有效，退出即失效" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '../api'
import type { ChatHistoryRow, FavoriteRow, MatchHistoryRow, ResumeRow } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { useResumeStore } from '../stores/resume'

const auth = useAuthStore()
const resume = useResumeStore()
const router = useRouter()

const tab = ref('resumes')
const loading = ref(false)
const stats = ref<Record<string, number>>({})
const resumes = ref<ResumeRow[]>([])
const favorites = ref<FavoriteRow[]>([])
const matches = ref<MatchHistoryRow[]>([])
const chats = ref<ChatHistoryRow[]>([])

const pf = reactive({ nickname: '', phone: '', email: '' })
const pw = reactive({ old_password: '', new_password: '', confirm: '' })

async function refresh() {
  loading.value = true
  try {
    const [s, r, f, m, c] = await Promise.all([
      api.getStats(), api.listResumes(), api.listFavorites(), api.listMatches(), api.listChats(),
    ])
    stats.value = s.统计
    resumes.value = r.简历
    favorites.value = f.收藏
    matches.value = m.历史
    chats.value = c.历史
    pf.nickname = s.用户.nickname
    pf.phone = s.用户.phone
    pf.email = s.用户.email
  } catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}
onMounted(refresh)

async function save(row: ResumeRow) {
  try { await api.updateResume(row.id, row.title, row.text); ElMessage.success('已保存'); refresh() }
  catch { /* 拦截器已提示 */ }
}
async function setDef(row: ResumeRow) {
  try { await api.setDefaultResume(row.id); ElMessage.success('已设为默认'); refresh() }
  catch { /* 拦截器已提示 */ }
}
async function del(row: ResumeRow) {
  try {
    await ElMessageBox.confirm('确定删除简历「' + row.title + '」？', '确认', { type: 'warning' })
    await api.deleteResume(row.id); ElMessage.success('已删除'); refresh()
  } catch { /* 取消或失败 */ }
}
async function useIt(row: ResumeRow) {
  resume.useSaved(row.id, row.title, row.text)
  try {
    resume.matchResult = await api.runMatch({ saved_resume_id: row.id, top_n: 20 })
    ElMessage.success('已用这份简历匹配，正在跳转…')
    router.push('/jobs')
  } catch { /* 拦截器已提示 */ }
}
async function unfav(row: FavoriteRow) {
  try { await api.removeFavorite(row.job_id); ElMessage.success('已取消收藏'); refresh() }
  catch { /* 拦截器已提示 */ }
}
async function saveProfile() {
  try {
    await api.updateProfile({ nickname: pf.nickname, phone: pf.phone, email: pf.email })
    await auth.fetchMe()
    ElMessage.success('资料已更新')
  } catch { /* 拦截器已提示 */ }
}
async function savePw() {
  if (pw.new_password !== pw.confirm) return ElMessage.warning('两次输入的新密码不一致')
  try {
    const r = await api.changePassword(pw.old_password, pw.new_password)
    ElMessage.success(r.message || '已修改')
    pw.old_password = pw.new_password = pw.confirm = ''
  } catch { /* 拦截器已提示 */ }
}
</script>
