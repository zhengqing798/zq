<template>
  <div>
    <div class="zq-page-title">职位推荐</div>
    <div class="zq-page-desc">
      对全量 <b>8,836</b> 个岗位逐对打分（六维加权），返回 Top-N —— 点任意岗位查看<b>六维雷达 + 双口径评分</b>
    </div>

    <!-- 匹配控制条 -->
    <div class="zq-card pad">
      <div class="ctrl">
        <div class="fld">
          <span class="lb">使用简历</span>
          <el-select v-model="src" style="width:230px" placeholder="选择简历">
            <el-option label="本次解析的简历" value="current" :disabled="!resume.resumeId" />
            <el-option v-for="r in savedList" :key="r.id"
                       :label="'📁 ' + r.title" :value="'saved:' + r.id" />
          </el-select>
        </div>
        <div class="fld">
          <span class="lb">返回条数</span>
          <el-slider v-model="topN" :min="5" :max="50" :step="5" style="width:170px" />
          <el-tag effect="plain">{{ topN }} 条</el-tag>
        </div>
        <el-button type="primary" :loading="loading" @click="doMatch">开始匹配</el-button>
        <span v-if="!resume.canMatch()" class="muted">
          还没有简历 → 先去 <router-link to="/resume">📄 简历</router-link> 解析一份
        </span>
      </div>
    </div>

    <!-- 结果区 -->
    <div v-if="result" style="margin-top:16px">
      <div class="kpi-row">
        <div class="kpi"><div class="v">{{ result.推荐数 }}</div><div class="l">推荐岗位数</div></div>
        <div class="kpi"><div class="v">{{ result.打分范围 }}</div><div class="l">打分范围（个岗位）</div></div>
        <div class="kpi"><div class="v">{{ result.权重版本 }}</div><div class="l">匹配权重版本</div></div>
        <div class="kpi"><div class="v">{{ result.耗时秒 }} s</div><div class="l">全量打分耗时</div></div>
        <div class="kpi"><div class="v">{{ filtered.length }}</div><div class="l">当前筛选后条数</div></div>
      </div>

      <div class="layout">
        <!-- 左侧筛选栏（招聘网站风格） -->
        <aside>
          <div class="zq-card pad">
            <div class="zq-section" style="margin-top:0">筛选</div>
            <div class="lb">城市</div>
            <el-select v-model="fCity" clearable placeholder="全部城市" style="width:100%">
              <el-option v-for="c in cities" :key="c" :label="c" :value="c" />
            </el-select>
            <div class="lb" style="margin-top:12px">岗位名称含</div>
            <el-input v-model="fKw" clearable placeholder="如 Java / 测试 / 前端" />
            <div class="lb" style="margin-top:12px">最低匹配分：{{ fScore }}</div>
            <el-slider v-model="fScore" :min="0" :max="100" :step="5" />
            <div class="lb" style="margin-top:4px">排序</div>
            <el-radio-group v-model="sortBy" size="small">
              <el-radio-button value="score">匹配分</el-radio-button>
              <el-radio-button value="salary">薪资</el-radio-button>
            </el-radio-group>
            <el-button text style="margin-top:10px" @click="resetFilter">重置筛选</el-button>
            <div class="muted" style="margin-top:8px">
              筛选作用于本次返回的 Top-{{ topN }}（前端过滤）
            </div>
          </div>

          <div class="zq-card pad" style="margin-top:12px">
            <div class="zq-section" style="margin-top:0">简历摘要</div>
            <div class="muted" style="line-height:1.9">
              姓名：{{ result.简历摘要.姓名 }}<br />
              期望城市：{{ result.简历摘要.期望城市 || '—' }}<br />
              学历序数：{{ result.简历摘要.学历序数 }}<br />
              工作年限：{{ result.简历摘要.工作年限 }} 年<br />
              技能数：{{ result.简历摘要.技能数 }}
            </div>
          </div>
        </aside>

        <!-- 右侧岗位列表 -->
        <section>
          <div v-if="!filtered.length" class="zq-card pad" style="text-align:center;color:#8896ab">
            没有符合筛选条件的岗位，试试放宽条件
          </div>
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
              <el-tag size="small" effect="light">技能命中 {{ j.技能命中数 }}/{{ j.岗位技能要求数 }}</el-tag>
              <el-tag size="small" type="success" effect="light" style="margin-left:6px">
                余弦 {{ j.余弦分 }}</el-tag>
              <el-tag size="small" type="info" effect="plain" style="margin-left:6px">
                距离 {{ j.距离km }} km</el-tag>
            </div>
            <div class="muted" style="margin-top:8px">💡 {{ j.推荐理由 }}</div>
          </div>

          <el-collapse style="margin-top:12px">
            <el-collapse-item title="📎 来源（可追溯到数据文件/报告）">
              <div class="src-list">
                <div v-for="s in result.来源" :key="s"><code>{{ s }}</code></div>
              </div>
            </el-collapse-item>
            <el-collapse-item title="⚠️ 已知局限（如实说明）">
              <div class="muted" style="line-height:1.95">
                · <b>无人工金标</b>：真值都由规则生成，不能宣称「准确率 X%」<br />
                · 简历侧为合成数据（500 份），岗位侧 8,836 条为真实抓取<br />
                · 只覆盖 16 城 / 4 省（闽浙苏皖）<br />
                · <code>经验要求</code> 字段 24.69% 错位，系统按「信息缺失」处理<br />
                · 在线推荐用规则口径（可解释）；模型口径是规则的蒸馏（Spearman 0.9909）
              </div>
            </el-collapse-item>
          </el-collapse>
        </section>
      </div>
    </div>

    <el-empty v-else description="点击「开始匹配」，查看与你简历最匹配的岗位" />

    <!-- 岗位详情抽屉 -->
    <el-drawer v-model="drawer" size="46%" :title="cur?.岗位名称 || ''">
      <template v-if="cur">
        <div class="job-top">
          <div>
            <div class="job-title">{{ cur.岗位名称 }}</div>
            <div class="job-co">{{ cur.公司 }} ｜ {{ cur.城市 }}</div>
          </div>
          <div class="job-salary">{{ cur.岗位薪资 }}</div>
        </div>
        <div class="job-meta">
          {{ cur.经验要求 || '经验不限' }} ｜ {{ cur.学历要求 || '学历不限' }}
          ｜ 技能标签：{{ cur.技能标签 || '—' }}
        </div>

        <el-divider />
        <div class="zq-section" style="margin-top:0">六维得分（雷达图）</div>
        <EChart :option="radarOption" height="290px" />
        <div style="margin-top:6px">
          <el-tag v-for="d in DIMS" :key="d" effect="plain" style="margin:0 6px 6px 0">
            {{ d }} {{ Number(cur[d as keyof typeof cur]).toFixed(1) }}</el-tag>
        </div>

        <el-divider />
        <div class="zq-section" style="margin-top:0">推荐理由</div>
        <div class="chat-bubble">{{ cur.推荐理由 }}</div>

        <el-divider />
        <div class="zq-section" style="margin-top:0">评分双口径（任务5 模型 / 任务6 规则）</div>
        <el-button size="small" :loading="scoring" @click="doScore">计算该岗位的模型分</el-button>
        <div v-if="score" style="margin-top:10px">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="规则总分（主）">
              <b class="salary">{{ score.规则口径.总分 }}</b></el-descriptions-item>
            <el-descriptions-item label="模型预测分（T1）">
              {{ score.模型口径.可用 ? score.模型口径.T1回归_预测总分 : '不可用' }}</el-descriptions-item>
            <el-descriptions-item label="匹配概率（T2）">
              {{ score.模型口径.可用 ? score.模型口径.T2分类_匹配概率 + '%' : '—' }}</el-descriptions-item>
            <el-descriptions-item label="两者差异">
              {{ score.差异 ?? '—' }} 分</el-descriptions-item>
          </el-descriptions>
          <div class="muted" style="margin-top:8px">{{ score.模型口径.口径说明 }}</div>
        </div>

        <el-divider />
        <el-button type="primary" :disabled="!auth.isLogged()" @click="fav">
          ⭐ 收藏这个岗位
        </el-button>
        <span v-if="!auth.isLogged()" class="muted" style="margin-left:8px">登录后可收藏</span>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'
