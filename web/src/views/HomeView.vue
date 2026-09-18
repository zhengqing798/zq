<template>
  <div class="home">
    <!-- ① 顶部：城市切换 + 搜索 + 热门职位 -->
    <div class="topbar">
      <div class="cityline">
        <span class="cur">📍 {{ city || '全部城市' }}</span>
        <div class="cities">
          <a :class="{ on: !city }" @click="pickCity('')">全部</a>
          <a v-for="c in st.按城市" :key="c.名称" :class="{ on: city === c.名称 }"
             @click="pickCity(c.名称)">{{ c.名称 }}</a>
        </div>
      </div>
      <div class="searchline">
        <el-input v-model="kw" size="large" class="sinput"
                  :placeholder="(city || '全部') + ' 搜索职位 / 公司 / 技能'"
                  clearable @keyup.enter="search">
          <template #prepend>
            <el-select v-model="category" placeholder="职位类型" clearable
                       style="width:126px" @change="search">
              <el-option v-for="g in st.分类导航" :key="g.大类" :label="g.大类" :value="g.大类" />
            </el-select>
          </template>
          <template #append>
            <el-button type="primary" :icon="Search" @click="search">搜索</el-button>
          </template>
        </el-input>
        <div class="hot">
          <span class="lb">热门职位：</span>
          <a v-for="k in st.热门搜索" :key="k.名称" @click="kw = k.名称; search()">{{ k.名称 }}</a>
        </div>
      </div>
    </div>

    <!-- ② 筛选栏 -->
    <div class="filters">
      <div class="frow">
        <span class="flb">区域：</span>
        <a :class="{ on: !district }" @click="setDistrict('')">不限</a>
        <a v-for="d in districts" :key="d.名称" :class="{ on: district === d.名称 }"
           @click="setDistrict(d.名称)">{{ d.名称 }}<em>{{ d.数量 }}</em></a>
        <span v-if="!city" class="tip">（先选城市才能按区域筛）</span>
      </div>
      <div class="frow">
        <span class="flb">薪资：</span>
        <a :class="{ on: !salaryMin }" @click="setSalary(0)">不限</a>
        <a v-for="s in salaryOpts" :key="s.v" :class="{ on: salaryMin === s.v }"
           @click="setSalary(s.v)">{{ s.t }}</a>
      </div>
      <div class="frow">
        <span class="flb">学历：</span>
        <a :class="{ on: !edu }" @click="setEdu('')">不限</a>
        <a v-for="e in st.按学历" :key="e.名称" :class="{ on: edu === e.名称 }"
           @click="setEdu(e.名称)">{{ e.名称 }}<em>{{ e.数量 }}</em></a>
      </div>
      <div class="frow">
        <span class="flb">排序：</span>
        <a v-for="s in st.筛选项.排序" :key="s.value" :class="{ on: sort === s.value }"
           @click="sort = s.value; search()">{{ s.label }}</a>
      </div>
    </div>

    <!-- ③ 结果统计 -->
    <div class="resultbar">
      <span>共 <b class="num">{{ fmt(list.总数) }}</b> 个职位</span>
      <span class="muted">{{ city || '全部城市' }}{{ district ? ' · ' + district : '' }}{{ category ? ' · ' + category : '' }}{{ kw ? ' · ' + kw : '' }}</span>
      <span class="right">
        <el-radio-group v-model="size" size="small" @change="search">
          <el-radio-button :value="20">20/页</el-radio-button>
          <el-radio-button :value="50">50/页</el-radio-button>
        </el-radio-group>
      </span>
    </div>

    <!-- ④ 职位列表（左：职位 / 右：公司 + 招聘者） -->
    <div v-loading="loading" class="joblist">
      <div v-for="j in list.岗位" :key="j.岗位ID" class="jcard" @click="open(j)">
        <div class="left">
          <div class="t1">
            <span class="jname">{{ j.岗位名称 }}</span>
            <span class="jsalary">{{ j.薪资 || '薪资面议' }}</span>
          </div>
          <div class="t2">
            <span>{{ j.区县 || j.城市 }}</span><i>·</i>
            <span>{{ j.经验要求 || '经验不限' }}</span><i>·</i>
            <span>{{ j.学历要求 || '学历不限' }}</span>
            <el-tag v-if="j.是否在线" size="small" type="success" effect="light" class="ml">在线</el-tag>
          </div>
          <div class="t3">
            <el-tag v-for="s in j.技能标签.slice(0, 5)" :key="s" size="small" effect="plain"
                    class="ml0">{{ s }}</el-tag>
          </div>
        </div>
        <div class="right">
          <div class="comrow">
            <span class="comname">{{ j.公司 }}</span>
            <span v-if="j.同公司岗位数 > 1" class="muted">在招 {{ j.同公司岗位数 }} 个职位</span>
          </div>
          <div class="hrrow">
            <div class="avatar">{{ j.招聘者.slice(0, 1) }}</div>
            <div class="hrinfo">
              <div><b>{{ j.招聘者 }}</b> <span class="muted">{{ j.招聘者职位 }}</span></div>
              <div class="muted">{{ j.回复文案 || '暂无回复数据' }}</div>
            </div>
          </div>
        </div>
      </div>
      <el-empty v-if="!list.岗位.length" description="没有符合条件的职位，试试放宽筛选" />
    </div>

    <el-pagination v-if="list.总页数 > 1" background layout="prev, pager, next, jumper"
                   :total="list.总数" :page-size="size" :current-page="page"
                   class="pager" @current-change="turn" />

    <!-- ⑤ 职位详情抽屉 -->
    <el-drawer v-model="drawer" size="46%" :title="cur?.岗位名称 || ''">
      <template v-if="cur">
        <div class="dt1">
          <div>
            <div class="jname" style="font-size:19px">{{ cur.岗位名称 }}</div>
            <div class="muted" style="margin-top:6px">
              {{ cur.地区 }} ｜ {{ cur.经验要求 || '经验不限' }} ｜ {{ cur.学历要求 || '学历不限' }}
            </div>
          </div>
          <div class="jsalary" style="font-size:20px">{{ cur.薪资 }}</div>
        </div>
        <div class="t3" style="margin-top:10px">
          <el-tag size="small" effect="dark" type="primary">{{ cur.岗位大类 }}</el-tag>
          <el-tag v-if="cur.一级簇名" size="small" type="success" effect="light" class="ml">{{ cur.一级簇名 }}</el-tag>
          <el-tag v-if="cur.二级簇名" size="small" type="warning" effect="light" class="ml">{{ cur.二级簇名 }}</el-tag>
        </div>

        <el-divider />
        <div class="hrbox">
          <div class="avatar big">{{ cur.招聘者.slice(0, 1) }}</div>
          <div>
            <div><b>{{ cur.招聘者 }}</b> ｜ {{ cur.招聘者职位 }}</div>
            <div class="muted">
              {{ cur.在线状态 || '离线' }} ｜ {{ cur.回复文案 || '暂无回复数据' }}
              ｜ 同公司 {{ cur.同公司岗位数 }} 个在招职位
            </div>
          </div>
        </div>

        <div class="zq-section">技能标签</div>
        <el-tag v-for="s in cur.技能标签" :key="s" effect="light" class="ml0">{{ s }}</el-tag>
        <div class="zq-section">职位描述</div>
        <div class="desc">{{ cur.职位描述 }}</div>

        <el-divider />
        <div class="acts">
          <el-button type="primary" :disabled="!auth.isLogged()" @click="fav">
            ⭐ 收藏这个职位</el-button>
          <el-button :disabled="!resume.canMatch()" :loading="scoring" @click="doScore">
            用我的简历算匹配分</el-button>
        </div>
        <div v-if="score" style="margin-top:10px">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="规则总分">{{ score.规则口径.总分 }}</el-descriptions-item>
            <el-descriptions-item label="模型预测分">
              {{ score.模型口径.可用 ? score.模型口径.T1回归_预测总分 : '—' }}</el-descriptions-item>
          </el-descriptions>
        </div>
        <div v-else-if="!resume.canMatch()" class="muted" style="margin-top:8px">
          先在「📄 简历」解析一份简历，才能算匹配分
        </div>
        <div v-if="!auth.isLogged()" class="muted" style="margin-top:8px">登录后可收藏</div>
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
import { useAuthStore } from '../stores/auth'
import { useResumeStore } from '../stores/resume'

