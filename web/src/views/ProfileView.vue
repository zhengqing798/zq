<template>
  <div>
    <div class="zq-page-title">个人中心</div>
    <div class="zq-page-desc">
      账号：{{ auth.user?.username }} ｜ 角色：{{ auth.user?.role_label }}
      ｜ 注册于 {{ auth.user?.created_at }}
    </div>

    <div class="kpi-row">
      <div class="kpi">
        <div class="v">{{ myResume ? '已保存' : '未保存' }}</div>
        <div class="l">我的简历</div>
      </div>
      <div class="kpi"><div class="v">{{ stats['收藏岗位数'] ?? 0 }}</div><div class="l">收藏岗位</div></div>
      <div class="kpi"><div class="v">{{ stats['匹配次数'] ?? 0 }}</div><div class="l">匹配次数</div></div>
      <div class="kpi"><div class="v">{{ stats['提问次数'] ?? 0 }}</div><div class="l">提问次数</div></div>
    </div>

    <el-tabs v-model="tab" style="margin-top:14px">
      <!-- 我的简历：粘贴 / 上传 PDF → 解析 → 匹配（原来的「简历」页已并入此处） -->
      <el-tab-pane label="📁 我的简历" name="resumes">
        <div class="rgrid">
          <div class="zq-card pad">
            <div class="zq-section" style="margin-top:0">粘贴简历正文</div>
            <el-input v-model="rtext" type="textarea" :rows="10"
                      placeholder="把简历内容粘贴到这里，例如：姓名、期望岗位、期望城市、学历、工作年限、技能特长…" />
            <div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap">
              <el-button type="primary" :loading="rloading" @click="doParse">解析这份文本</el-button>
              <el-button :loading="rloading" @click="saveResume">
                💾 {{ myResume ? '保存修改' : '保存简历' }}</el-button>
              <el-button text @click="rtext = SAMPLE">填入示例</el-button>
            </div>
          </div>

          <div>
            <div class="zq-card pad">
              <div class="zq-section" style="margin-top:0">上传 PDF 简历</div>
              <el-upload drag :auto-upload="false" :show-file-list="true" accept=".pdf"
                         :on-change="onResumeFile" :limit="1">
                <el-icon class="el-icon--upload"><upload-filled /></el-icon>
                <div class="el-upload__text">拖拽 PDF 到此处，或<em>点击选择</em></div>
                <template #tip>
                  <div class="muted">一份 PDF = 一份简历（多页视为续页）</div>
                </template>
              </el-upload>
            </div>

            <div class="zq-card pad" style="margin-top:12px">
              <div class="zq-section" style="margin-top:0">我的简历</div>
              <template v-if="myResume">
                <el-input v-model="rTitle" maxlength="24" placeholder="简历标题"
                          style="max-width:280px" />
                <div class="muted" style="margin-top:8px">
                  {{ myResume.字数 }} 字 ｜ 更新于 {{ myResume.updated_at }}
                </div>
                <div class="racts">
                  <el-button @click="loadMyResume">✏️ 修改</el-button>
                  <el-button type="primary" @click="saveResume">💾 保存修改</el-button>
                  <el-button type="danger" plain @click="delMyResume">删除</el-button>
                  <el-button @click="goMatch">去岗位推荐 →</el-button>
                </div>
              </template>
              <el-empty v-else description="还没有简历：在左边粘贴正文或在这里上传 PDF，然后点保存" />
            </div>

            <div v-if="resume.parsed" class="zq-card pad" style="margin-top:12px">
              <div class="zq-section" style="margin-top:0">解析结果</div>
              <div class="muted" style="line-height:2">
                姓名：<b>{{ resume.parsed.解析字段['姓名'] || '（未识别）' }}</b> ｜
                期望岗位：{{ resume.parsed.解析字段['期望岗位'] || '—' }} ｜
                期望城市：{{ resume.parsed.解析字段['期望城市'] || '—' }}<br />
                工作年限：{{ resume.parsed.解析字段['工作年限'] }} 年 ｜
                识别技能：<b>{{ resume.parsed.技能数 }}</b> 项
              </div>
              <div style="margin-top:8px">
                <el-tag v-for="s in resume.parsed.技能列表.slice(0, 12)" :key="s" effect="light"
                        style="margin:0 6px 6px 0">{{ s }}</el-tag>
              </div>
              <el-alert v-if="resume.parsed.解析告警.length" type="warning" :closable="false"
                        style="margin-top:8px"
                        :title="'解析告警：' + resume.parsed.解析告警.join('；')" />
              <div style="margin-top:10px">
                <el-button type="primary" @click="goMatch">用这份简历做岗位推荐 →</el-button>
                <el-popover placement="top" :width="420" trigger="click">
                  <template #reference><el-button text>查看全部解析字段</el-button></template>
                  <pre style="max-height:320px;overflow:auto;font-size:12px">{{ resume.parsed.解析字段 }}</pre>
                </el-popover>
              </div>
            </div>
          </div>
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
          <el-empty v-if="!favorites.length" description="还没有收藏：在「岗位」或「岗位推荐」点岗位卡片 → 收藏" />
        </div>
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
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type UploadFile } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import * as api from '../api'
import type { FavoriteRow, ResumeRow } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { useResumeStore } from '../stores/resume'

