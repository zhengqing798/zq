<template>
  <div class="companies">
    <!-- ① 顶部：标题 + 公司名搜索 + 城市快捷 -->
    <div class="topbar">
      <div class="trow">
        <div>
          <div class="h1">公司广场</div>
          <div class="sub">
            数据来源：{{ st.来源[0] || '真实抓取岗位表' }} ｜ 点公司卡片查看该公司的<b>全部在招职位</b>
          </div>
        </div>
        <el-input v-model="kw" size="large" class="sinput" placeholder="搜索公司名称，如 软通动力"
                  clearable @keyup.enter="search">
          <template #append>
            <el-button type="primary" :icon="Search" @click="search">搜索</el-button>
          </template>
        </el-input>
      </div>
      <div class="cityline">
        <span class="cur">📍 {{ city || '全部城市' }}</span>
        <div class="cities">
          <a :class="{ on: !city }" @click="pickCity('')">全部</a>
          <a v-for="c in st.按城市" :key="c.名称" :class="{ on: city === c.名称 }"
             @click="pickCity(c.名称)">{{ c.名称 }}<em>{{ c.数量 }}</em></a>
        </div>
      </div>
    </div>

    <div class="layout">
      <!-- ② 左栏：榜单 + 口径 -->
      <aside class="side">
        <div class="zq-card pad panel">
          <div class="zq-section" style="margin-top:0">热门企业 · 在招职位最多</div>
          <a v-for="(c, i) in st.热门企业.slice(0, 10)" :key="c.公司ID" class="rank"
             @click="go(c)">
            <b :class="{ top3: i < 3 }">{{ i + 1 }}</b>
            <span class="rn">{{ c.公司名称 }}</span>
            <em>{{ c.在招岗位数 }} 个</em>
          </a>
        </div>

        <div class="zq-card pad panel">
          <div class="zq-section">最活跃企业 · 今日回复最多</div>
          <a v-for="(c, i) in st.最活跃企业.slice(0, 6)" :key="c.公司ID" class="rank"
             @click="go(c)">
            <b :class="{ top3: i < 3 }">{{ i + 1 }}</b>
            <span class="rn">{{ c.公司名称 }}</span>
            <em>回复 {{ c.今日回复总数 }}</em>
          </a>
        </div>

        <div class="zq-card pad panel">
          <div class="zq-section">口径说明</div>
          <ul class="notes">
            <li v-for="s in st.口径说明" :key="s">{{ s }}</li>
          </ul>
        </div>
      </aside>

      <!-- ③ 右栏：筛选 + 公司卡列表 -->
      <main class="main">
        <div class="filters">
          <div class="frow">
            <span class="flb">岗位大类：</span>
            <a :class="{ on: !category }" @click="pickCategory('')">不限</a>
            <a v-for="c in st.按大类" :key="c.名称" :class="{ on: category === c.名称 }"
               @click="pickCategory(c.名称)">{{ c.名称 }}<em>{{ c.数量 }}</em></a>
          </div>
          <div class="frow">
            <span class="flb" title="口径：该公司的在招职位数">在招职位数：</span>
            <a :class="{ on: !bucket }" @click="pickBucket('')">不限</a>
            <a v-for="b in st.规模分档" :key="b.名称" :class="{ on: bucket === b.名称 }"
               :title="b.说明" @click="pickBucket(b.名称)">{{ b.名称 }}<em>{{ b.数量 }}</em></a>
          </div>
          <div class="frow">
            <span class="flb">排序：</span>
            <a v-for="s in st.筛选项.排序" :key="s.value" :class="{ on: sort === s.value }"
               @click="sort = s.value; search()">{{ s.label }}</a>
          </div>
        </div>

        <div class="resultbar">
          <span>共 <b class="num">{{ fmtNum(list.总数) }}</b> 家公司</span>
          <span class="muted">
            {{ city || '全部城市' }}{{ category ? ' · ' + category + '类' : ''
            }}{{ bucket ? ' · 在招 ' + bucket : '' }}{{ kw ? ' · ' + kw : '' }}
          </span>
          <span class="right">
            <el-radio-group v-model="size" size="small" @change="search">
              <el-radio-button :value="12">12/页</el-radio-button>
              <el-radio-button :value="24">24/页</el-radio-button>
            </el-radio-group>
          </span>
        </div>

        <div v-loading="loading" class="grid">
          <CompanyCard v-for="c in list.公司" :key="c.公司ID" :c="c"
                       @open="go" @job="openJob" />
        </div>
        <el-empty v-if="!loading && !list.公司.length" description="没有符合条件的公司，试试放宽筛选" />

        <el-pagination v-if="list.总页数 > 1" background layout="prev, pager, next, jumper"
                       :total="list.总数" :page-size="size" :current-page="page"
                       class="pager" @current-change="turn" />
      </main>
    </div>

    <!-- ④ 职位详情抽屉（点「热招职位」直接看岗位，不用先跳公司页） -->
    <JobDetailDrawer v-model="drawer" :job-id="curJob" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import * as api from '../api'
import type { CompanyItem, CompanyListResp, CompanyStatsResp } from '../api/companies'
import CompanyCard from '../components/CompanyCard.vue'
import JobDetailDrawer from '../components/JobDetailDrawer.vue'
import { fmtNum } from '../utils/format'

const router = useRouter()

