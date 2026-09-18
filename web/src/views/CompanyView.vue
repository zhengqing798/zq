<template>
  <div v-loading="loading" class="company">
    <div class="back">
      <el-button link @click="router.push('/companies')">← 返回公司列表</el-button>
    </div>

    <template v-if="c">
      <!-- ① 公司头部 -->
      <div class="zq-card pad head">
        <div class="row1">
          <div class="logo" :style="{ background: logoBg(c.公司ID) }">{{ logoChar(c.公司名称) }}</div>
          <div class="hmain">
            <div class="cname">{{ c.公司名称 }}</div>
            <div class="htags">
              <el-tag size="small" type="primary" effect="dark" :title="sizeTip">
                在招职位数 {{ c.规模分档 }}</el-tag>
              <el-tag size="small" effect="light">{{ c.主要城市 }}</el-tag>
              <el-tag size="small" effect="light" type="success">{{ c.主要大类 }}类</el-tag>
              <el-tag v-if="c.城市数 > 1" size="small" effect="light" type="info">
                覆盖 {{ c.城市数 }} 个城市</el-tag>
              <el-tag v-if="c.区县数" size="small" effect="light" type="info">
                覆盖 {{ c.区县数 }} 个区县</el-tag>
            </div>
            <div class="muted" style="margin-top:8px">
              该公司今日回复 {{ c.今日回复总数 }} 次 ｜ {{ c.在线岗位数 }} 个岗位招聘者在线
              ｜ 薪资中位数 {{ fmtSalaryK(c.薪资下限中位数, c.薪资上限中位数) }}/月
              ｜ 最高 {{ fmtSalaryK(0, c.最高薪资上限) }}
            </div>
          </div>
          <div class="hright">
            <div class="big">{{ c.在招岗位数 }}</div>
            <div class="muted">在招职位</div>
          </div>
        </div>
      </div>

      <div class="layout">
        <!-- ② 左：全部在招职位（点开抽屉看详情） -->
        <main class="main">
          <div class="zq-section">在招职位（{{ c.在招岗位数 }}）</div>
          <div class="joblist">
            <div v-for="j in shown" :key="j.岗位ID" class="jrow" @click="openJob(j.岗位ID)">
              <div class="jrow-main">
                <div class="jt1">
                  <span class="jname">{{ j.岗位名称 }}</span>
                  <span class="jsalary">{{ j.薪资 || '薪资面议' }}</span>
                </div>
                <div class="jt2">
                  <span>{{ j.区县 || j.城市 }}</span><i>·</i>
                  <span>{{ j.经验要求 || '经验不限' }}</span><i>·</i>
                  <span>{{ j.学历要求 || '学历不限' }}</span>
                  <el-tag v-if="j.是否在线" size="small" type="success" effect="light" class="ml">
                    在线</el-tag>
                  <span class="muted ml">{{ j.回复文案 || '暂无回复数据' }}</span>
                </div>
                <div class="jt3">
                  <el-tag v-for="s in j.技能标签.slice(0, 6)" :key="s" size="small" effect="plain"
                          class="tg">{{ s }}</el-tag>
                  <span v-if="!j.技能标签.length" class="muted">未标注技能标签</span>
                </div>
              </div>
              <div class="jrow-side">
                <div>{{ j.招聘者 }}</div>
                <div class="muted">{{ j.招聘者职位 }}</div>
              </div>
            </div>
          </div>
          <div v-if="shown.length < c.在招岗位.length" class="more">
            <el-button @click="limit += 20">
              显示更多（还有 {{ c.在招岗位.length - shown.length }} 个）</el-button>
          </div>
        </main>

        <!-- ③ 右：公司画像 -->
        <aside class="side">
          <div class="zq-card pad panel">
            <div class="zq-section" style="margin-top:0">岗位大类分布</div>
            <div v-for="x in c.岗位大类" :key="x.名称" class="dist">
              <span class="dn">{{ x.名称 }}</span>
              <el-progress :percentage="pct(x.数量, c.在招岗位数)" :show-text="false"
                           :stroke-width="8" />
              <em>{{ x.数量 }}</em>
            </div>
          </div>

          <div class="zq-card pad panel">
            <div class="zq-section">技能需求 Top{{ c.技能需求.length }}</div>
            <el-tag v-for="s in c.技能需求" :key="s.名称" size="small" effect="plain" class="tg2">
              {{ s.名称 }}<em>{{ s.数量 }}</em></el-tag>
            <div v-if="!c.技能需求.length" class="muted">该公司的岗位未标注技能标签</div>
          </div>

          <div class="zq-card pad panel">
            <div class="zq-section">学历 / 经验要求</div>
            <div v-for="x in c.学历要求" :key="'e' + x.名称" class="kv">
              <span>{{ x.名称 }}</span><b>{{ x.数量 }}</b></div>
            <el-divider style="margin:10px 0" />
            <div v-for="x in c.经验要求" :key="'x' + x.名称" class="kv">
              <span>{{ x.名称 }}</span><b>{{ x.数量 }}</b></div>
          </div>

          <div class="zq-card pad panel">
            <div class="zq-section">招聘者（{{ c.招聘者数 }} 人）</div>
            <div v-for="h in c.招聘者.slice(0, 12)" :key="h.姓名 + h.职位" class="hrrow">
              <div class="avatar">{{ h.姓名.slice(0, 1) }}</div>
              <div>
                <div><b>{{ h.姓名 }}</b> <span class="muted">{{ h.职位 }}</span></div>
                <div class="muted">{{ h.回复文案 }}</div>
              </div>
            </div>
          </div>

          <div class="zq-card pad panel">
            <div class="zq-section">相似公司（同城·同类）</div>
            <CompanyCard v-for="x in c.相似公司" :key="x.公司ID" :c="x" compact
                         @open="go" @job="openJob" />
            <div v-if="!c.相似公司.length" class="muted">没有同为「{{ c.主要城市 }} · {{ c.主要大类 }}」的其他公司</div>
          </div>
        </aside>
      </div>
    </template>

    <el-empty v-else-if="!loading" description="公司不存在（ID 可能有误）" />

    <JobDetailDrawer v-model="drawer" :job-id="curJob" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as api from '../api'
