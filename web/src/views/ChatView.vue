<template>
  <div>
    <div class="zq-page-title">智能问答</div>
    <div class="zq-page-desc">
      Agent · Function Calling + 9 个工具：问题 → DeepSeek 选工具 → 本地执行 → 带来源的中文回答
    </div>

    <div class="zq-card pad">
      <div style="display:flex;gap:10px">
        <el-input v-model="q" size="large" placeholder="问点什么，例如：福州市的Java岗位有多少个？"
                  @keyup.enter="send" />
        <el-button type="primary" size="large" :loading="loading" @click="send">提问</el-button>
      </div>
      <div style="margin-top:10px;display:flex;gap:10px;align-items:center">
        <el-checkbox v-model="noCache">忽略缓存（强制真实调用，较慢）</el-checkbox>
        <span class="muted">每次提问约 3~10 秒；相同问题命中缓存则秒回</span>
      </div>
      <div style="margin-top:10px">
        <span class="muted">试试：</span>
        <el-tag v-for="s in samples" :key="s" effect="plain" style="margin:4px 6px 0 0;cursor:pointer"
                @click="q = s; send()">{{ s }}</el-tag>
      </div>
    </div>

    <div v-if="cur" style="margin-top:16px">
      <div class="kpi-row">
        <div class="kpi"><div class="v" style="font-size:15px">{{ cur.工具序列 || '（未调用）' }}</div>
          <div class="l">工具序列</div></div>
        <div class="kpi"><div class="v">{{ cur.轮数 }}</div><div class="l">轮数</div></div>
        <div class="kpi"><div class="v">{{ cur.耗时秒 }} s</div><div class="l">耗时</div></div>
        <div class="kpi"><div class="v">{{ cur.缓存命中 ? '命中' : '未命中' }}</div>
          <div class="l">结果缓存</div></div>
        <div class="kpi"><div class="v" style="font-size:16px">{{ cur.prompt版本 }}</div>
          <div class="l">Prompt 版本</div></div>
      </div>

      <div class="zq-section">回答（每个数字都带来源）</div>
      <div class="chat-bubble me">{{ cur.回答 }}</div>
      <div class="muted" style="margin-top:6px">
        模型 {{ cur.模型 }} ｜ prompt {{ cur.tokens.prompt }} + completion {{ cur.tokens.completion }} tokens
        <span v-if="cur.已存历史"> ｜ ✅ 已存入问答记录</span>
      </div>

      <el-collapse style="margin-top:12px">
        <el-collapse-item :title="'🔧 工具轨迹（每一步查了什么）'">
          <el-timeline>
            <el-timeline-item v-for="(t, i) in cur.工具轨迹" :key="i" :timestamp="'ok=' + t.ok"
                              placement="top" :type="t.ok ? 'success' : 'danger'">
              <b>{{ t.工具 }}</b>
              <div class="muted">参数：<code>{{ JSON.stringify(t.参数) }}</code></div>
              <div>{{ t.结果摘要 }}</div>
            </el-timeline-item>
          </el-timeline>
        </el-collapse-item>
        <el-collapse-item :title="'📎 来源（' + cur.来源.length + ' 条，可追溯）'">
          <div v-for="s in cur.来源" :key="s"><code>{{ s }}</code></div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <el-empty v-else description="问一句试试，例如「福州市的Java岗位有多少个？」" />

    <div class="zq-card pad" style="margin-top:16px">
      <div class="zq-section" style="margin-top:0">这个问答系统怎么做的</div>
      <div class="muted" style="line-height:1.95">
        8,852 张知识卡片（岗位卡 8,836 + 结论卡 16）用本地 <b>BGE-small-zh-v1.5</b>（512 维）向量化，
        存 FAISS 用<b>余弦检索</b>；统计/口径类问句走<b>分类型路由</b>只查结论卡，避免被 8,836 张岗位卡淹没
        （召回评估 P@5 <b>0.147 → 0.353</b>）。Agent 最多 6 轮、12 次工具调用，
        <b>30 问「问题—答案—来源」三元组有来源标注 30/30（100%）</b>。
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'
import type { ChatResp } from '../api/types'

const q = ref('福州市的Java岗位有多少个？')
const noCache = ref(false)
const loading = ref(false)
const cur = ref<ChatResp | null>(null)

const samples = [
  '厦门有哪些 Java 开发岗位？顺便说下厦门整体的薪资水平。',
  '岗位可以分成哪几类？软件测试类岗位大概是什么样的？',
  '薪资是用中位数还是平均数描述更合适？',
  '匹配系统给一份简历打分要多久？',
  '帮我看看北京有没有合适的岗位，我想投字节跳动。',
]

async function send() {
  if (!q.value.trim()) return ElMessage.warning('请输入问题')
  loading.value = true
  try { cur.value = await api.ask(q.value.trim(), !noCache.value) }
  catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}
</script>
