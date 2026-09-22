<template>
  <div class="jobs">
    <div class="zq-page-title">岗位</div>

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
           @click="setSort(s.value)">{{ s.label }}</a>
      </div>
    </div>

    <!-- ③ 结果统计 -->
    <div class="resultbar">
      <span>共 <b class="num">{{ fmt(list.总数) }}</b> 个职位</span>
      <span class="muted">{{ city || '全部城市' }}{{ district ? ' · ' + district : '' }}{{ category ? ' · ' + category : '' }}{{ sourceKw ? ' · 来源关键词：' + sourceKw : '' }}{{ kw ? ' · ' + kw : '' }}</span>
      <span class="right">
        <el-radio-group v-model="size" size="small" @change="search">
          <el-radio-button :value="20">20/页</el-radio-button>
          <el-radio-button :value="50">50/页</el-radio-button>
        </el-radio-group>
      </span>
    </div>

    <!-- ④ 职位列表（左：职位 / 右：公司 + 招聘者） -->
    <div v-loading="loading" class="joblist">
      <!-- data-id：把岗位ID 暴露到 DOM 上，供渲染检查按**唯一ID**比较（而不是按岗位名称）——
           8,836 个岗位里只有 6,037 个不同名称、41% 是重名（「测试工程师」有 67 个），
           按名称比较会把"两个不同岗位恰好同名"误报成"翻页重复"。 -->
      <div v-for="j in list.岗位" :key="j.岗位ID" class="jcard"
           :data-id="j.岗位ID" @click="open(j)">
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
            <span class="comname" :title="j.公司ID ? '查看该公司全部在招职位' : ''"
                  @click.stop="goCompany(j)">{{ j.公司 }}</span>
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
  </div>
</template>

<script setup lang="ts">
/**
 * 「岗位」页：全部 8,836 个岗位的浏览与筛选（游客可用）
 *
 * 支持 URL 查询参数，便于首页/公司页跳进来时带上筛选条件：
 *   /#/jobs?keyword=Java&city=苏州&category=测试&sort=salary_desc
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import * as api from '../api'
import type { JobItem, JobListResp, JobStatsResp } from '../api/jobs'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const kw = ref('')
const city = ref('')
const district = ref('')
const edu = ref('')
const salaryMin = ref(0)
const category = ref('')
const sourceKw = ref('')
const sort = ref('default')
/** 默认排序的随机种子：进页面时随机一次，点「默认排序」再随机一次 → 每次顺序都不同 */
const newSeed = () => Math.floor(Math.random() * 1e9)
const seed = ref(newSeed())
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

const fmt = (n: number) => (n || 0).toLocaleString('en-US')
const districts = computed(() => (city.value ? st.value.按城市区县[city.value] || [] : [])
  .filter((d) => d.数量 >= 3))

function load(pageNo = 1) {
  loading.value = true
  return api.listJobs({
    page: pageNo, size: size.value, city: city.value, district: district.value,
    category: category.value, keyword: kw.value, source_kw: sourceKw.value,
    salary_min: salaryMin.value || 0, edu: edu.value, sort: sort.value,
    // 默认排序是「打乱」：带上种子，翻页顺序才稳定（否则第 1、2 页会重复/漏岗位）
    seed: seed.value,
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

/** 切换排序；切到/重新点「默认排序」时换一个随机种子（= 换一批顺序） */
function setSort(v: string) {
  sort.value = v
  if (v === 'default') seed.value = newSeed()
  search()
}

/** 从 URL 查询参数初始化筛选（首页的「看这类岗位」/ 地区卡就是这么跳过来的） */
function initFromQuery() {
  const q = route.query
  city.value = String(q.city || '')
  district.value = String(q.district || '')
  category.value = String(q.category || '')
  kw.value = String(q.keyword || '')
  sourceKw.value = String(q.source_kw || '')
  edu.value = String(q.edu || '')
  sort.value = String(q.sort || 'default')
  salaryMin.value = Number(q.salary_min || 0) || 0
  if (sort.value === 'default') seed.value = newSeed()   // 每次带新种子进页面 = 换一批顺序
}

async function open(j: JobItem) {
  // 点岗位 → 跳独立详情页（每个岗位有自己的 URL），不再弹右侧抽屉
  router.push('/job/' + j.岗位ID)
}

/** 点公司名 → 该公司详情页（全部在招职位） */
function goCompany(j: JobItem) {
  if (j.公司ID) router.push('/company/' + j.公司ID)
}

watch(() => route.query, () => { initFromQuery(); load(1) })

onMounted(async () => {
  initFromQuery()
  try { st.value = await api.jobStats() } catch { /* 拦截器已提示 */ }
  await load(1)
})
</script>

<style scoped>
.jobs { max-width: 1180px; margin: 0 auto; }
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
.filters { background: #fff; border: 1px solid var(--zq-border); border-radius: 12px;
  padding: 10px 18px; margin-top: 12px; }
.filters em { font-style: normal; color: #b3bfd0; font-size: 11.5px; margin-left: 3px; }
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
.comname { font-weight: 600; color: #41506b; font-size: 14px; cursor: pointer; }
.comname:hover { color: var(--el-color-primary); }
.hrrow { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.avatar { width: 34px; height: 34px; border-radius: 50%; flex: none; color: #fff; font-size: 15px;
  display: flex; align-items: center; justify-content: center; font-weight: 700;
  background: linear-gradient(135deg, #00a6a7, #12c2b4); }
.hrinfo { font-size: 13px; line-height: 1.5; }
.pager { margin-top: 18px; justify-content: center; }

@media (max-width: 900px) {
  .jcard { flex-direction: column; }
  .jcard .right { width: auto; border-left: none; border-top: 1px dashed #eef3f9;
    padding-left: 0; padding-top: 12px; }
}
</style>
