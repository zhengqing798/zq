import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

/**
 * 路由（hash 模式：nginx 托管时无需额外 rewrite 配置，静态托管即可）
 * 个人中心需要登录；其余页面游客可用（与后端设计一致：核心功能允许游客体验）
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
        { path: 'resume', name: 'resume', component: () => import('../views/ResumeView.vue'),
          meta: { title: '简历' } },
        { path: 'jobs', name: 'jobs', component: () => import('../views/JobsView.vue'),
          meta: { title: '职位推荐' } },
        { path: 'clusters', name: 'clusters', component: () => import('../views/ClustersView.vue'),
          meta: { title: '岗位聚类' } },
        { path: 'chat', name: 'chat', component: () => import('../views/ChatView.vue'),
          meta: { title: '智能问答' } },
        { path: 'profile', name: 'profile', component: () => import('../views/ProfileView.vue'),
          meta: { title: '个人中心', requiresAuth: true } },
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