const auth = useAuthStore()
const resume = useResumeStore()

const loading = ref(false)
const kw = ref('')
const city = ref('')
const district = ref('')
const edu = ref('')
const salaryMin = ref(0)
const category = ref('')
const sort = ref('default')
const page = ref(1)
const size = ref(20)

const salaryOpts = [
  { v: 5000, t: '5千以上' }, { v: 8000, t: '8千以上' }, { v: 10000, t: '1万以上' },
  { v: 15000, t: '1.5万以上' }, { v: 20000, t: '2万以上' }, { v: 30000, t: '3万以上' },
]

const empty: JobStatsResp = {
  ok: true,
  总体: { 岗位总数: 0, 公司数: 0, 城市数: 0, 省份数: 0, 平均薪资上限: 0,
         薪资下限中位数: 0, 薪资上限中位数: 0, 在线岗位数: 0, 区县数: 0,
         有招聘者职位数: 0, 有回复数据岗位数: 0 },
  按城市: [], 按大类: [], 按学历: [], 按经验: [], 按簇: [], 热门技能: [],
  热门搜索: [], 按城市区县: {}, 分类导航: [],
  筛选项: { 城市: [], 大类: [], 学历: [], 省份: [], 排序: [] }, 来源: [],
}
const st = ref<JobStatsResp>(empty)
const list = ref<JobListResp>({ ok: true, 总数: 0, 页码: 1, 每页: 20, 总页数: 1, 岗位: [], 来源: [] })

