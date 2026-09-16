<template>
  <div>
    <!-- 搜索区 -->
    <div class="zq-card pad search">
      <div class="row">
        <el-input v-model="kw" size="large" placeholder="搜索岗位名称 / 公司 / 技能，如 Java、测试、Python"
                  clearable style="flex:1" @keyup.enter="search">
          <template #prefix><el-icon><search /></el-icon></template>
        </el-input>
        <el-select v-model="city" size="large" clearable placeholder="全部城市" style="width:150px">
          <el-option v-for="c in opt.城市" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="sort" size="large" style="width:170px">
          <el-option v-for="s in opt.排序" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-button type="primary" size="large" @click="search">搜 索</el-button>
      </div>
      <div class="hot">
        <span class="muted">热门：</span>
        <el-tag v-for="t in ['Java', '软件测试', 'Python', '前端', '算法', '运维', '嵌入式']" :key="t"
                effect="plain" style="cursor:pointer;margin:4px 6px 0 0" @click="kw = t; search()">
          {{ t }}</el-tag>
      </div>
    </div>

    <!-- 数据概览 -->
    <div class="kpi-row" style="margin-top:14px">
      <div class="kpi"><div class="v">{{ fmt(st.总体.岗位总数) }}</div><div class="l">岗位总数</div></div>
      <div class="kpi"><div class="v">{{ fmt(st.总体.公司数) }}</div><div class="l">招聘公司</div></div>
      <div class="kpi"><div class="v">{{ st.总体.城市数 }}</div><div class="l">覆盖城市</div></div>
      <div class="kpi"><div class="v">{{ fmt(st.总体.薪资上限中位数) }}</div><div class="l">薪资上限中位数（元/月）</div></div>
      <div class="kpi"><div class="v">{{ fmt(st.总体.在线岗位数) }}</div><div class="l">招聘方在线岗位</div></div>
    </div>

    <!-- 分类导航 -->
    <div class="zq-card pad" style="margin-top:14px">
      <span class="muted" style="margin-right:10px">岗位分类：</span>
      <el-tag :effect="category === '' ? 'dark' : 'plain'" style="cursor:pointer;margin:0 6px 6px 0"
              @click="pickCat('')">全部 {{ fmt(st.总体.岗位总数) }}</el-tag>
      <el-tag v-for="c in st.按大类" :key="c.名称" style="cursor:pointer;margin:0 6px 6px 0"
              :effect="category === c.名称 ? 'dark' : 'plain'"
              :type="category === c.名称 ? 'primary' : 'info'"
              @click="pickCat(c.名称)">{{ c.名称 }} {{ fmt(c.数量) }}</el-tag>
    </div>

    <!-- 图表 -->
    <div class="charts">
      <div class="zq-card pad">
        <div class="zq-section" style="margin-top:0">各岗位大类分布</div>
        <EChart :option="catBar" height="250px" />
      </div>
      <div class="zq-card pad">
        <div class="zq-section" style="margin-top:0">热门技能 Top12</div>
        <EChart :option="skillBar" height="250px" />
      </div>
    </div>

    <!-- 岗位列表 -->
    <div class="layout">
      <aside>
        <div class="zq-card pad">
          <div class="zq-section" style="margin-top:0">筛选</div>
          <div class="lb">城市</div>
          <el-select v-model="city" clearable placeholder="全部城市" style="width:100%" @change="search">
            <el-option v-for="c in opt.城市" :key="c" :label="c" :value="c" />
          </el-select>
          <div class="lb" style="margin-top:12px">学历要求</div>
          <el-select v-model="edu" clearable placeholder="不限" style="width:100%" @change="search">
            <el-option v-for="e in opt.学历" :key="e" :label="e" :value="e" />
          </el-select>
          <div class="lb" style="margin-top:12px">薪资上限 ≥ {{ salaryMin ? fmt(salaryMin) : '不限' }}</div>
          <el-slider v-model="salaryMin" :min="0" :max="40000" :step="1000" @change="search" />
          <div class="lb" style="margin-top:4px">所属簇</div>
          <el-select v-model="cluster" clearable placeholder="全部" style="width:100%" @change="search">
            <el-option v-for="c in st.按簇" :key="c.名称" :label="c.名称" :value="c.名称" />
          </el-select>
          <el-button text style="margin-top:10px" @click="reset">重置全部条件</el-button>
        </div>
        <div class="zq-card pad" style="margin-top:12px">
          <div class="zq-section" style="margin-top:0">城市分布</div>
          <EChart :option="cityBar" height="300px" />
        </div>
      </aside>

      <section>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <div>
            共 <b class="salary">{{ fmt(list.总数) }}</b> 个岗位
            <span class="muted">（第 {{ list.页码 }} / {{ list.总页数 }} 页）</span>
          </div>
          <el-radio-group v-model="size" size="small" @change="search">
            <el-radio-button :value="20">20/页</el-radio-button>
            <el-radio-button :value="50">50/页</el-radio-button>
          </el-radio-group>
        </div>

        <div v-loading="loading">
          <div v-for="j in list.岗位" :key="j.岗位ID" class="job-card" @click="open(j)">
            <div class="job-top">
              <div class="job-title">{{ j.岗位名称 }}</div>
              <div class="job-salary">{{ j.薪资 || '薪资面议' }}</div>
            </div>
            <div class="job-co">{{ j.公司 }}</div>
            <div class="job-meta">
              {{ j.地区 || j.城市 }} ｜ {{ j.经验要求 || '经验不限' }} ｜ {{ j.学历要求 || '学历不限' }}
              <span v-if="j.是否在线"> ｜ <b style="color:#0e9f6e">在线</b></span>
              <span v-if="j.今日回复数"> ｜ 今日回复 {{ j.今日回复数 }}</span>
            </div>
            <div class="job-tags">
              <el-tag size="small" effect="dark" type="primary">{{ j.岗位大类 }}</el-tag>
              <el-tag v-for="s in j.技能标签.slice(0, 6)" :key="s" size="small" effect="plain"
                      style="margin-left:6px">{{ s }}</el-tag>
            </div>
          </div>
          <el-empty v-if="!list.岗位.length" description="没有符合条件的岗位，试试放宽筛选" />
        </div>

        <el-pagination v-if="list.总页数 > 1" background layout="prev, pager, next, jumper"
                       :total="list.总数" :page-size="size" :current-page="page"
                       style="margin-top:16px;justify-content:center" @current-change="turn" />
      </section>
    </div>

    <!-- 岗位详情 -->
    <el-drawer v-model="drawer" size="46%" :title="cur?.岗位名称 || ''">
      <template v-if="cur">
        <div class="job-top">
          <div>
            <div class="job-title">{{ cur.岗位名称 }}</div>
            <div class="job-co">{{ cur.公司 }} ｜ {{ cur.地区 }}</div>
          </div>
          <div class="job-salary">{{ cur.薪资 }}</div>
        </div>
        <div class="job-tags" style="margin-top:10px">
          <el-tag effect="dark" type="primary">{{ cur.岗位大类 }}</el-tag>
          <el-tag v-if="cur.一级簇名" type="success" effect="light" style="margin-left:6px">
            {{ cur.一级簇名 }}</el-tag>
          <el-tag v-if="cur.二级簇名" type="warning" effect="light" style="margin-left:6px">
            {{ cur.二级簇名 }}</el-tag>
        </div>
        <el-divider />
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="岗位ID">{{ cur.岗位ID }}</el-descriptions-item>
          <el-descriptions-item label="薪资区间">{{ cur.薪资 }}</el-descriptions-item>
          <el-descriptions-item label="经验要求">{{ cur.经验要求 || '不限' }}</el-descriptions-item>
          <el-descriptions-item label="学历要求">{{ cur.学历要求 || '不限' }}</el-descriptions-item>
          <el-descriptions-item label="今日回复数">{{ cur.今日回复数 }}</el-descriptions-item>
          <el-descriptions-item label="在线状态">{{ cur.是否在线 ? '在线' : '离线' }}</el-descriptions-item>
        </el-descriptions>
        <div class="zq-section">技能标签</div>
        <el-tag v-for="s in cur.技能标签" :key="s" effect="light" style="margin:0 6px 6px 0">{{ s }}</el-tag>
        <div class="zq-section">职位描述</div>
        <div class="chat-bubble" style="max-height:320px;overflow:auto">{{ cur.职位描述 }}</div>
        <el-divider />
        <el-button type="primary" :disabled="!auth.isLogged()" @click="fav">⭐ 收藏这个岗位</el-button>
        <el-button :disabled="!resume.canMatch()" :loading="scoring" @click="doScore">
          用我的简历算匹配分</el-button>
        <div v-if="score" style="margin-top:12px">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="规则总分">{{ score.规则口径.总分 }}</el-descriptions-item>
            <el-descriptions-item label="模型预测分">
              {{ score.模型口径.可用 ? score.模型口径.T1回归_预测总分 : '—' }}</el-descriptions-item>
          </el-descriptions>
        </div>
        <div v-else-if="!resume.canMatch()" class="muted" style="margin-top:8px">
          先去「📄 简历」解析一份简历，才能算匹配分
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import * as api from '../api'
import type { JobItem, JobListResp, JobStatsResp } from '../api/jobs'
import type { ScoreResp } from '../api/types'
import EChart from '../components/EChart.vue'
import { useAuthStore } from '../stores/auth'
import { useResumeStore } from '../stores/resume'