import type { JobRec, ResumeRow, ScoreResp } from '../api/types'
import EChart from '../components/EChart.vue'
import { useAuthStore } from '../stores/auth'
import { useResumeStore } from '../stores/resume'

const DIMS = ['技能', '经验', '学历', '地域', '薪资', '专业证书']
const auth = useAuthStore()
const resume = useResumeStore()

const loading = ref(false)
const scoring = ref(false)
const src = ref('current')
const topN = ref(20)
const savedList = ref<ResumeRow[]>([])
const result = ref(resume.matchResult)
const drawer = ref(false)
const cur = ref<JobRec | null>(null)
const score = ref<ScoreResp | null>(null)

const fCity = ref('')
const fKw = ref('')
const fScore = ref(0)
const sortBy = ref<'score' | 'salary'>('score')

const cities = computed(() => {
  const s = new Set((result.value?.推荐 || []).map((x) => x.城市).filter(Boolean))
  return Array.from(s).sort()
})

function salaryMid(s: string) {
  // "10000-15000元·13薪" → 12500
  const m = String(s || '').match(/(\d+)\D+(\d+)/)
  return m ? (Number(m[1]) + Number(m[2])) / 2 : 0
}

const filtered = computed(() => {
  let list = [...(result.value?.推荐 || [])]
  if (fCity.value) list = list.filter((x) => x.城市 === fCity.value)
  if (fKw.value.trim()) {
    const k = fKw.value.trim()
    list = list.filter((x) => (x.岗位名称 + x.技能标签).includes(k))
  }
  list = list.filter((x) => x.总分 >= fScore.value)
  list.sort((a, b) => sortBy.value === 'score' ? b.总分 - a.总分 : salaryMid(b.岗位薪资) - salaryMid(a.岗位薪资))
  return list
})

