<template>
  <div class="home">
    <!-- ① Hero 轮播：热门分类（取自真实的「来源关键词」列） -->
    <el-carousel v-if="st.热门分类.length" class="hero" height="286px"
                 :interval="4500" arrow="hover" indicator-position="outside">
      <el-carousel-item v-for="(c, i) in st.热门分类" :key="c.分类">
        <div class="slide" :class="'g' + (i % 6)">
          <div class="sleft">
            <div class="stag">热门分类</div>
            <div class="stitle">{{ c.分类 }}</div>
            <div class="snum"><b>{{ fmt(c.岗位数) }}</b> 个在招岗位</div>
            <div class="smeta">
              平均薪资上限 {{ fmtSalaryK(0, c.平均薪资上限) }} ｜ 在招企业 {{ c.公司数 }} 家
              ｜ 在线 {{ c.在线岗位数 }} 个
            </div>
            <div class="sskills">
              <el-tag v-for="s in c.热门技能" :key="s" size="small" effect="dark"
                      class="stg">{{ s }}</el-tag>
            </div>
            <div class="sbtns">
              <el-button type="primary" @click="goJobs({ source_kw: c.分类 })">
                看这类岗位 →</el-button>
              <el-button plain @click="goJobs({ source_kw: c.分类, sort: 'salary_desc' })">
                按薪资从高到低</el-button>
            </div>
          </div>
          <div class="sright">
            <div class="srtip">该类热门在招职位</div>
            <div v-for="j in c.示例岗位" :key="j.岗位ID" class="sjob" @click="openJob(j.岗位ID)">
              <div class="sj1">
                <span class="sjname">{{ j.岗位名称 }}</span>
                <span class="sjsal">{{ j.薪资 || '面议' }}</span>
              </div>
              <div class="sj2">{{ j.公司 }} ｜ {{ j.区县 || j.城市 }}</div>
            </div>
          </div>
        </div>
      </el-carousel-item>
    </el-carousel>

    <!-- ② 热门分类快捷条 -->
    <div class="chips">
      <span class="lb">热门分类：</span>
      <a v-for="c in st.热门分类" :key="c.分类" @click="goJobs({ source_kw: c.分类 })">
        {{ c.分类 }}<em>{{ c.岗位数 }}</em></a>
      <a class="more" @click="goJobs({})">全部岗位 →</a>
    </div>

    <!-- ③ 地区推荐 -->
    <div class="zq-section">地区推荐</div>
    <div class="regions">
      <div v-for="r in st.地区推荐" :key="r.城市" class="rcard" @click="goJobs({ city: r.城市 })">
        <div class="rc1"><b>{{ r.城市 }}</b><em>{{ r.省份 }}</em></div>
        <div class="rc2"><span class="num">{{ fmt(r.岗位数) }}</span> 个岗位
          ｜ {{ r.公司数 }} 家企业 ｜ {{ r.在线岗位数 }} 个在线</div>
        <div class="rc3">平均薪资上限 {{ fmtSalaryK(0, r.平均薪资上限) }}</div>
        <div class="rc4">
          <a v-for="d in r.热门区县" :key="d.名称"
             @click.stop="goJobs({ city: r.城市, district: d.名称 })">
            {{ d.名称 }}<em>{{ d.数量 }}</em></a>
        </div>
      </div>
    </div>

    <!-- ④ 高薪岗位推荐 -->
    <div class="zq-section">高薪岗位推荐</div>
    <div class="jobgrid">
      <div v-for="(j, i) in st.高薪岗位" :key="j.岗位ID" class="jmini" @click="openJob(j.岗位ID)">
        <div class="jm1">
          <span class="rank" :class="{ top: i < 3 }">{{ i + 1 }}</span>
          <span class="jmname">{{ j.岗位名称 }}</span>
          <span class="jmsal">{{ j.薪资 || '面议' }}</span>
        </div>
        <div class="jm2">
          <span class="jmco" @click.stop="goCompany(j)">{{ j.公司 }}</span>
        </div>
        <div class="jm3">
          {{ j.区县 || j.城市 }} ｜ {{ j.经验要求 || '经验不限' }} ｜ {{ j.学历要求 || '学历不限' }}
        </div>
        <div class="jm4">
          <el-tag v-for="s in j.技能标签.slice(0, 3)" :key="s" size="small" effect="plain"
                  class="jmtg">{{ s }}</el-tag>
        </div>
      </div>
    </div>

    <!-- ⑤ 热门岗位推荐 -->
    <div class="zq-section">热门岗位推荐</div>
    <div class="jobgrid">
      <div v-for="j in st.热门岗位" :key="j.岗位ID" class="jmini" @click="openJob(j.岗位ID)">
        <div class="jm1">
          <span class="jmname">{{ j.岗位名称 }}</span>
          <span class="jmsal">{{ j.薪资 || '面议' }}</span>
        </div>
        <div class="jm2">
          <span class="jmco" @click.stop="goCompany(j)">{{ j.公司 }}</span>
          <el-tag v-if="j.是否在线" size="small" type="success" effect="light" class="jml">在线</el-tag>
        </div>
        <div class="jm3">
          {{ j.区县 || j.城市 }} ｜ {{ j.招聘者 }}（{{ j.招聘者职位 }}）｜ {{ j.回复文案 }}
        </div>
        <div class="jm4">
          <el-tag v-for="s in j.技能标签.slice(0, 3)" :key="s" size="small" effect="plain"
                  class="jmtg">{{ s }}</el-tag>
        </div>
      </div>
    </div>

    <!-- ⑥ 热门企业 -->
    <div class="zq-section">热门企业</div>
    <div class="compgrid">
      <CompanyCard v-for="c in st.热门企业" :key="c.公司ID" :c="c" compact
                   @open="goCompanyCard" @job="openJob" />
    </div>

    <!-- ⑦ 热门技能 -->
    <div class="zq-section">热门技能</div>
    <div class="skills">
      <a v-for="s in st.热门技能" :key="s.名称" class="skill" @click="goJobs({ keyword: s.名称 })">
        {{ s.名称 }}<em>{{ s.数量 }}</em></a>
    </div>

    <!-- 数据来源与口径不再展示在页面上（接口仍返回，文档里仍记录） -->

    <JobDetailDrawer v-model="drawer" :job-id="curJob" />
  </div>