const auth = useAuthStore()
const resume = useResumeStore()

const loading = ref(false)
const kw = ref('')
const city = ref('')
const edu = ref('')
const salaryMin = ref(0)
const cluster = ref('')
const sort = ref('default')
const category = ref('')
const page = ref(1)
const size = ref(20)

const st = ref<JobStatsResp>({
  ok: true,
  总体: { 岗位总数: 0, 公司数: 0, 城市数: 0, 省份数: 0, 平均薪资上限: 0,
         薪资下限中位数: 0, 薪资上限中位数: 0, 在线岗位数: 0 },
  按城市: [], 按大类: [], 按学历: [], 按经验: [], 按簇: [], 热门技能: [],
  筛选项: { 城市: [], 大类: [], 学历: [], 省份: [], 排序: [] }, 来源: [],
})
const list = ref<JobListResp>({ ok: true, 总数: 0, 页码: 1, 每页: 20, 总页数: 1, 岗位: [], 来源: [] })

const drawer = ref(false)
const cur = ref<JobItem | null>(null)
const score = ref<ScoreResp | null>(null)
const scoring = ref(false)

const opt = computed(() => st.value.筛选项)
const fmt = (n: number) => (n || 0).toLocaleString('en-US')

const catBar = computed(() => ({
  grid: { left: 70, right: 30, top: 10, bottom: 10 },
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  xAxis: { type: 'value', splitLine: { lineStyle: { color: '#eef3f9' } } },
  yAxis: { type: 'category', inverse: true, axisTick: { show: false },
           data: st.value.按大类.map((x) => x.名称), axisLine: { show: false } },
  series: [{
    type: 'bar', barWidth: 14,
    itemStyle: { borderRadius: [0, 6, 6, 0], color: '#00a6a7' },
    label: { show: true, position: 'right', color: '#6b7a90', fontSize: 11 },
    data: st.value.按大类.map((x) => x.数量),
  }],
}))