const radarOption = computed(() => {
  const v = DIMS.map((d) => Number((cur.value as never as Record<string, number>)?.[d] ?? 0))
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

onMounted(async () => {
  if (auth.isLogged()) {
    try {
      const r = await api.listResumes()
      savedList.value = r.简历
      if (!resume.resumeId && savedList.value.length) {
        const d = savedList.value.find((x) => x.is_default) || savedList.value[0]
        src.value = 'saved:' + d.id
      }
    } catch { /* 忽略 */ }
  }
})

async function doMatch() {
  if (!resume.canMatch()) return ElMessage.warning('请先在「简历」页解析一份简历')
  loading.value = true
  try {
    const body: api.MatchPayload = { top_n: topN.value }
    if (src.value === 'current') body.resume_id = resume.resumeId
    else if (src.value.startsWith('saved:')) body.saved_resume_id = Number(src.value.split(':')[1])
    else body.resume_text = resume.text
    const r = await api.runMatch(body)
    result.value = r
    resume.matchResult = r
    if (r.已存历史) ElMessage.success('已存入匹配历史')
    else ElMessage.success('匹配完成')
  } catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}

function resetFilter() {
  fCity.value = ''; fKw.value = ''; fScore.value = 0; sortBy.value = 'score'
}

function openDetail(j: JobRec) {
  cur.value = j
  score.value = null
  drawer.value = true
}

async function doScore() {
  if (!cur.value) return
  scoring.value = true
  try {
    score.value = await api.runScore(cur.value.岗位ID, resume.resumeId || null, resume.text || null)
  } catch { /* 拦截器已提示 */ }
  finally { scoring.value = false }
}

async function fav() {
  if (!cur.value) return
  try {
    const r = await api.addFavorite(cur.value.岗位ID)
    ElMessage.success(r.message || '已收藏')
  } catch { /* 拦截器已提示 */ }
}
</script>

<style scoped>
.ctrl { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.fld { display: flex; align-items: center; gap: 10px; }
.lb { font-size: 12.5px; color: #6b7a90; display: block; margin-bottom: 6px; }
.layout { display: grid; grid-template-columns: 268px 1fr; gap: 14px; margin-top: 14px; }
@media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } }
</style>
