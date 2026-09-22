<template>
  <div ref="el" :style="{ height: height, width: '100%' }"></div>
</template>

<script setup lang="ts">
/**
 * ECharts 轻量封装：负责初始化、随 option 更新、窗口缩放自适应、卸载时销毁
 *
 * ⚠️ **不要**把它改回 `import * as echarts from 'echarts'`（全量引入）。
 * 整套 Vue 前端只有「岗位详情页」的一张六维雷达图用到 ECharts，全量引入却会把整包
 * （约 1MB）打进 JobView 的页面 chunk —— 实测 `JobView-*.js` 因此膨胀到 1.13MB，
 * 用户要下完这 1MB 才可能看到雷达图。
 *
 * 现在改成按需引入：只带雷达图系列 + 雷达坐标系 + tooltip + 画布渲染器。
 * 体积对比见《测试报告》任务13 的性能优化小节。
 *
 * 以后要用别的图表（柱状/折线/饼图…）或别的组件（dataZoom / visualMap…），
 * **必须**在这里补上对应的 import 并加进 `echarts.use([...])` —— 漏了不会报错，
 * 只是那张图静默不渲染，很难查。
 */
import * as echarts from 'echarts/core'
import { RadarChart } from 'echarts/charts'
import { LegendComponent, RadarComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ECharts } from 'echarts/core'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

echarts.use([RadarChart, RadarComponent, TooltipComponent, LegendComponent, TitleComponent,
             CanvasRenderer])

const props = defineProps<{ option: Record<string, unknown>; height?: string }>()
const el = ref<HTMLElement | null>(null)
let chart: ECharts | null = null

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