const skillBar = computed(() => ({
  grid: { left: 80, right: 30, top: 10, bottom: 10 },
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  xAxis: { type: 'value', splitLine: { lineStyle: { color: '#eef3f9' } } },
  yAxis: { type: 'category', inverse: true, axisTick: { show: false },
           data: st.value.热门技能.slice(0, 12).map((x) => x.名称), axisLine: { show: false } },
  series: [{
    type: 'bar', barWidth: 12,
    itemStyle: { borderRadius: [0, 6, 6, 0], color: '#ffb020' },
    label: { show: true, position: 'right', color: '#6b7a90', fontSize: 11 },
    data: st.value.热门技能.slice(0, 12).map((x) => x.数量),
  }],
}))

const cityBar = computed(() => ({
  grid: { left: 55, right: 24, top: 10, bottom: 10 },
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  xAxis: { type: 'value', splitLine: { lineStyle: { color: '#eef3f9' } } },
  yAxis: { type: 'category', inverse: true, axisTick: { show: false },
           data: st.value.按城市.map((x) => x.名称), axisLine: { show: false },
           axisLabel: { fontSize: 11 } },
  series: [{
    type: 'bar', barWidth: 11,
    itemStyle: { borderRadius: [0, 6, 6, 0], color: '#4dabf7' },
    data: st.value.按城市.map((x) => x.数量),
  }],
}))

async function load(pageNo = 1) {
  loading.value = true
  try {
    list.value = await api.listJobs({
      page: pageNo, size: size.value, city: city.value, category: category.value,
      keyword: kw.value, salary_min: salaryMin.value || 0, edu: edu.value,
      cluster: cluster.value, sort: sort.value,
    })
    page.value = list.value.页码
  } catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}

function search() { load(1) }
function turn(p: number) { load(p) }
function pickCat(c: string) { category.value = c; search() }
function reset() {
  kw.value = ''; city.value = ''; edu.value = ''; salaryMin.value = 0
  cluster.value = ''; sort.value = 'default'; category.value = ''; search()
}

async function open(j: JobItem) {
  cur.value = j
  score.value = null
  drawer.value = true
  try { cur.value = await api.jobDetail(j.岗位ID) as JobItem }
  catch { /* 详情失败仍显示列表里的字段 */ }
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

onMounted(async () => {
  try { st.value = await api.jobStats() } catch { /* 拦截器已提示 */ }
  await load(1)
})
</script>

<style scoped>
.search .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.hot { margin-top: 10px; }
.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
.layout { display: grid; grid-template-columns: 268px 1fr; gap: 14px; margin-top: 14px; }
.lb { font-size: 12.5px; color: #6b7a90; display: block; margin-bottom: 6px; }
@media (max-width: 1100px) {
  .charts, .layout { grid-template-columns: 1fr; }
}
</style>
