<template>
  <div v-loading="loading" class="jobpage">
    <div class="back">
      <el-button link @click="goBack">← 返回</el-button>
      <span class="muted">岗位ID：{{ job?.岗位ID }}</span>
    </div>

    <template v-if="job">
      <!-- ① 头部 -->
      <div class="zq-card pad head">
        <div class="row1">
          <div class="hmain">
            <div class="jname">{{ job.岗位名称 }}</div>
            <div class="meta">
              <span>{{ job.地区 || job.城市 }}</span><i>·</i>
              <span>{{ job.经验要求 || '经验不限' }}</span><i>·</i>
              <span>{{ job.学历要求 || '学历不限' }}</span>
              <el-tag v-if="job.是否在线" size="small" type="success" effect="light" class="ml">在线</el-tag>
            </div>
            <div class="tags">
              <el-tag size="small" effect="dark" type="primary">{{ job.岗位大类 }}</el-tag>
              <el-tag v-if="job.一级簇名" size="small" type="success" effect="light" class="ml">
                {{ job.一级簇名 }}</el-tag>
              <el-tag v-if="job.二级簇名" size="small" type="warning" effect="light" class="ml">
                {{ job.二级簇名 }}</el-tag>
            </div>
          </div>
          <div class="hright">
            <div class="salary">{{ job.薪资 || '薪资面议' }}</div>
            <div class="acts">
              <!-- 收藏：未收藏是空心灰星，收藏后变黄星（再点一次取消）
                   星标颜色用行内样式绑定：Element Plus 的按钮 color / hover 会盖掉 scoped 类选择器 -->
              <el-button class="favbtn" :class="{ faved }" :disabled="!auth.isLogged()"
                         :loading="faving"
                         :style="faved ? { borderColor: '#f7ba2a', color: '#b8860b', background: '#fffbf0' } : {}"
                         @click="toggleFav">
                <el-icon :style="{ color: faved ? '#f7ba2a' : '#c8d2e0', fontSize: '16px' }">
                  <StarFilled v-if="faved" />
                  <Star v-else />
                </el-icon>
                <span>{{ faved ? '已收藏' : '收藏' }}</span>
              </el-button>
              <el-button :disabled="!resume.canMatch()" :loading="scoring" @click="doScore">
                用我的简历算匹配分</el-button>
            </div>
            <div v-if="!auth.isLogged()" class="muted">登录后可收藏</div>
          </div>
        </div>
      </div>

      <div class="layout">
        <main class="main">
          <!-- ② 与我简历的匹配（进页面自动算一次；有简历就显示，不限于 Top-50 里的岗位） -->
          <template v-if="sixDim">
            <div class="zq-card pad">
              <div class="zq-section" style="margin-top:0">
                与我简历的匹配<template v-if="match">（推荐排名第 {{ match.排名 }}）</template>
              </div>
              <div class="scorebar">
                <div class="big">
                  <b class="salary">{{ ruleTotal }}</b><em>分</em>
                  <span class="lbl">规则口径（主）</span>
                </div>
                <div v-if="score?.模型口径.可用" class="cell">
                  <b>{{ score.模型口径.T1回归_预测总分 }}</b>
                  <span class="lbl">模型预测分</span>
                </div>
                <div v-if="score?.模型口径.可用" class="cell">
                  <b>{{ score.模型口径.T2分类_匹配概率 }}%</b>
                  <span class="lbl">匹配概率</span>
                </div>
                <div class="cell">
                  <b>{{ skillHit }}</b>
                  <span class="lbl">技能命中</span>
                </div>
                <div class="cell">
                  <b>{{ cosText }}</b>
                  <span class="lbl">技能余弦</span>
                </div>
                <div class="cell">
                  <b>{{ distText }}</b>
                  <span class="lbl">通勤距离</span>
                </div>
              </div>
              <EChart :option="radarOption" height="255px" />
              <div>
                <el-tag v-for="d in DIMS" :key="d" effect="plain" style="margin:0 6px 6px 0">
                  {{ d }} {{ Number(sixDim[d] ?? 0).toFixed(1) }}</el-tag>
              </div>
              <div v-if="match" class="reason">💡 {{ match.推荐理由 }}</div>
            </div>
          </template>

          <!-- ③ 评分对比 -->
          <div v-if="score" class="zq-card pad" style="margin-top:12px">
            <div class="zq-section" style="margin-top:0">评分对比</div>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="规则总分">{{ score.规则口径.总分 }}</el-descriptions-item>
              <el-descriptions-item label="模型预测分">
                {{ score.模型口径.可用 ? score.模型口径.T1回归_预测总分 : '不可用' }}</el-descriptions-item>
              <el-descriptions-item label="匹配概率">
                {{ score.模型口径.可用 ? score.模型口径.T2分类_匹配概率 + '%' : '—' }}</el-descriptions-item>
              <el-descriptions-item label="两者差异">{{ score.差异 ?? '—' }} 分</el-descriptions-item>
            </el-descriptions>
          </div>

          <!-- ④ 技能标签 + 职位描述 -->
          <div class="zq-card pad" style="margin-top:12px">
            <div class="zq-section" style="margin-top:0">技能标签</div>
            <el-tag v-for="s in job.技能标签" :key="s" effect="light" class="ml0">{{ s }}</el-tag>
            <div v-if="!job.技能标签.length" class="muted">该岗位未标注技能标签</div>
            <el-divider />
            <div class="zq-section">职位描述</div>
            <div class="desc">{{ job.职位描述 || '（无描述）' }}</div>
          </div>
        </main>

        <aside class="side">
          <!-- ⑤ 公司与招聘者 -->
          <div class="zq-card pad panel">
            <div class="zq-section" style="margin-top:0">公司</div>
            <div class="comname" @click="goCompany">{{ job.公司 }}</div>
            <div class="muted" style="margin-top:6px">
              <template v-if="job.同公司岗位数 > 1">在招 {{ job.同公司岗位数 }} 个职位</template>
              <template v-else>当前在招 1 个职位</template>
            </div>
            <div class="hrbox">
              <div class="avatar">{{ job.招聘者.slice(0, 1) }}</div>
              <div>
                <div><b>{{ job.招聘者 }}</b> <span class="muted">{{ job.招聘者职位 }}</span></div>
                <div class="muted">{{ job.回复文案 || '暂无回复数据' }}</div>
              </div>
            </div>
          </div>

          <!-- ⑥ 同公司其他在招岗位 -->
          <div v-if="siblings.length" class="zq-card pad panel">
            <div class="zq-section" style="margin-top:0">该公司其他在招岗位（{{ siblings.length }}）</div>
            <div v-for="s in siblings" :key="s.岗位ID" class="sib" @click="openJob(s.岗位ID)">
              <span class="sibname">{{ s.岗位名称 }}</span>
              <span class="sibsal">{{ s.薪资 }}</span>
            </div>
          </div>
        </aside>
      </div>
    </template>

    <el-empty v-else-if="!loading" description="岗位不存在（ID 可能有误）" />
  </div>
