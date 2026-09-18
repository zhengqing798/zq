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
        <router-link v-for="m in menus" :key="m.path" :to="m.path" :class="{ active: isActive(m) }">
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
  </div>

  <!-- 全局智能问答悬浮球（可拖动，点开是小对话框） -->
  <ChatWidget />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import ChatWidget from '../components/ChatWidget.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const menus = computed(() => {
  // 顶部标签：首页 / 岗位 / 公司（游客可见）；岗位推荐需登录后才有
  const base = [
    { path: '/home', label: '🏠 首页', match: ['/home'] },
    { path: '/jobs', label: '💼 岗位', match: ['/jobs'] },
    { path: '/companies', label: '🏬 公司', match: ['/companies', '/company/'] },
  ]
  if (auth.isLogged()) base.push({ path: '/match', label: '🎯 岗位推荐', match: ['/match'] })
  return base
})

/** 导航高亮：公司列表与公司详情属于同一个栏目 */
const isActive = (m: { match: string[] }) => m.match.some((p) => route.path.startsWith(p))

async function onCommand(cmd: string) {
  if (cmd === 'profile') router.push('/profile')
  if (cmd === 'logout') {
    await auth.doLogout()
    ElMessage.success('已退出登录')
    router.push('/home')
  }
}
</script>