import type { CompanyDetail, CompanyItem } from '../api/companies'
import CompanyCard from '../components/CompanyCard.vue'
import JobDetailDrawer from '../components/JobDetailDrawer.vue'
import { fmtSalaryK, logoBg, logoChar } from '../utils/format'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const c = ref<CompanyDetail | null>(null)
const limit = ref(20)
const drawer = ref(false)
const curJob = ref('')

const sizeTip = '数据里没有「公司规模」列，这里用该公司的在招职位数分档代理'
const shown = computed(() => (c.value?.在招岗位 || []).slice(0, limit.value))
const pct = (n: number, total: number) => Math.round((n / (total || 1)) * 100)

async function load() {
  loading.value = true
  limit.value = 20
  try {
    c.value = await api.companyDetail(String(route.params.id))
  } catch { c.value = null }
  finally { loading.value = false }
}

function openJob(jobId: string) { curJob.value = jobId; drawer.value = true }
const go = (x: CompanyItem) => router.push('/company/' + x.公司ID)

watch(() => route.params.id, load)
onMounted(load)
</script>

<style scoped>
.company { max-width: 1280px; margin: 0 auto; }
.back { margin-bottom: 8px; }
.muted { color: #8896ab; font-size: 12.5px; }
.ml { margin-left: 8px; }

/* ---------- 头部 ---------- */
.head { padding: 18px 20px; }
.row1 { display: flex; gap: 16px; align-items: flex-start; }
.logo { width: 64px; height: 64px; border-radius: 14px; flex: none; color: #fff; font-size: 30px;
  font-weight: 700; display: flex; align-items: center; justify-content: center; }
.hmain { flex: 1; min-width: 0; }
.cname { font-size: 22px; font-weight: 800; color: #16233a; line-height: 1.3; }
.htags { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
.hright { flex: none; text-align: right; }
.hright .big { font-size: 32px; font-weight: 800; color: #ff6a00; line-height: 1.1; }

/* ---------- 两栏 ---------- */
.layout { display: flex; gap: 16px; align-items: flex-start; margin-top: 4px; }
.main { flex: 1; min-width: 0; }
.side { width: 330px; flex: none; display: flex; flex-direction: column; gap: 12px; }
.panel { border-radius: 12px; }

/* ---------- 职位行 ---------- */
.joblist { display: flex; flex-direction: column; gap: 8px; }
.jrow { display: flex; gap: 14px; background: #fff; border: 1px solid var(--zq-border);
  border-radius: 10px; padding: 12px 14px; cursor: pointer; transition: .16s;
  box-shadow: var(--zq-card-shadow); }
.jrow:hover { border-color: var(--el-color-primary-light-5);
  box-shadow: 0 6px 18px rgba(0, 166, 167, .12); }
.jrow-main { flex: 1; min-width: 0; }
.jrow-side { width: 110px; flex: none; border-left: 1px dashed #eef3f9; padding-left: 12px;
  font-size: 13px; color: #41506b; }
.jt1 { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
.jname { font-size: 15.5px; font-weight: 700; color: #16233a; }
.jsalary { font-size: 16px; font-weight: 800; color: #ff6a00; white-space: nowrap; }
.jt2 { margin-top: 6px; color: #5b6b7f; font-size: 12.5px; display: flex; align-items: center;
  flex-wrap: wrap; gap: 6px; }
.jt2 i { color: #c9d3e0; font-style: normal; }
.jt3 { margin-top: 8px; }
.tg { margin: 0 6px 4px 0; }
.tg em { font-style: normal; color: #b3bfd0; font-size: 11px; margin-left: 3px; }
.tg2 { margin: 0 6px 6px 0; }
.more { margin-top: 12px; text-align: center; }

/* ---------- 侧栏小件 ---------- */
.dist { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 3px 0; }
.dist .dn { width: 62px; flex: none; color: #41506b; }
.dist :deep(.el-progress) { flex: 1; min-width: 0; }
.dist em { font-style: normal; color: #8896ab; font-size: 12px; width: 30px; text-align: right; }
.kv { display: flex; justify-content: space-between; font-size: 13px; color: #41506b; padding: 2px 0; }
.kv b { color: #16233a; }
.hrrow { display: flex; align-items: center; gap: 10px; padding: 5px 0; font-size: 13px; }
.avatar { width: 32px; height: 32px; border-radius: 50%; flex: none; color: #fff; font-size: 14px;
  display: flex; align-items: center; justify-content: center; font-weight: 700;
  background: linear-gradient(135deg, #00a6a7, #12c2b4); }
.notes { margin: 0; padding-left: 16px; color: #6b7a90; font-size: 12px; line-height: 1.7; }

@media (max-width: 980px) {
  .layout { flex-direction: column; }
  .side { width: 100%; }
  .row1 { flex-wrap: wrap; }
}
</style>
