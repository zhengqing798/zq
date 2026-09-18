<template>
  <!-- 悬浮球：按住可拖动，位置记在 localStorage；单击开/关对话框 -->
  <div class="ball" :style="{ left: pos.x + 'px', top: pos.y + 'px' }"
       :class="{ open }" title="智能问答"
       @mousedown="startDrag" @touchstart="startDrag"
       @click="onBallClick">
    <span class="ico">{{ open ? '✕' : '💬' }}</span>
  </div>
  <!-- 小对话框：贴着球的一侧弹出 -->
  <transition name="pop">
    <div v-if="open" class="panel" :style="panelStyle">
      <div class="phead">
        <b>智能问答</b>
        <span class="spacer" />
        <el-button link size="small" @click="open = false">收起</el-button>
      </div>

      <div ref="bodyEl" class="pbody">
        <div v-if="!msgs.length" class="phint">
          <div class="muted" style="margin-bottom:6px">试试：</div>
          <el-tag v-for="s in samples" :key="s" effect="plain" class="tag"
                  @click="ask(s)">{{ s }}</el-tag>
        </div>

        <div v-for="(m, i) in msgs" :key="i" class="row" :class="m.role">
          <div class="bubble">{{ m.text }}</div>
          <div v-if="m.resp" class="meta">
            <div class="muted">
              {{ m.resp.工具序列 || '（未调用工具）' }} ｜ {{ m.resp.轮数 }} 轮
              ｜ {{ m.resp.耗时秒 }}s{{ m.resp.缓存命中 ? ' ｜ 缓存命中' : '' }}
            </div>
            <el-collapse>
              <el-collapse-item :title="'🔧 工具轨迹（' + m.resp.工具轨迹.length + ' 步）'">
                <el-timeline>
                  <el-timeline-item v-for="(t, k) in m.resp.工具轨迹" :key="k"
                                    :timestamp="'ok=' + t.ok" placement="top"
                                    :type="t.ok ? 'success' : 'danger'">
                    <b>{{ t.工具 }}</b>
                    <div class="muted">参数：<code>{{ JSON.stringify(t.参数) }}</code></div>
                    <div>{{ t.结果摘要 }}</div>
                  </el-timeline-item>
                </el-timeline>
              </el-collapse-item>
              <el-collapse-item :title="'📎 来源（' + m.resp.来源.length + ' 条）'">
                <div v-for="s in m.resp.来源" :key="s" class="src"><code>{{ s }}</code></div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>

        <div v-if="loading" class="muted" style="padding:6px 2px">正在检索…</div>
      </div>

      <div class="pfoot">
        <el-input v-model="q" placeholder="输入问题…" :disabled="loading"
                  @keyup.enter="ask()" />
        <el-button type="primary" :loading="loading" @click="ask()">发送</el-button>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
/**
 * 智能问答悬浮球（全局挂在 AppLayout 上，每个页面都能用）
 *
 * · 悬浮球可**拖动**（鼠标/触摸），位置存 localStorage，刷新后仍在原处
 * · 单击球开/关右侧（或左侧）的**小对话框**，在里面提问并查看检索结果
 * · 拖动超过 4px 视为拖动，不触发开关（避免"想拖却点开"）
 */
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'
import type { ChatResp } from '../api/types'

const SAMPLES = [
  '厦门有哪些 Java 开发岗位？',
  '岗位可以分成哪几类？',
  '软件测试类岗位大概是什么样的？',
  '匹配系统给一份简历打分要多久？',
]
const KEY = 'zq_chat_ball'
const BALL = 54
const PW = 370
const PH = 520

const open = ref(false)
const q = ref('')
const loading = ref(false)
const msgs = ref<{ role: 'me' | 'ai'; text: string; resp?: ChatResp }[]>([])
const bodyEl = ref<HTMLElement | null>(null)
const samples = SAMPLES

const vw = ref(window.innerWidth)
const vh = ref(window.innerHeight)
/** 期望位置（拖动时更新、存 localStorage）；渲染位置 = 夹进视口后的结果 */
const want = ref({ x: window.innerWidth - BALL - 26, y: window.innerHeight - BALL - 34 })

/** 把坐标夹进视口 */
function clampTo(p: { x: number; y: number }, w: number, h: number) {
  return {
    x: Math.min(Math.max(6, p.x), Math.max(6, w - BALL - 6)),
    y: Math.min(Math.max(6, p.y), Math.max(6, h - BALL - 6)),
  }
}
/**
 * 关键：**夹取只影响渲染，不改期望位置**。
 * 否则一旦视口被临时改小（截图工具、手机旋转、开发者工具切换设备等触发 resize），
 * 球会被永久压到左上角，用户拖好的位置就丢了。
 */
const pos = computed(() => clampTo(want.value, vw.value, vh.value))

let dragging = false
let moved = false
let suppressClickUntil = 0
let start = { x: 0, y: 0 }
let origin = { x: 0, y: 0 }

const pt = (e: MouseEvent | TouchEvent) => {
  const t = (e as TouchEvent).touches?.[0]
  return t ? { x: t.clientX, y: t.clientY } : { x: (e as MouseEvent).clientX, y: (e as MouseEvent).clientY }
}

function startDrag(e: MouseEvent | TouchEvent) {
  dragging = true
  moved = false
  start = pt(e)
  origin = { ...want.value }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', endDrag)
  window.addEventListener('touchmove', onMove, { passive: false })
  window.addEventListener('touchend', endDrag)
}

