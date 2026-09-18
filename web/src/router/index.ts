import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

/**
 * 路由（hash 模式：nginx 托管时无需额外 rewrite 配置，静态托管即可）
 *
 * 导航结构（2026-09-18 改版）：
 * · 游客可见：首页（推荐）/ 岗位（浏览筛选）/ 公司
 * · 需登录：岗位推荐（简历匹配）、个人中心（简历粘贴/上传 PDF 也在这里，不再有独立「简历」页）
 * · 没有导航入口但保留页面：智能问答（#/chat）
 * · 旧地址兼容：/resume → /profile（简历已并入个人中心）
 */
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
    {
      path: '/',
      component: () => import('../layouts/AppLayout.vue'),
      children: [
        { path: '', redirect: '/home' },
        { path: 'home', name: 'home', component: () => import('../views/HomeView.vue'),
          meta: { title: '首页' } },
        { path: 'jobs', name: 'jobs', component: () => import('../views/JobsBrowseView.vue'),
          meta: { title: '岗位' } },
        { path: 'companies', name: 'companies', component: () => import('../views/CompaniesView.vue'),
          meta: { title: '公司' } },
        { path: 'company/:id', name: 'company', component: () => import('../views/CompanyView.vue'),
          meta: { title: '公司详情' } },
        { path: 'match', name: 'match', component: () => import('../views/MatchView.vue'),
          meta: { title: '岗位推荐', requiresAuth: true } },
        { path: 'chat', name: 'chat', component: () => import('../views/ChatView.vue'),
          meta: { title: '智能问答' } },
        { path: 'profile', name: 'profile', component: () => import('../views/ProfileView.vue'),
          meta: { title: '个人中心', requiresAuth: true } },
        // 旧地址兼容：简历页已并入个人中心
        { path: 'resume', redirect: '/profile' },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/home' },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isLogged()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