</template>

<script setup lang="ts">
/**
 * 岗位详情页（每个岗位一个独立 URL：`#/job/J0020`）
 *
 * · 从各列表页点岗位都跳到这里，不再用右侧抽屉
 * · 如果本次会话做过人岗匹配、且该岗位在结果里，就额外展示「与我简历的匹配」（雷达图 + 推荐理由）
 * · 支持收藏、用规则/模型双口径算分、跳该公司详情页、看同公司其他在招岗位
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Star, StarFilled } from '@element-plus/icons-vue'
import * as api from '../api'
import type { JobItem } from '../api/jobs'
import type { JobRec, ScoreResp } from '../api/types'
import EChart from '../components/EChart.vue'
import { useAuthStore } from '../stores/auth'
import { useResumeStore } from '../stores/resume'

const DIMS = ['技能', '经验', '学历', '地域', '薪资', '专业证书']

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const resume = useResumeStore()

const loading = ref(false)
const job = ref<JobItem | null>(null)
const score = ref<ScoreResp | null>(null)
const scoring = ref(false)
const faving = ref(false)
/** 当前岗位是否已被我收藏（决定星星是空心灰还是实心黄） */
const faved = ref(false)
const siblings = ref<{ 岗位ID: string; 岗位名称: string; 薪资: string }[]>([])

/** 本次会话的匹配结果里如果有这个岗位，就把推荐理由/排名带出来 */
const match = computed<JobRec | null>(() => {
  const list = resume.matchResult?.推荐 || []
  return list.find((x) => x.岗位ID === job.value?.岗位ID) || null
})

/**
 * 六维得分：优先用 `/api/score` 的结果（**每个岗位进页面都会算一次**，
 * 不限于匹配 Top-50 里的岗位）；没有 score 时退回匹配结果里的六维。
 */
