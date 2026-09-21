<template>
  <div>
    <div class="zq-page-title">岗位推荐</div>

    <!-- ① 顶部控制 + 筛选（全部在顶部，没有侧边栏） -->
    <div class="zq-card pad">
      <div class="ctrl">
        <div class="fld">
          <span class="lb">使用简历</span>
          <el-select v-model="src" style="width:240px" placeholder="选择简历">
            <el-option label="本次解析的简历" value="current" :disabled="!resume.resumeId" />
            <el-option v-for="r in savedList" :key="r.id"
                       :label="'📁 ' + r.title" :value="'saved:' + r.id" />
          </el-select>
        </div>
        <el-button type="primary" :loading="loading" @click="doMatch">重新推荐</el-button>
      </div>

      <!-- 优先维度（点一下换排序口径） -->
      <div class="frow">
        <span class="flb">优先：</span>
        <a v-for="p in PRIORITIES" :key="p.value" :class="{ on: priority === p.value }"
           @click="priority = p.value">{{ p.label }}</a>
      </div>

      <!-- 其他筛选 -->
      <div class="frow">
        <span class="flb">城市：</span>
        <el-select v-model="fCity" clearable placeholder="全部城市" size="small" style="width:150px">
          <el-option v-for="c in cities" :key="c" :label="c" :value="c" />
        </el-select>
        <span class="flb" style="margin-left:10px">岗位名含：</span>
        <el-input v-model="fKw" clearable size="small" placeholder="如 Java / 测试 / 前端"
                  style="width:190px" />
        <span class="flb" style="margin-left:10px">最低匹配分：{{ fScore }}</span>
        <el-slider v-model="fScore" :min="0" :max="100" :step="5" style="width:150px" />
        <el-button text size="small" @click="resetFilter">重置</el-button>
      </div>

      <!-- 一行摘要：简历 + 结果条数 -->
      <div v-if="result" class="summary">
        <span class="muted">
          {{ result.简历摘要.姓名 }} ｜ 期望城市 {{ result.简历摘要.期望城市 || '—' }}
          ｜ 工作年限 {{ result.简历摘要.工作年限 }} 年 ｜ 技能 {{ result.简历摘要.技能数 }} 项
        </span>
        <span class="right">
          共 <b class="num">{{ filtered.length }}</b> 条
        </span>
      </div>
    </div>

    <!-- ② 推荐结果（单列全宽） -->
    <div v-if="result" v-loading="loading" class="joblist">
      <el-empty v-if="!filtered.length" description="没有符合筛选条件的岗位，试试放宽条件" />
      <div v-for="j in filtered" :key="j.岗位ID" class="job-card" @click="openDetail(j)">
        <div class="job-top">
          <div class="job-title">
            <el-tag v-if="j.排名 <= 3" :type="j.排名 === 1 ? 'danger' : 'warning'"
                    size="small" effect="dark" style="margin-right:6px">TOP{{ j.排名 }}</el-tag>
            {{ j.岗位名称 }}
          </div>
          <div class="job-salary">{{ j.岗位薪资 || '薪资面议' }}</div>
        </div>
        <div class="job-co">{{ j.公司 }}</div>
        <div class="job-meta">
          {{ j.城市 || '—' }} ｜ {{ j.经验要求 || '经验不限' }} ｜ {{ j.学历要求 || '学历不限' }}
          ｜ 匹配度 <b class="salary">{{ j.总分.toFixed(1) }}</b> 分
        </div>
        <div class="job-tags">
          <el-tag size="small" :type="priority === 'skill' ? 'success' : 'info'"
                  :effect="priority === 'skill' ? 'dark' : 'light'">
            技能 {{ j.技能.toFixed(1) }}</el-tag>
          <el-tag size="small" :type="priority === 'geo' ? 'success' : 'info'"
                  :effect="priority === 'geo' ? 'dark' : 'light'" style="margin-left:6px">
            地域 {{ j.地域.toFixed(1) }}（{{ j.距离km }} km）</el-tag>
          <el-tag size="small" :type="priority === 'exp' ? 'success' : 'info'"
                  :effect="priority === 'exp' ? 'dark' : 'light'" style="margin-left:6px">
            经验 {{ j.经验.toFixed(1) }}</el-tag>
          <el-tag size="small" effect="plain" style="margin-left:6px">
            技能命中 {{ j.技能命中数 }}/{{ j.岗位技能要求数 }}</el-tag>
          <el-tag size="small" effect="plain" style="margin-left:6px">余弦 {{ j.余弦分 }}</el-tag>
        </div>
        <div class="muted" style="margin-top:8px">💡 {{ j.推荐理由 }}</div>
      </div>
    </div>

    <el-empty v-else-if="!loading" description="先在个人中心粘贴或上传一份简历，这里会自动给出评分最高的岗位" />
  </div>
</template>

