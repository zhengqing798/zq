<template>
  <div>
    <div class="zq-page-title">岗位聚类画像</div>
    <div class="zq-page-desc">
      任务7 K-Means 聚类结果：定 K=9（轮廓系数峰值 0.6735，ARI=1.0000），最大簇已做二阶细分
    </div>

    <div v-if="list" class="kpi-row">
      <div class="kpi"><div class="v">{{ list.主方案 }}</div><div class="l">主方案</div></div>
      <div class="kpi"><div class="v">{{ list.簇数 }}</div><div class="l">簇数</div></div>
      <div class="kpi"><div class="v">{{ total }}</div><div class="l">覆盖岗位</div></div>
      <div class="kpi"><div class="v">0.6735</div><div class="l">轮廓系数（峰值）</div></div>
      <div class="kpi"><div class="v">1.0000</div><div class="l">ARI（换种子一致）</div></div>
    </div>

    <div v-if="list" class="layout" style="margin-top:14px">
      <div class="zq-card pad">
        <div class="zq-section" style="margin-top:0">簇规模分布</div>
        <EChart :option="donut" height="360px" />
      </div>
      <div class="zq-card pad">
        <div class="zq-section" style="margin-top:0">簇明细（点击行查看画像）</div>
        <el-table :data="list.簇" height="360" size="small" @row-click="show" style="cursor:pointer">
          <el-table-column prop="簇名" label="簇名" min-width="180" show-overflow-tooltip />
          <el-table-column prop="岗位数" label="岗位数" width="90" sortable />
          <el-table-column prop="占比" label="占比" width="80" />
          <el-table-column prop="薪资中位数" label="薪资中位数" width="110" />
        </el-table>
        <el-select v-if="list.方案.length > 1" v-model="plan" style="margin-top:10px;width:100%">
          <el-option v-for="p in list.方案" :key="p" :label="'切换方案：' + p" :value="p" />
        </el-select>
        <el-table v-if="plan !== list.主方案" :data="list.各方案[plan] || []" height="220"
                  size="small" style="margin-top:10px">
          <el-table-column prop="簇名" label="簇名" min-width="180" show-overflow-tooltip />
          <el-table-column prop="岗位数" label="岗位数" width="90" />
          <el-table-column prop="占比" label="占比" width="80" />
        </el-table>
      </div>
    </div>

    <div class="zq-card pad" style="margin-top:14px">
      <div class="zq-section" style="margin-top:0">查某个簇的画像</div>
      <div style="display:flex;gap:10px">
        <el-input v-model="q" placeholder="簇名关键词，如：软件测试 / 算法 / 后端 / 质量检验"
                  style="max-width:420px" @keyup.enter="query" />
        <el-button type="primary" :loading="loading" @click="query">查询</el-button>
      </div>
      <div v-if="prof" style="margin-top:12px">
        <div class="muted" style="margin-bottom:8px">{{ prof.summary }}</div>
        <div v-for="d in prof.data" :key="d.簇名" class="zq-card pad" style="margin-bottom:10px">
          <b>{{ d.簇名 }}</b>
          ｜ 规模 {{ d.岗位数 }} ｜ 占比 {{ d.占比 }} ｜ 薪资中位数 {{ d.薪资中位数 }}
          <div class="muted" style="margin-top:6px">
            主导大类 {{ d.主导大类 || '—' }} ｜ 主要城市 {{ d.主要城市 || '—' }}
          </div>
        </div>
        <el-collapse>
          <el-collapse-item title="📎 来源">
            <div v-for="s in prof.来源" :key="s"><code>{{ s }}</code></div>
          </el-collapse-item>
        </el-collapse>
      </div>
      <el-alert type="warning" :closable="false" style="margin-top:12px"
                title="簇名是统计推断（主导大类 + 特征技能 lift + 关键词规则），未做人工逐簇确认；最大簇占 51.45%，已做二阶细分（K=8）" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'
import type { ClusterListResp, ClusterRow } from '../api/types'
import EChart from '../components/EChart.vue'

const list = ref<ClusterListResp | null>(null)
const plan = ref('')
const q = ref('软件测试')
const loading = ref(false)
const prof = ref<{ summary: string; data: ClusterRow[]; 来源: string[] } | null>(null)

const total = computed(() => (list.value?.簇 || []).reduce((a, b) => a + b.岗位数, 0))

const donut = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 个岗位（{d}%）' },
  legend: { type: 'scroll', bottom: 0, textStyle: { fontSize: 11 } },
  series: [{
    type: 'pie', radius: ['42%', '68%'], center: ['50%', '44%'], avoidLabelOverlap: true,
    itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
    label: { show: false }, labelLine: { show: false },
    data: (list.value?.簇 || []).map((x) => ({ name: x.簇名, value: x.岗位数 })),
  }],
}))

onMounted(async () => {
  try {
    list.value = await api.getClusterList()
    plan.value = list.value.主方案
  } catch { /* 拦截器已提示 */ }
})

async function query() {
  loading.value = true
  try { prof.value = await api.getClusterProfile(q.value) }
  catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}

function show(row: ClusterRow) {
  q.value = row.簇名.split('（')[0]
  ElMessage.info('已填入关键词：' + q.value + '，点「查询」看详细画像')
}
</script>

<style scoped>
.layout { display: grid; grid-template-columns: 1fr 1.15fr; gap: 14px; }
@media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } }
</style>
