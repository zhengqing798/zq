<template>
  <el-drawer v-model="visible" size="46%" :title="job?.岗位名称 || '职位详情'">
    <template v-if="job">
      <div class="dt1">
        <div>
          <div class="jname">{{ job.岗位名称 }}</div>
          <div class="muted" style="margin-top:6px">
            <span class="colink" :title="job.公司ID ? '查看该公司全部在招职位' : ''" @click="goCompany">
              {{ job.公司 }}</span>
            ｜ {{ job.地区 }} ｜ {{ job.经验要求 || '经验不限' }}
            ｜ {{ job.学历要求 || '学历不限' }}
          </div>
        </div>
        <div class="jsalary">{{ job.薪资 || '薪资面议' }}</div>
      </div>
      <div class="t3">
        <el-tag size="small" effect="dark" type="primary">{{ job.岗位大类 }}</el-tag>
        <el-tag v-if="job.一级簇名" size="small" type="success" effect="light" class="ml">
          {{ job.一级簇名 }}</el-tag>
        <el-tag v-if="job.二级簇名" size="small" type="warning" effect="light" class="ml">
          {{ job.二级簇名 }}</el-tag>
      </div>

      <el-divider />
      <div class="hrbox">
        <div class="avatar big">{{ job.招聘者.slice(0, 1) }}</div>
        <div>
          <div><b>{{ job.招聘者 }}</b> ｜ {{ job.招聘者职位 }}</div>
          <div class="muted">
            {{ job.在线状态 || '离线' }} ｜ {{ job.回复文案 || '暂无回复数据' }}
            ｜ 同公司 {{ job.同公司岗位数 }} 个在招职位
          </div>
        </div>
      </div>

      <div class="zq-section">技能标签</div>
      <el-tag v-for="s in job.技能标签" :key="s" effect="light" class="ml0">{{ s }}</el-tag>
      <div class="zq-section">职位描述</div>
      <div class="desc">{{ job.职位描述 }}</div>

      <el-divider />
      <div class="acts">
        <el-button type="primary" :disabled="!auth.isLogged()" @click="fav">⭐ 收藏这个职位</el-button>
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
        还没有简历 → 去
        <el-button link type="primary" @click="goResume">个人中心</el-button>
        粘贴或上传 PDF 简历后即可算匹配分
      </div>
      <div v-if="!auth.isLogged()" class="muted" style="margin-top:8px">登录后可收藏</div>
    </template>
    <el-skeleton v-else :rows="6" animated />
  </el-drawer>
</template>

<script setup lang="ts">
/**
 * 职位详情抽屉（首页 / 公司页 / 公司详情页共用）
 *
 * 传 `jobId` 与 `v-model` 即可：组件自己拉 `/api/jobs/{id}` 详情、
 * 自己处理「收藏」「用我的简历算匹配分」，避免每个页面各写一套。
 */
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as api from '../api'
import type { JobItem } from '../api/jobs'
import type { ScoreResp } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { useResumeStore } from '../stores/resume'

const props = defineProps<{ modelValue: boolean; jobId: string }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const auth = useAuthStore()
const resume = useResumeStore()
const router = useRouter()

/** 抽屉里的公司名 → 该公司详情页（先关抽屉，避免跳页后抽屉还挂着） */
function goCompany() {
  if (!job.value?.公司ID) return
  visible.value = false
  router.push('/company/' + job.value.公司ID)
}

/** 没有简历时引导去个人中心（简历已并入个人中心，不再有独立「简历」页） */
function goResume() {
  visible.value = false
  router.push('/profile')
}

const job = ref<JobItem | null>(null)
const score = ref<ScoreResp | null>(null)
const scoring = ref(false)

const visible = ref(props.modelValue)
watch(() => props.modelValue, (v) => { visible.value = v })
watch(visible, (v) => {
  emit('update:modelValue', v)
  if (v) load()
})

async function load() {
  if (!props.jobId) return
  score.value = null
  job.value = null
  try {
    job.value = (await api.jobDetail(props.jobId)) as JobItem
  } catch { /* 拦截器已提示 */ }
}

async function doScore() {
  if (!job.value) return
  scoring.value = true
  try {
    score.value = await api.runScore(job.value.岗位ID, resume.resumeId || null, resume.text || null)
  } catch { /* 拦截器已提示 */ }
  finally { scoring.value = false }
}

async function fav() {
  if (!job.value) return
  try {
    const r = await api.addFavorite(job.value.岗位ID)
    ElMessage.success(r.message || '已收藏')
  } catch { /* 拦截器已提示 */ }
}
</script>

<style scoped>
.ml { margin-left: 6px; }
.ml0 { margin: 0 6px 6px 0; }
.muted { color: #8896ab; font-size: 12.5px; }
.colink { color: #41506b; cursor: pointer; }
.colink:hover { color: var(--el-color-primary); }
.jname { font-size: 19px; font-weight: 700; color: #16233a; }
.jsalary { font-size: 20px; font-weight: 800; color: #ff6a00; white-space: nowrap; }
.dt1 { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.t3 { margin-top: 10px; }
.avatar { width: 34px; height: 34px; border-radius: 50%; flex: none; color: #fff; font-size: 15px;
  display: flex; align-items: center; justify-content: center; font-weight: 700;
  background: linear-gradient(135deg, #00a6a7, #12c2b4); }
.avatar.big { width: 44px; height: 44px; font-size: 19px; }
.hrbox { display: flex; align-items: center; gap: 12px; background: #f7fbfb;
  border: 1px solid #e6f4f4; border-radius: 10px; padding: 12px 14px; font-size: 13.5px; }
.desc { background: #fbfcfe; border: 1px solid var(--zq-border); border-radius: 10px;
  padding: 14px 16px; white-space: pre-wrap; line-height: 1.8; font-size: 14px;
  max-height: 320px; overflow: auto; }
.acts { display: flex; gap: 10px; }
</style>