const sixDim = computed<Record<string, number> | null>(() => {
  const d = score.value?.规则口径?.六维分 as Record<string, number> | undefined
  if (d && Object.keys(d).length) return d
  const m = match.value as unknown as Record<string, number> | null
  if (m) {
    return { 技能: m.技能, 经验: m.经验, 学历: m.学历, 地域: m.地域, 薪资: m.薪资, 专业证书: m.专业证书 }
  }
  return null
})
const ruleTotal = computed(() => score.value?.规则口径?.总分 ?? match.value?.总分 ?? 0)
const skillHit = computed(() => {
  const r = score.value?.规则口径 as Record<string, number> | undefined
  if (r && r.岗位技能要求数 !== undefined) return `${r.技能命中数}/${r.岗位技能要求数}`
  return match.value ? `${match.value.技能命中数}/${match.value.岗位技能要求数}` : '—'
})
const cosText = computed(() => {
  const r = score.value?.规则口径 as Record<string, number> | undefined
  return r?.TFIDF余弦 !== undefined ? String(r.TFIDF余弦) : (match.value ? String(match.value.余弦分) : '—')
})
const distText = computed(() => {
  const r = score.value?.规则口径 as Record<string, number> | undefined
  const km = r?.距离km !== undefined ? r.距离km : match.value?.距离km
  return km === undefined || km === null || Number(km) < 0 ? '—' : `${km} km`
})

const radarOption = computed(() => {
  const six = sixDim.value || {}
  const v = DIMS.map((d) => Number(six[d] ?? 0))
  return {
    tooltip: {},
    radar: {
      indicator: DIMS.map((d) => ({ name: d, max: 100 })),
      radius: '62%', splitNumber: 4,
      axisName: { color: '#41506b', fontSize: 12 },
      splitLine: { lineStyle: { color: '#e8eef6' } },
      splitArea: { areaStyle: { color: ['#fff', '#f8fbfb'] } },
      axisLine: { lineStyle: { color: '#e8eef6' } },
    },
    series: [{
      type: 'radar', symbolSize: 5,
      areaStyle: { color: 'rgba(0,166,167,.28)' },
      lineStyle: { color: '#00a6a7', width: 2 },
      itemStyle: { color: '#00a6a7' },
      data: [{ value: v, name: '六维得分' }],
    }],
  }
})

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/jobs')
}
function goCompany() {
  if (job.value?.公司ID) router.push('/company/' + job.value.公司ID)
}
function openJob(jobId: string) { router.push('/job/' + jobId) }

async function load() {
  const id = String(route.params.id || '')
  loading.value = true
  score.value = null
  siblings.value = []
  job.value = null
  faved.value = false
  try {
    job.value = (await api.jobDetail(id)) as JobItem
    // 是否已收藏（登录时查一次我的收藏列表，决定星星颜色）
    if (auth.isLogged()) {
      try {
        const f = await api.listFavorites()
        faved.value = (f.收藏 || []).some((x) => x.job_id === job.value?.岗位ID)
      } catch { /* 拿不到收藏态就按未收藏显示 */ }
    }
    // **进页面就算一次「我这份简历 vs 这个岗位」的匹配分**
    // 直接用「已保存的简历」时 store 可能是空的（比如刷新后直接打开岗位页），先补灌一次
    if (!resume.canMatch() && auth.isLogged()) {
      try {
        const r = await api.listResumes()
        const d = (r.简历 || []).find((x) => x.is_default) || (r.简历 || [])[0]
        if (d) resume.useSaved(d.id, d.title, d.text)
      } catch { /* 拿不到简历就不显示匹配分 */ }
    }
    if (resume.canMatch()) await calcScore()
    // 同公司其他在招岗位（有公司ID时才能取）
    if (job.value.公司ID) {
      try {
        const c = await api.companyDetail(job.value.公司ID)
        siblings.value = (c.在招岗位 || [])
          .filter((x) => x.岗位ID !== job.value?.岗位ID)
          .slice(0, 8)
          .map((x) => ({ 岗位ID: x.岗位ID, 岗位名称: x.岗位名称, 薪资: x.薪资 }))
      } catch { /* 公司详情不可用不影响主内容 */ }
    }
  } catch { job.value = null }
  finally { loading.value = false }
}

async function doScore() {
  await calcScore()
}