</template>

<script setup lang="ts">
/**
 * 首页 = 推荐页（游客可用）：热门分类 hero 轮播 → 地区推荐 → 高薪岗位 →
 * 热门岗位 → 热门企业 → 热门技能。
 *
 * 所有榜单都来自真实列；排序口径由接口 `口径说明` 返回并记录在《系统设计文档》§3.10，
 * 页面上不再展示这类说明文字（按使用者要求：页面上不放口径/来源描述）。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as api from '../api'
import type { HomeJob, HomeResp } from '../api/home'
import type { CompanyItem } from '../api/companies'
import CompanyCard from '../components/CompanyCard.vue'
import JobDetailDrawer from '../components/JobDetailDrawer.vue'
import { fmtNum, fmtSalaryK } from '../utils/format'

const router = useRouter()

const empty: HomeResp = {
  ok: true, 热门分类: [], 地区推荐: [], 高薪岗位: [], 热门岗位: [], 热门企业: [],
  热门技能: [], 总体: { 岗位数: 0, 公司数: 0, 城市数: 0, 在线岗位数: 0, 有回复岗位数: 0 },
  口径说明: [], 来源: [],
}
const st = ref<HomeResp>(empty)
const drawer = ref(false)
const curJob = ref('')

const fmt = fmtNum

/** 跳「岗位」页并带上筛选条件（该页支持 URL 查询参数） */
function goJobs(q: Record<string, string>) {
  router.push({ path: '/jobs', query: q })
}
function openJob(jobId: string) { curJob.value = jobId; drawer.value = true }
function goCompany(j: HomeJob) { if (j.公司ID) router.push('/company/' + j.公司ID) }
function goCompanyCard(c: CompanyItem) { router.push('/company/' + c.公司ID) }

onMounted(async () => {
  try { st.value = await api.home(8) } catch { /* 拦截器已提示 */ }
})
</script>