function onMove(e: MouseEvent | TouchEvent) {
  if (!dragging) return
  const p = pt(e)
  if (Math.abs(p.x - start.x) > 4 || Math.abs(p.y - start.y) > 4) moved = true
  want.value = { x: origin.x + (p.x - start.x), y: origin.y + (p.y - start.y) }
  if (e.cancelable) e.preventDefault()
}

function endDrag() {
  dragging = false
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', endDrag)
  window.removeEventListener('touchmove', onMove)
  window.removeEventListener('touchend', endDrag)
  if (moved) {
    localStorage.setItem(KEY, JSON.stringify(want.value))
    // 拖动结束后的那次 click 不应该被当成"点开/收起"——但只用**时间窗**屏蔽，
    // 不能用一次性开关：鼠标若在球外松开，浏览器根本不会补发 click，
    // 开关留在"已屏蔽"状态会把用户的下一次真实点击吃掉（踩过这个坑）。
    suppressClickUntil = Date.now() + 300
  }
}

function onBallClick() {
  if (Date.now() < suppressClickUntil) return
  open.value = !open.value
}

/** 对话框贴着球的一侧展开，并保证不出屏 */
const panelStyle = computed(() => {
  const onLeftHalf = pos.value.x < vw.value / 2
  let left = onLeftHalf ? pos.value.x + BALL + 10 : pos.value.x - PW - 10
  let top = pos.value.y + BALL - PH
  left = Math.min(Math.max(8, left), Math.max(8, vw.value - PW - 8))
  top = Math.min(Math.max(8, top), Math.max(8, vh.value - PH - 8))
  const w = Math.min(PW, vw.value - 16)
  return { left: left + 'px', top: top + 'px', width: w + 'px', height: Math.min(PH, vh.value - 16) + 'px' }
})

function onResize() {
  // 视口变化只更新尺寸（渲染位置随之被夹取），**不动期望位置**
  vw.value = window.innerWidth
  vh.value = window.innerHeight
}

async function ask(text?: string) {
  const question = (text ?? q.value).trim()
  if (!question || loading.value) return
  q.value = ''
  msgs.value.push({ role: 'me', text: question })
  loading.value = true
  await scrollDown()
  try {
    const resp = await api.ask(question)
    msgs.value.push({ role: 'ai', text: resp.回答, resp })
  } catch {
    msgs.value.push({ role: 'ai', text: '这次没查到结果，换个说法再试试。' })
  } finally {
    loading.value = false
    await scrollDown()
  }
}

async function scrollDown() {
  await nextTick()
  const el = bodyEl.value
  if (el) el.scrollTop = el.scrollHeight
}

onMounted(() => {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || 'null')
    if (saved && typeof saved.x === 'number') want.value = saved
  } catch { /* 位置坏了就用默认右下 */ }
  window.addEventListener('resize', onResize)
})
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<style scoped>
/* ---------- 悬浮球 ---------- */
.ball {
  position: fixed; z-index: 1800; width: 54px; height: 54px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; cursor: grab;
  color: #fff; font-size: 24px; user-select: none; touch-action: none;
  background: linear-gradient(135deg, #00a6a7, #12c2b4);
  box-shadow: 0 8px 22px rgba(0, 166, 167, .42);
  transition: transform .16s, box-shadow .16s;
}
.ball:hover { transform: scale(1.06); box-shadow: 0 10px 26px rgba(0, 166, 167, .55); }
.ball:active { cursor: grabbing; }
.ball.open { background: linear-gradient(135deg, #41506b, #5b6b7f); font-size: 18px; }
.ball .ico { pointer-events: none; line-height: 1; }

/* ---------- 小对话框 ---------- */
.panel {
  position: fixed; z-index: 1800; background: #fff; border: 1px solid var(--zq-border);
  border-radius: 14px; box-shadow: 0 18px 44px rgba(16, 43, 51, .18);
  display: flex; flex-direction: column; overflow: hidden;
}
.phead { display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  border-bottom: 1px solid var(--zq-border); background: #f7fbfb; }
.phead b { font-size: 14.5px; color: #16233a; }
.phead .spacer { flex: 1; }
.pbody { flex: 1; min-height: 0; overflow: auto; padding: 12px; }
.pfoot { display: flex; gap: 8px; padding: 10px 12px; border-top: 1px solid var(--zq-border);
  background: #fbfcfd; }
.pfoot :deep(.el-input) { flex: 1; }
.phint .tag { margin: 0 6px 6px 0; cursor: pointer; }
.row { margin-bottom: 12px; display: flex; flex-direction: column; }
.row.me { align-items: flex-end; }
.row.ai { align-items: flex-start; }
.bubble { max-width: 92%; padding: 9px 12px; border-radius: 10px; font-size: 13.5px;
  line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.row.me .bubble { background: var(--el-color-primary-light-9); border: 1px solid #cdeeee; }
.row.ai .bubble { background: #fbfcfe; border: 1px solid var(--zq-border); }
.meta { max-width: 100%; margin-top: 6px; font-size: 12px; }
.meta .muted { font-size: 11.5px; }
.meta :deep(.el-collapse-item__header) { height: 32px; line-height: 32px; font-size: 12.5px; }
.meta :deep(.el-collapse-item__content) { font-size: 12px; padding-bottom: 6px; }
.meta :deep(.el-timeline) { padding-left: 4px; }
.src code { background: #f2f6fb; padding: 1px 5px; border-radius: 4px; font-size: 11.5px; }

.pop-enter-active, .pop-leave-active { transition: opacity .16s, transform .16s; }
.pop-enter-from, .pop-leave-to { opacity: 0; transform: translateY(8px) scale(.98); }
</style>
