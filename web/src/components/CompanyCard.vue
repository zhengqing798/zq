<template>
  <div class="ccard" :class="{ compact }" @click="emit('open', c)">
    <div class="crow">
      <div class="logo" :style="{ background: logoBg(c.公司ID) }">{{ logoChar(c.公司名称) }}</div>
      <div class="cmain">
        <div class="cname">{{ c.公司名称 }}</div>
        <div class="cmeta">
          <span class="hot">在招 {{ c.在招岗位数 }} 个职位</span>
          <i>·</i>
          <span>{{ c.主要城市 }}<template v-if="c.城市数 > 1"> 等 {{ c.城市数 }} 城</template></span>
          <i>·</i>
          <span>{{ c.主要大类 }}类</span>
          <i>·</i>
          <span :title="sizeTip">{{ c.规模分档 }}</span>
        </div>
        <div v-if="!compact" class="cmeta2">
          招聘者 {{ c.招聘者数 }} 人 ｜ 在线岗位 {{ c.在线岗位数 }} 个
          ｜ 今日回复 {{ c.今日回复总数 }} 次
          <template v-if="c.区县数"> ｜ 覆盖 {{ c.区县数 }} 个区县</template>
        </div>
      </div>
      <div class="cright">
        <div class="sal">{{ fmtSalaryK(c.薪资下限中位数, c.薪资上限中位数) }}</div>
        <div class="muted">薪资中位数/月</div>
      </div>
    </div>

    <template v-if="!compact">
      <div class="cline">
        <span class="lb">技能需求：</span>
        <el-tag v-for="s in c.技能需求.slice(0, 6)" :key="s.名称" size="small" effect="plain"
                class="tg">{{ s.名称 }}<em>{{ s.数量 }}</em></el-tag>
        <span v-if="!c.技能需求.length" class="muted">该岗位未标注技能标签</span>
      </div>
      <div class="cline">
        <span class="lb">热招职位：</span>
        <a v-for="j in c.热招职位" :key="j.岗位ID" class="job" @click.stop="emit('job', j.岗位ID)">
          {{ j.岗位名称 }}<b>{{ j.薪资 }}</b>
          <em>{{ j.区县 || j.城市 }}</em>
        </a>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/** 公司卡片（公司列表 + 公司详情页「相似公司」共用） */
import type { CompanyItem } from '../api/companies'
import { fmtSalaryK, logoBg, logoChar } from '../utils/format'

withDefaults(defineProps<{ c: CompanyItem; compact?: boolean }>(), { compact: false })
const emit = defineEmits<{ open: [CompanyItem]; job: [string] }>()
const sizeTip = '数据里没有「公司规模」列，这里用该公司的在招职位数分档代理'
</script>

<style scoped>
.ccard { background: #fff; border: 1px solid var(--zq-border); border-radius: 12px;
  padding: 14px 16px; cursor: pointer; transition: .16s; box-shadow: var(--zq-card-shadow); }
.ccard:hover { box-shadow: 0 8px 22px rgba(0, 166, 167, .14); transform: translateY(-2px);
  border-color: var(--el-color-primary-light-5); }
.crow { display: flex; gap: 12px; align-items: flex-start; }
.logo { width: 46px; height: 46px; border-radius: 10px; flex: none; color: #fff;
  font-size: 21px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.compact .logo { width: 38px; height: 38px; font-size: 17px; }
.cmain { flex: 1; min-width: 0; }
.cname { font-size: 16px; font-weight: 700; color: #16233a; line-height: 1.35; }
.cmeta { margin-top: 5px; color: #5b6b7f; font-size: 13px; display: flex; flex-wrap: wrap;
  align-items: center; gap: 4px; }
.cmeta i { color: #c9d3e0; font-style: normal; }
.cmeta .hot { color: #ff6a00; font-weight: 700; }
.cmeta2 { margin-top: 4px; color: #8896ab; font-size: 12.5px; }
.cright { flex: none; text-align: right; }
.sal { font-size: 16px; font-weight: 800; color: #ff6a00; white-space: nowrap; }
.muted { color: #8896ab; font-size: 12px; }
.cline { margin-top: 10px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  font-size: 13px; }
.cline .lb { color: #8896ab; font-size: 12.5px; }
.tg em { font-style: normal; color: #b3bfd0; font-size: 11px; margin-left: 3px; }
.cline a.job { color: #41506b; cursor: pointer; text-decoration: none; margin-right: 10px; }
.cline a.job:hover { color: var(--el-color-primary); }
.cline a.job b { color: #ff6a00; font-weight: 700; margin-left: 4px; }
.cline a.job em { font-style: normal; color: #b3bfd0; font-size: 11.5px; margin-left: 4px; }
</style>