const loading = ref(false)
const kw = ref('')
const city = ref('')
const category = ref('')
const bucket = ref('')
const sort = ref('jobs_desc')
const page = ref(1)
const size = ref(12)

const emptySt: CompanyStatsResp = {
  ok: true,
  总体: { 公司总数: 0, 在招岗位总数: 0, 平均每司岗位数: 0, 只招1个岗位的公司数: 0,
         在招10个以上的公司数: 0, 城市数: 0, 岗位数最多公司: '', 岗位数最多公司岗位数: 0,
         有回复活跃的公司数: 0 },
  规模分档: [], 按城市: [], 按大类: [], 热门企业: [], 最活跃企业: [],
  筛选项: { 城市: [], 大类: [], 规模分档: [], 排序: [] }, 口径说明: [], 来源: [],
}
const st = ref<CompanyStatsResp>(emptySt)
const list = ref<CompanyListResp>({ ok: true, 总数: 0, 页码: 1, 每页: 12, 总页数: 1,
                                   公司: [], 来源: [] })

const drawer = ref(false)
const curJob = ref('')

function load(pageNo = 1) {
  loading.value = true
  return api.listCompanies({
    page: pageNo, size: size.value, city: city.value, category: category.value,
    keyword: kw.value, bucket: bucket.value, sort: sort.value,
  }).then((r) => { list.value = r; page.value = r.页码 })
    .catch(() => { /* 拦截器已提示 */ })
    .finally(() => { loading.value = false })
}
const search = () => load(1)
const turn = (p: number) => load(p)

function pickCity(c: string) { city.value = c; search() }
function pickCategory(c: string) { category.value = category.value === c ? '' : c; search() }
function pickBucket(b: string) { bucket.value = bucket.value === b ? '' : b; search() }

const go = (c: CompanyItem) => router.push('/company/' + c.公司ID)
function openJob(jobId: string) { curJob.value = jobId; drawer.value = true }

onMounted(async () => {
  try { st.value = await api.companyStats() } catch { /* 拦截器已提示 */ }
  await load(1)
})
</script>

<style scoped>
.companies { max-width: 1280px; margin: 0 auto; }
.num { color: #ff6a00; font-size: 17px; }
.muted { color: #8896ab; font-size: 12.5px; }

/* ---------- 顶部 ---------- */
.topbar { background: #fff; border: 1px solid var(--zq-border); border-radius: 12px;
  padding: 14px 18px; }
.trow { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.h1 { font-size: 20px; font-weight: 800; color: #16233a; }
.sub { color: #8896ab; font-size: 12.5px; margin-top: 4px; }
.sinput { max-width: 420px; flex: none; }
.cityline { display: flex; align-items: center; gap: 10px; padding-top: 12px; margin-top: 12px;
  border-top: 1px dashed #eef3f9; }
.cityline .cur { font-weight: 700; color: var(--el-color-primary); white-space: nowrap; }
.cities { display: flex; flex-wrap: wrap; gap: 4px 12px; }
.cities a { color: #41506b; cursor: pointer; font-size: 13.5px; }
.cities a:hover { color: var(--el-color-primary); }
.cities a.on { color: var(--el-color-primary); font-weight: 700; }
.cities em { font-style: normal; color: #b3bfd0; font-size: 11.5px; margin-left: 3px; }

/* ---------- 两栏 ---------- */
.layout { display: flex; gap: 16px; align-items: flex-start; margin-top: 14px; }
.side { width: 288px; flex: none; display: flex; flex-direction: column; gap: 12px; }
.main { flex: 1; min-width: 0; }
.panel { border-radius: 12px; }
.rank { display: flex; align-items: center; gap: 8px; padding: 5px 0; cursor: pointer;
  color: #41506b; font-size: 13.5px; }
.rank:hover { color: var(--el-color-primary); }
.rank b { width: 18px; height: 18px; border-radius: 5px; flex: none; font-size: 11.5px;
  display: flex; align-items: center; justify-content: center; color: #fff;
  background: #c3ccda; font-weight: 700; }
.rank b.top3 { background: linear-gradient(135deg, #00a6a7, #12c2b4); }
.rank .rn { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank em { font-style: normal; color: #ff6a00; font-size: 12.5px; white-space: nowrap; }
.notes { margin: 0; padding-left: 16px; color: #6b7a90; font-size: 12px; line-height: 1.7; }

/* ---------- 筛选 ---------- */
.filters { background: #fff; border: 1px solid var(--zq-border); border-radius: 12px;
  padding: 10px 18px; }
.frow { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; padding: 5px 0; }
.flb { color: #8896ab; font-size: 13px; flex: none; }
.frow a { color: #41506b; font-size: 13.5px; cursor: pointer; }
.frow a:hover { color: var(--el-color-primary); }
.frow a.on { color: var(--el-color-primary); font-weight: 700; }
.frow em { font-style: normal; color: #b3bfd0; font-size: 11.5px; margin-left: 3px; }

/* ---------- 结果与网格 ---------- */
.resultbar { display: flex; align-items: center; gap: 12px; margin: 14px 2px 10px; }
.resultbar .right { margin-left: auto; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(430px, 1fr)); gap: 12px; }
.pager { margin-top: 18px; justify-content: center; }

@media (max-width: 980px) {
  .layout { flex-direction: column; }
  .side { width: 100%; }
  .grid { grid-template-columns: 1fr; }
  .trow { flex-direction: column; }
  .sinput { max-width: 100%; }
}
</style>