/** 算「我这份简历 vs 这个岗位」的规则分（六维）+ 模型分；进页面自动调一次，也可手动重算 */
async function calcScore() {
  if (!job.value) return
  scoring.value = true
  try {
    score.value = await api.runScore(job.value.岗位ID, resume.resumeId || null, resume.text || null)
  } catch { /* 拦截器已提示 */ }
  finally { scoring.value = false }
}

/** 收藏 / 取消收藏：收藏后星星变黄，再点一次取消 */
async function toggleFav() {
  if (!job.value || faving.value) return
  faving.value = true
  try {
    if (faved.value) {
      const r = await api.removeFavorite(job.value.岗位ID)
      faved.value = false
      ElMessage.success(r.message || '已取消收藏')
    } else {
      const r = await api.addFavorite(job.value.岗位ID)
      faved.value = true
      ElMessage.success(r.message || '已收藏')
    }
  } catch { /* 拦截器已提示 */ }
  finally { faving.value = false }
}

watch(() => route.params.id, load)
onMounted(load)
</script>

<style scoped>
.jobpage { max-width: 1180px; margin: 0 auto; }
.back { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.muted { color: #8896ab; font-size: 12.5px; }
.ml { margin-left: 6px; }
.ml0 { margin: 0 6px 6px 0; }

.head { padding: 18px 20px; }
.row1 { display: flex; gap: 20px; align-items: flex-start; }
.hmain { flex: 1; min-width: 0; }
.jname { font-size: 22px; font-weight: 800; color: #16233a; line-height: 1.35; }
.meta { margin-top: 8px; color: #5b6b7f; font-size: 13px; display: flex; align-items: center;
  flex-wrap: wrap; gap: 6px; }
.meta i { color: #c9d3e0; font-style: normal; }
.tags { margin-top: 10px; }
.hright { flex: none; text-align: right; }
.salary { font-size: 24px; font-weight: 800; color: #ff6a00; white-space: nowrap; }
.acts { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; align-items: flex-end; }
.acts :deep(.el-button) { margin-left: 0; }

/* 收藏按钮：类名保留（便于测试选择与主题覆盖），颜色由模板里的行内样式控制 */
.favbtn .star { font-size: 16px; }

.layout { display: flex; gap: 16px; align-items: flex-start; margin-top: 14px; }
.main { flex: 1; min-width: 0; }
.side { width: 330px; flex: none; }
.panel { border-radius: 12px; }
.panel + .panel { margin-top: 12px; }
.comname { font-size: 15.5px; font-weight: 700; color: #41506b; cursor: pointer; }
.comname:hover { color: var(--el-color-primary); }
.hrbox { display: flex; align-items: center; gap: 10px; margin-top: 12px; background: #f7fbfb;
  border: 1px solid #e6f4f4; border-radius: 10px; padding: 10px 12px; font-size: 13px; }
.avatar { width: 36px; height: 36px; border-radius: 50%; flex: none; color: #fff; font-size: 16px;
  display: flex; align-items: center; justify-content: center; font-weight: 700;
  background: linear-gradient(135deg, #00a6a7, #12c2b4); }
.desc { background: #fbfcfe; border: 1px solid var(--zq-border); border-radius: 10px;
  padding: 14px 16px; white-space: pre-wrap; line-height: 1.85; font-size: 14px; }
.reason { margin-top: 6px; color: #5b6b7f; font-size: 13px; }
/* 匹配分概览条 */
.scorebar { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px 26px; margin: 4px 0 8px; }
.scorebar .big { display: flex; align-items: baseline; gap: 4px; }
.scorebar .big b { font-size: 32px; font-weight: 800; }
.scorebar .big em { font-style: normal; color: #ff6a00; font-weight: 700; }
.scorebar .cell { display: flex; flex-direction: column; line-height: 1.25; }
.scorebar .cell b { font-size: 19px; font-weight: 800; color: #16233a; }
.scorebar .lbl { font-size: 12px; color: #8896ab; }
.scorebar .big .lbl { margin-left: 6px; }
.sib { display: flex; justify-content: space-between; gap: 10px; padding: 6px 0; cursor: pointer;
  border-bottom: 1px dashed #eef3f9; font-size: 13px; }
.sib:last-child { border-bottom: none; }
.sib:hover .sibname { color: var(--el-color-primary); }
.sibname { color: #41506b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sibsal { color: #ff6a00; font-weight: 700; white-space: nowrap; }

@media (max-width: 980px) {
  .layout { flex-direction: column; }
  .side { width: 100%; }
  .row1 { flex-direction: column; }
  .hright { text-align: left; }
  .acts { align-items: flex-start; }
}
</style>