/** 简历示例（与「填入示例」一致，便于演示解析能力） */
const SAMPLE = `姓名：张伟
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

【项目经验】
使用 Python + Selenium 搭建 UI 自动化框架，覆盖 300 条用例`

const auth = useAuthStore()
const resume = useResumeStore()
const router = useRouter()

const tab = ref('resumes')
const loading = ref(false)
const stats = ref<Record<string, number>>({})
const resumes = ref<ResumeRow[]>([])
const favorites = ref<FavoriteRow[]>([])

/** 一个用户只有一份简历：取唯一的那条（没有则 null） */
const myResume = computed<ResumeRow | null>(() => resumes.value[0] || null)

/* 简历输入（粘贴 / PDF）：原来独立的「简历」页已并入本页 */
const rtext = ref(resume.text || '')
const rTitle = ref('我的简历')
const rloading = ref(false)

// 简历变化时同步标题输入框
watch(myResume, (r) => { rTitle.value = r?.title || '我的简历' })

const pf = reactive({ nickname: '', phone: '', email: '' })
const pw = reactive({ old_password: '', new_password: '', confirm: '' })

async function refresh() {
  loading.value = true
  try {
    // 注意：问答记录、匹配历史两个页签已删除，这里不再拉 /api/user/chats、/api/user/matches
    // （接口与入库逻辑都还在，需要时恢复列表即可）
    const [s, r, f] = await Promise.all([
      api.getStats(), api.listResumes(), api.listFavorites(),
    ])
    stats.value = s.统计
    resumes.value = r.简历
    favorites.value = f.收藏
    pf.nickname = s.用户.nickname
    pf.phone = s.用户.phone
    pf.email = s.用户.email
  } catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}
onMounted(refresh)

/* ---------------- 简历：粘贴解析 / 上传 PDF / 保存 ---------------- */
async function doParse() {
  if (!rtext.value.trim()) return ElMessage.warning('请先粘贴简历正文')
  rloading.value = true
  try {
    const r = await api.parseResumeText(rtext.value)
    resume.setParsed(r, rtext.value)
    ElMessage.success('解析完成，会话 ID：' + r.resume_id)
  } catch { /* 拦截器已提示 */ }
  finally { rloading.value = false }
}

async function onResumeFile(f: UploadFile) {
  const raw = f.raw as File | undefined
  if (!raw) return
  rloading.value = true
  try {
    const r = await api.parseResumePdf(raw)
    // 用解析出的原文填充正文，这样上传 PDF 之后也能"保存简历"
    resume.setParsed(r, r.原文 || '')
    if (r.原文) rtext.value = r.原文
    ElMessage.success('PDF 解析完成（' + r.来源 + '）')
  } catch { /* 拦截器已提示 */ }
  finally { rloading.value = false }
}

/** 保存 / 覆盖那一份简历（一个用户只有一份） */
async function saveResume() {
  const text = rtext.value.trim() || resume.text || ''
  if (!text) return ElMessage.warning('请先粘贴简历正文或上传 PDF')
  rloading.value = true
  try {
    if (myResume.value) {
      await api.updateResume(myResume.value.id, rTitle.value, text)
      ElMessage.success('简历已更新')
    } else {
      const r = await api.createResume(rTitle.value || '我的简历', text)
      ElMessage.success(r.message || '简历已保存')
    }
    await refresh()
    const cur = resumes.value[0]
    if (cur) resume.useSaved(cur.id, cur.title, cur.text)   // 同步给「岗位推荐」用
  } catch { /* 拦截器已提示 */ }
  finally { rloading.value = false }
}

/** 把已保存的正文载入左侧输入框，便于修改 */
function loadMyResume() {
  if (!myResume.value) return
  rtext.value = myResume.value.text
  ElMessage.success('正文已载入，改完点「保存修改」')
}

async function delMyResume() {
  if (!myResume.value) return
  try {
    await ElMessageBox.confirm('确定删除你的简历？', '确认', { type: 'warning' })
    await api.deleteResume(myResume.value.id)
    ElMessage.success('已删除')
    await refresh()
  } catch { /* 取消或失败 */ }
}

/** 带着这份简历去「岗位推荐」 */
function goMatch() {
  if (myResume.value) resume.useSaved(myResume.value.id, myResume.value.title, myResume.value.text)
  router.push('/match')
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

<style scoped>
.rgrid { display: grid; grid-template-columns: 1.3fr 1fr; gap: 14px; }
.racts { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
@media (max-width: 1000px) { .rgrid { grid-template-columns: 1fr; } }
</style>
