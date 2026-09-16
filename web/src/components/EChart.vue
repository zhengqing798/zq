<template>
  <div ref="el" :style="{ height: height, width: '100%' }"></div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

// ECharts 轻量封装：负责初始化、随 option 更新、窗口缩放自适应、卸载时销毁
const props = defineProps<{ option: Record<string, unknown>; height?: string }>()
const el = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

function render() {
  if (el.value) chart?.setOption(props.option as never, true)
}
onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value)
  render()
  window.addEventListener('resize', onResize)
})
function onResize() { chart?.resize() }
watch(() => props.option, render, { deep: true })
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>
