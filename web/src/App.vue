<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'

// 刷新后若本地有令牌，拉一次当前用户，保证登录态一致
const auth = useAuthStore()
onMounted(() => { auth.fetchMe() })
</script>
