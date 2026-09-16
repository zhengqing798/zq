<template>
  <div class="zq-header">
    <div class="zq-header-inner">
      <!-- 左：品牌 -->
      <div class="zq-brand" @click="router.push('/jobs')">
        <div class="logo">🎯</div>
        <div>
          <div class="name">人岗匹配推荐</div>
          <div class="sub">岗位-简历智能匹配系统</div>
        </div>
      </div>

      <!-- 中：导航 -->
      <nav class="zq-nav">
        <router-link v-for="m in menus" :key="m.path" :to="m.path"
                     :class="{ active: route.path.startsWith(m.path) }">
          {{ m.label }}
        </router-link>
      </nav>

      <!-- 右：用户区 / 登录 -->
      <div class="zq-user">
        <template v-if="auth.isLogged()">
          <el-dropdown @command="onCommand">
            <span class="el-dropdown-link" style="cursor:pointer;display:flex;align-items:center;gap:8px">
              <el-avatar :size="30" style="background:var(--el-color-primary)">
                {{ (auth.user?.nickname || auth.user?.username || '?').slice(0, 1) }}
              </el-avatar>
              <span style="font-weight:600">{{ auth.user?.nickname || auth.user?.username }}</span>
              <el-tag size="small" type="success" effect="light">{{ auth.user?.role_label }}</el-tag>
              <el-icon><arrow-down /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
        <template v-else>
          <span class="muted">游客模式 · 数据不会保存</span>
          <el-button type="primary" plain @click="router.push('/login')">登录 / 注册</el-button>
        </template>
      </div>
    </div>
  </div>

  <div class="zq-main">
    <router-view />
    <el-divider />
    <div class="muted" style="text-align:center">
      岗位-简历人岗匹配推荐系统 ｜ 任务11 前后端集成（Vue3 + Element Plus 前端 · FastAPI 后端）
      ｜ 数据：8,836 岗位 / 500 简历 / 8,852 知识卡片 ｜ 每个结论都带 <b>来源</b>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const menus = computed(() => {
  const base = [
    { path: '/resume', label: '📄 简历' },
    { path: '/jobs', label: '🎯 职位推荐' },
    { path: '/clusters', label: '🏢 岗位聚类' },
    { path: '/chat', label: '💬 智能问答' },
  ]
  if (auth.isLogged()) base.push({ path: '/profile', label: '👤 个人中心' })
  return base
})

async function onCommand(cmd: string) {
  if (cmd === 'profile') router.push('/profile')
  if (cmd === 'logout') {
    await auth.doLogout()
    ElMessage.success('已退出登录')
    router.push('/jobs')
  }
}
</script>