<style scoped>
.home { max-width: 1180px; margin: 0 auto; }
.muted { color: #8896ab; font-size: 12.5px; }

/* ---------- Hero 轮播 ---------- */
.hero { border-radius: 14px; overflow: hidden; }
.hero :deep(.el-carousel__indicators--outside) { margin-top: 4px; }
.hero :deep(.el-carousel__indicator button) { background: #c3ccda; }
.slide { height: 100%; border-radius: 14px; padding: 22px 26px; display: flex; gap: 24px;
  color: #fff; }
.slide.g0 { background: linear-gradient(120deg, #00a6a7 0%, #12c2b4 60%, #57d9c8 100%); }
.slide.g1 { background: linear-gradient(120deg, #2b6cb0 0%, #3f8fd0 60%, #6bb6e8 100%); }
.slide.g2 { background: linear-gradient(120deg, #7c3aed 0%, #9a5cf5 60%, #b98bfa 100%); }
.slide.g3 { background: linear-gradient(120deg, #d97706 0%, #f59e0b 60%, #fbbf24 100%); }
.slide.g4 { background: linear-gradient(120deg, #0f766e 0%, #14907f 60%, #3fb39c 100%); }
.slide.g5 { background: linear-gradient(120deg, #be185d 0%, #db2777 60%, #f472b6 100%); }
.sleft { flex: 1; min-width: 0; }
.stag { display: inline-block; font-size: 12px; padding: 2px 10px; border-radius: 20px;
  background: rgba(255,255,255,.22); }
.stitle { font-size: 34px; font-weight: 800; margin-top: 8px; letter-spacing: 1px; }
.snum { font-size: 15px; opacity: .95; margin-top: 2px; }
.snum b { font-size: 22px; }
.smeta { font-size: 12.5px; opacity: .9; margin-top: 6px; }
.sskills { margin-top: 10px; }
.stg { margin: 0 6px 6px 0; background: rgba(255,255,255,.18); border: none; color: #fff; }
.sbtns { margin-top: 10px; display: flex; gap: 10px; }
.sright { width: 372px; flex: none; background: rgba(255,255,255,.14); border-radius: 12px;
  padding: 12px 14px; }
.srtip { font-size: 12px; opacity: .85; margin-bottom: 6px; }
.sjob { padding: 6px 0; cursor: pointer; border-bottom: 1px dashed rgba(255,255,255,.22); }
.sjob:last-child { border-bottom: none; }
.sjob:hover .sjname { text-decoration: underline; }
.sj1 { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
.sjname { font-size: 13.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.sjsal { font-size: 13.5px; font-weight: 800; white-space: nowrap; }
.sj2 { font-size: 12px; opacity: .85; margin-top: 2px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }

/* ---------- 热门分类快捷条 ---------- */
.chips { background: #fff; border: 1px solid var(--zq-border); border-radius: 12px;
  padding: 10px 18px; margin-top: 14px; display: flex; flex-wrap: wrap; gap: 4px 14px;
  align-items: center; }
.chips .lb { color: #8896ab; font-size: 13px; }
.chips a { color: #41506b; font-size: 13.5px; cursor: pointer; }
.chips a:hover { color: var(--el-color-primary); }
.chips em { font-style: normal; color: #b3bfd0; font-size: 11.5px; margin-left: 3px; }
.chips a.more { color: var(--el-color-primary); font-weight: 700; }

/* ---------- 地区推荐 ---------- */
.regions { display: grid; grid-template-columns: repeat(auto-fill, minmax(268px, 1fr)); gap: 12px; }
.rcard { background: #fff; border: 1px solid var(--zq-border); border-radius: 12px;
  padding: 12px 14px; cursor: pointer; transition: .16s; box-shadow: var(--zq-card-shadow); }
.rcard:hover { box-shadow: 0 8px 22px rgba(0,166,167,.14); transform: translateY(-2px);
  border-color: var(--el-color-primary-light-5); }
.rc1 { display: flex; align-items: baseline; gap: 8px; }
.rc1 b { font-size: 17px; color: #16233a; }
.rc1 em { font-style: normal; color: #b3bfd0; font-size: 12px; }
.rc2 { margin-top: 6px; color: #5b6b7f; font-size: 12.5px; }
.rc2 .num { color: #ff6a00; font-weight: 800; font-size: 15px; }
.rc3 { margin-top: 4px; color: #8896ab; font-size: 12.5px; }
.rc4 { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 8px; }
.rc4 a { font-size: 12.5px; color: var(--el-color-primary); cursor: pointer; }
.rc4 a:hover { text-decoration: underline; }
.rc4 em { font-style: normal; color: #b3bfd0; margin-left: 3px; }

/* ---------- 岗位推荐网格 ---------- */
.jobgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 12px; }
.jmini { background: #fff; border: 1px solid var(--zq-border); border-radius: 12px;
  padding: 12px 14px; cursor: pointer; transition: .16s; box-shadow: var(--zq-card-shadow); }
.jmini:hover { box-shadow: 0 8px 22px rgba(0,166,167,.14); transform: translateY(-2px);
  border-color: var(--el-color-primary-light-5); }
.jm1 { display: flex; align-items: baseline; gap: 8px; }
.jm1 .rank { width: 18px; height: 18px; border-radius: 5px; flex: none; color: #fff; font-size: 11.5px;
  font-weight: 700; display: flex; align-items: center; justify-content: center; background: #c3ccda; }
.jm1 .rank.top { background: linear-gradient(135deg, #ff8a3d, #ff6a00); }
.jmname { flex: 1; min-width: 0; font-size: 15px; font-weight: 700; color: #16233a;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jmsal { font-size: 15px; font-weight: 800; color: #ff6a00; white-space: nowrap; }
.jm2 { margin-top: 6px; display: flex; align-items: center; gap: 6px; font-size: 13px; }
.jmco { color: #41506b; cursor: pointer; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.jmco:hover { color: var(--el-color-primary); }
.jml { flex: none; }
.jm3 { margin-top: 4px; color: #8896ab; font-size: 12.5px; }
.jm4 { margin-top: 8px; }
.jmtg { margin: 0 6px 4px 0; }

/* ---------- 热门企业 ---------- */
.compgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }

/* ---------- 热门技能 ---------- */
.skills { display: flex; flex-wrap: wrap; gap: 8px; }
.skill { background: #fff; border: 1px solid var(--zq-border); border-radius: 8px;
  padding: 6px 12px; font-size: 13px; color: #41506b; cursor: pointer; transition: .16s; }
.skill:hover { color: var(--el-color-primary); border-color: var(--el-color-primary-light-5); }
.skill em { font-style: normal; color: #b3bfd0; font-size: 11.5px; margin-left: 5px; }

/* ---------- 底部 ---------- */
@media (max-width: 900px) {
  .slide { flex-direction: column; padding: 16px; }
  .sright { width: auto; }
  .stitle { font-size: 26px; }
}
</style>
