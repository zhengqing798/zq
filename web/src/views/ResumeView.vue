<template>
  <div>
    <div class="zq-page-title">简历输入</div>

    <div class="grid">
      <!-- 左：输入 -->
      <div class="zq-card pad">
        <div class="zq-section">粘贴简历正文</div>
        <el-input v-model="text" type="textarea" :rows="16" placeholder="把简历内容粘贴到这里…" />
        <div style="margin-top:12px;display:flex;gap:10px;flex-wrap:wrap">
          <el-button type="primary" :loading="loading" @click="doParse">解析这份文本</el-button>
          <el-button :disabled="!auth.isLogged()" @click="saveToCenter">
            💾 保存到我的简历
          </el-button>
          <el-button text @click="text = SAMPLE">填入示例</el-button>
        </div>
        <div v-if="!auth.isLogged()" class="muted" style="margin-top:8px">
          游客模式：核心功能可用；<router-link to="/login">登录</router-link>后可保存简历
        </div>
      </div>

      <!-- 右：PDF + 说明 -->
      <div>
        <div class="zq-card pad">
          <div class="zq-section">上传 PDF 简历</div>
          <el-upload drag :auto-upload="false" :show-file-list="true" accept=".pdf"
                     :on-change="onFile" :limit="1">
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">拖拽 PDF 到此处，或<em>点击选择</em></div>
            <template #tip>
              <div class="muted">一份 PDF = 一份简历（多页视为续页）</div>
            </template>
          </el-upload>
        </div>
      </div>
    </div>

    <!-- 解析结果 -->
    <div v-if="resume.parsed" style="margin-top:20px">
      <div class="zq-section">解析结果</div>
      <div class="kpi-row">
        <div class="kpi"><div class="v">{{ resume.parsed.解析字段['姓名'] || '（未识别）' }}</div>
          <div class="l">姓名</div></div>
        <div class="kpi"><div class="v">{{ resume.parsed.解析字段['期望岗位'] || '—' }}</div>
          <div class="l">期望岗位</div></div>
        <div class="kpi"><div class="v">{{ resume.parsed.解析字段['期望城市'] || '—' }}</div>
          <div class="l">期望城市</div></div>
        <div class="kpi"><div class="v">{{ resume.parsed.解析字段['工作年限'] }} 年</div>
          <div class="l">工作年限</div></div>
        <div class="kpi"><div class="v">{{ resume.parsed.技能数 }}</div><div class="l">识别技能数</div></div>
      </div>

      <div class="zq-card pad" style="margin-top:14px">
        <div style="margin-bottom:8px"><b>技能（{{ resume.parsed.技能数 }} 项）</b></div>
        <el-tag v-for="s in resume.parsed.技能列表" :key="s" effect="light"
                style="margin:0 6px 6px 0">{{ s }}</el-tag>
        <template v-if="resume.parsed.未在词典的技能.length">
          <div style="margin:10px 0 8px"><b>词典外技能（未参与余弦匹配）</b></div>
          <el-tag v-for="s in resume.parsed.未在词典的技能" :key="s" type="info" effect="plain"
                  style="margin:0 6px 6px 0">{{ s }}</el-tag>
        </template>
        <el-alert v-if="resume.parsed.解析告警.length" type="warning" :closable="false"
                  style="margin-top:12px"
                  :title="'解析告警：' + resume.parsed.解析告警.join('；')" />
        <div style="margin-top:12px">
          <el-button type="primary" @click="router.push('/jobs')">下一步：查看职位推荐 →</el-button>
          <el-popover placement="top" :width="420" trigger="click">
            <template #reference><el-button text>查看全部解析字段</el-button></template>
            <pre style="max-height:320px;overflow:auto;font-size:12px">{{ resume.parsed.解析字段 }}</pre>
          </el-popover>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type UploadFile } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import * as api from '../api'
import { useAuthStore } from '../stores/auth'
import { useResumeStore } from '../stores/resume'

const SAMPLE = `姓名：张伟
期望岗位：测试开发工程师
期望城市：苏州
期望薪资：12000-16000元
最高学历：大专
专业：软件技术
工作年限：3年
是否应届：否

【技能特长】
熟练掌握 Selenium、JMeter、Python、MySQL、Linux，了解 Postman 与 Git

【工作经历】
2022.07-2025.06 某软件公司 测试工程师，负责接口自动化测试与性能测试

【项目经验】
使用 Python + Selenium 搭建 UI 自动化框架，覆盖 300 条用例`

const router = useRouter()
const auth = useAuthStore()
const resume = useResumeStore()

const text = ref(resume.text || SAMPLE)
const loading = ref(false)

async function doParse() {
  if (!text.value.trim()) return ElMessage.warning('请先粘贴简历正文')
  loading.value = true
  try {
    const r = await api.parseResumeText(text.value)
    resume.setParsed(r, text.value)
    ElMessage.success('解析完成，会话 ID：' + r.resume_id)
  } catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}

async function onFile(f: UploadFile) {
  const raw = f.raw as File | undefined
  if (!raw) return
  loading.value = true
  try {
    const r = await api.parseResumePdf(raw)
    resume.setParsed(r, '')
    ElMessage.success('PDF 解析完成（' + r.来源 + '）')
  } catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}

async function saveToCenter() {
  try {
    const r = await api.createResume(
      (resume.parsed?.解析字段['期望岗位'] as string) || '我的简历', text.value)
    ElMessage.success('已保存（id=' + r.id + '），可在个人中心查看')
  } catch { /* 拦截器已提示 */ }
}
</script>

<style scoped>
.grid { display: grid; grid-template-columns: 1.35fr 1fr; gap: 14px; }
@media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } }
</style>