const drawer = ref(false)
const cur = ref<JobItem | null>(null)
const score = ref<ScoreResp | null>(null)
const scoring = ref(false)

const fmt = (n: number) => (n || 0).toLocaleString('en-US')
const districts = computed(() => (city.value ? st.value.按城市区县[city.value] || [] : [])
  .filter((d) => d.数量 >= 3))

function load(pageNo = 1) {
  loading.value = true
  return api.listJobs({
    page: pageNo, size: size.value, city: city.value, district: district.value,
    category: category.value, keyword: kw.value, salary_min: salaryMin.value || 0,
    edu: edu.value, sort: sort.value,
  }).then((r) => { list.value = r; page.value = r.页码 })
    .catch(() => { /* 拦截器已提示 */ })
    .finally(() => { loading.value = false })
}
const search = () => load(1)
const turn = (p: number) => load(p)

function pickCity(c: string) {
  city.value = c
  district.value = ''
  search()
}
function setDistrict(d: string) { district.value = d; search() }
function setSalary(v: number) { salaryMin.value = salaryMin.value === v ? 0 : v; search() }
function setEdu(e: string) { edu.value = edu.value === e ? '' : e; search() }

async function open(j: JobItem) {
  cur.value = j
  score.value = null
  drawer.value = true
  try { cur.value = await api.jobDetail(j.岗位ID) as JobItem }
  catch { /* 保留列表字段 */ }
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
.home { max-width: 1180px; margin: 0 auto; }
.ml { margin-left: 6px; }
.ml0 { margin: 0 6px 6px 0; }
.num { color: #ff6a00; font-size: 17px; }
.muted { color: #8896ab; font-size: 12.5px; }

/* ---------- 顶部 ---------- */
.topbar { background: #fff; border: 1px solid var(--zq-border); border-radius: 12px;
  padding: 14px 18px; }
.cityline { display: flex; align-items: center; gap: 10px; padding-bottom: 10px;
  border-bottom: 1px dashed #eef3f9; }
.cityline .cur { font-weight: 700; color: var(--el-color-primary); white-space: nowrap; }
.cities { display: flex; flex-wrap: wrap; gap: 4px 12px; }
.cities a { color: #41506b; cursor: pointer; font-size: 13.5px; }
.cities a:hover { color: var(--el-color-primary); }
.cities a.on { color: var(--el-color-primary); font-weight: 700; }
.searchline { padding-top: 12px; }
.sinput { max-width: 760px; }
.hot { margin-top: 10px; font-size: 13px; color: #8896ab; }
.hot .lb { margin-right: 4px; }
.hot a { color: #41506b; margin-right: 14px; cursor: pointer; }
.hot a:hover { color: var(--el-color-primary); }

/* ---------- 筛选栏 ---------- */
.filters em { font-style: normal; color: #b3bfd0; font-size: 11.5px; margin-left: 3px; }

/* ---------- 筛选栏 ---------- */
.filters { background: #fff; border: 1px solid var(--zq-border); border-radius: 12px;
  padding: 10px 18px; margin-top: 12px; }
.frow { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; padding: 5px 0; }
.flb { color: #8896ab; font-size: 13px; flex: none; }
.frow a { color: #41506b; font-size: 13.5px; cursor: pointer; }
.frow a:hover { color: var(--el-color-primary); }
.frow a.on { color: var(--el-color-primary); font-weight: 700; }
.frow .tip { color: #c0c9d6; font-size: 12px; }

/* ---------- 结果统计 ---------- */
.resultbar { display: flex; align-items: center; gap: 12px; margin: 14px 2px 10px; }
.resultbar .right { margin-left: auto; }

/* ---------- 职位卡 ---------- */
.joblist { display: flex; flex-direction: column; gap: 10px; }
.jcard { display: flex; gap: 20px; background: #fff; border: 1px solid var(--zq-border);
  border-radius: 12px; padding: 16px 18px; cursor: pointer; transition: .16s;
  box-shadow: var(--zq-card-shadow); }
.jcard:hover { box-shadow: 0 8px 22px rgba(0,166,167,.14); transform: translateY(-2px);
  border-color: var(--el-color-primary-light-5); }
.jcard .left { flex: 1; min-width: 0; }
.jcard .right { width: 270px; flex: none; border-left: 1px dashed #eef3f9; padding-left: 18px; }
.t1 { display: flex; justify-content: space-between; align-items: baseline; gap: 14px; }
.jname { font-size: 17px; font-weight: 700; color: #16233a; }
.jsalary { font-size: 18px; font-weight: 800; color: #ff6a00; white-space: nowrap; }
.t2 { margin-top: 8px; color: #5b6b7f; font-size: 13px; display: flex; align-items: center; gap: 6px;
  flex-wrap: wrap; }
.t2 i { color: #c9d3e0; font-style: normal; }
.t3 { margin-top: 10px; }
.comrow { display: flex; flex-direction: column; gap: 2px; }
.comname { font-weight: 600; color: #41506b; font-size: 14px; }
.hrrow { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.avatar { width: 34px; height: 34px; border-radius: 50%; flex: none; color: #fff; font-size: 15px;
  display: flex; align-items: center; justify-content: center; font-weight: 700;
  background: linear-gradient(135deg, #00a6a7, #12c2b4); }
.avatar.big { width: 44px; height: 44px; font-size: 19px; }
.hrinfo { font-size: 13px; line-height: 1.5; }
.dt1 { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.hrbox { display: flex; align-items: center; gap: 12px; background: #f7fbfb;
  border: 1px solid #e6f4f4; border-radius: 10px; padding: 12px 14px; font-size: 13.5px; }
.desc { background: #fbfcfe; border: 1px solid var(--zq-border); border-radius: 10px;
  padding: 14px 16px; white-space: pre-wrap; line-height: 1.8; font-size: 14px;
  max-height: 320px; overflow: auto; }
.acts { display: flex; gap: 10px; }
.pager { margin-top: 18px; justify-content: center; }

@media (max-width: 900px) {
  .jcard { flex-direction: column; }
  .jcard .right { width: auto; border-left: none; border-top: 1px dashed #eef3f9;
    padding-left: 0; padding-top: 12px; }
}
</style>