<script setup lang="ts">
/**
 * 「岗位推荐」页（需登录）：用简历做六维加权匹配。
 *
 * · 进入页面**自动拉满评分最高的 50 条**（有简历就自动匹配，不用手动点）
 * · 顶部可按「优先维度」重排这 50 条：综合评分 / 技能匹配 / 地理位置 / 工作经验
 * · 顶部另有城市、岗位名关键词、最低匹配分三个筛选；本页**没有侧边栏**
 * · 点岗位 → 跳该岗位的独立详情页（匹配明细/雷达图在那边）
 * 简历不在本页输入——统一在个人中心粘贴/上传（见 ProfileView）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as api from '../api'
import type { JobRec, ResumeRow } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { useResumeStore } from '../stores/resume'

/** 优先维度：默认按综合评分（= 六维加权总分） */
const PRIORITIES = [
  { value: 'score', label: '综合评分' },
  { value: 'skill', label: '技能匹配' },
  { value: 'geo', label: '地理位置' },
  { value: 'exp', label: '工作经验' },
] as const

const auth = useAuthStore()
const resume = useResumeStore()
const router = useRouter()

const loading = ref(false)
const src = ref('current')
const topN = ref(50)                    // 固定拉满评分最高的 50 条（页面上不再放条数控件）
const savedList = ref<ResumeRow[]>([])
const result = ref(resume.matchResult)

const fCity = ref('')
const fKw = ref('')
const fScore = ref(0)
const priority = ref<'score' | 'skill' | 'geo' | 'exp'>('score')

const cities = computed(() => {
  const s = new Set((result.value?.推荐 || []).map((x) => x.城市).filter(Boolean))
  return Array.from(s).sort()
})

/** 按优先维度排序（同分时用综合评分兜底，保证顺序稳定） */
const sorted = computed(() => {
  const list = [...(result.value?.推荐 || [])]
  const by = {
    score: (a: JobRec, b: JobRec) => b.总分 - a.总分,
    skill: (a: JobRec, b: JobRec) => b.技能 - a.技能 || b.总分 - a.总分,
    geo: (a: JobRec, b: JobRec) => b.地域 - a.地域 || a.距离km - b.距离km || b.总分 - a.总分,
    exp: (a: JobRec, b: JobRec) => b.经验 - a.经验 || b.总分 - a.总分,
  }[priority.value]
  return list.sort(by)
})

const filtered = computed(() => {
  let list = sorted.value
  if (fCity.value) list = list.filter((x) => x.城市 === fCity.value)
  if (fKw.value.trim()) {
    const k = fKw.value.trim()
    list = list.filter((x) => (x.岗位名称 + x.技能标签).includes(k))
  }
  return list.filter((x) => x.总分 >= fScore.value)
})

function resetFilter() {
  fCity.value = ''; fKw.value = ''; fScore.value = 0; priority.value = 'score'
}

async function doMatch(quiet = false) {
  // 直接用「已保存的简历」匹配时，只要拿到 id 就能匹配（后端按 saved_resume_id 取简历），
  // 不强制要求 store 里已经有内容——否则"登录后直接进本页"会被判成没有简历
  const canRun = resume.canMatch() || src.value.startsWith('saved:')
  if (!canRun) {
    if (!quiet) ElMessage.warning('请先在个人中心粘贴或上传一份简历')
    return
  }
  loading.value = true
  try {
    const body: api.MatchPayload = { top_n: topN.value }
    if (src.value === 'current') body.resume_id = resume.resumeId
    else if (src.value.startsWith('saved:')) body.saved_resume_id = Number(src.value.split(':')[1])
    else body.resume_text = resume.text
    const r = await api.runMatch(body)
    result.value = r
    resume.matchResult = r
    if (!quiet) ElMessage.success(r.已存历史 ? '已重新推荐并存入历史' : '已重新推荐')
  } catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}

/** 点岗位 → 跳独立详情页（匹配明细/雷达图会显示在那边） */
function openDetail(j: JobRec) {
  router.push('/job/' + j.岗位ID)
}

onMounted(async () => {
  if (auth.isLogged()) {
    try {
      const r = await api.listResumes()
      savedList.value = r.简历
      if (!resume.resumeId && savedList.value.length) {
        const d = savedList.value.find((x) => x.is_default) || savedList.value[0]
        src.value = 'saved:' + d.id
        // 同步进 store：本页的「用我的简历算匹配分」、岗位详情页的匹配面板都要用
        resume.useSaved(d.id, d.title, d.text)
      }
    } catch { /* 忽略 */ }
  }
  // 已有结果就不再打扰；否则自动拉一次 Top-50
  if (!result.value) await doMatch(true)
})
</script>

<style scoped>
.ctrl { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.fld { display: flex; align-items: center; gap: 10px; }
.lb { font-size: 12.5px; color: #6b7a90; }
.frow { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; padding-top: 10px;
  margin-top: 10px; border-top: 1px dashed #eef3f9; }
.flb { color: #8896ab; font-size: 13px; flex: none; }
.frow a { color: #41506b; font-size: 13.5px; cursor: pointer; }
.frow a:hover { color: var(--el-color-primary); }
.frow a.on { color: var(--el-color-primary); font-weight: 700; }
.summary { display: flex; align-items: center; gap: 12px; margin-top: 10px; }
.summary .right { margin-left: auto; }
.summary .num { color: #ff6a00; font-size: 16px; }
.joblist { margin-top: 14px; }
</style>
