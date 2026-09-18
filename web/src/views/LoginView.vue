<template>
  <div class="login-wrap">
    <div class="login-box">
      <!-- 极简品牌头（原来的左栏大面板已按要求删除） -->
      <div class="brand">
        <div class="logo">🎯</div>
        <div class="name">人岗匹配推荐系统</div>
      </div>

      <el-card shadow="never" class="box">
        <el-tabs v-model="tab" stretch>
          <el-tab-pane label="登录" name="login">
            <el-form :model="lf" label-position="top" @submit.prevent>
              <el-form-item label="用户名">
                <el-input v-model="lf.username" size="large" placeholder="请输入用户名"
                          :prefix-icon="User" @keyup.enter="doLogin" />
              </el-form-item>
              <el-form-item label="密码">
                <el-input v-model="lf.password" size="large" type="password" show-password
                          placeholder="请输入密码" :prefix-icon="Lock" @keyup.enter="doLogin" />
              </el-form-item>
              <el-button type="primary" size="large" class="submit" :loading="loading"
                         @click="doLogin">登 录</el-button>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="注册" name="reg">
            <el-form :model="rf" label-position="top" @submit.prevent>
              <el-form-item label="用户名（3~24 位字母 / 数字 / 下划线）">
                <el-input v-model="rf.username" size="large" placeholder="如 zhangwei" />
              </el-form-item>
              <el-form-item label="密码（至少 6 位）">
                <el-input v-model="rf.password" size="large" type="password" show-password />
              </el-form-item>
              <el-form-item label="昵称（可选）">
                <el-input v-model="rf.nickname" size="large" placeholder="如 小张" />
              </el-form-item>
              <el-button type="primary" size="large" class="submit" :loading="loading"
                         @click="doRegister">注册并登录</el-button>
            </el-form>
          </el-tab-pane>
        </el-tabs>
      </el-card>

      <el-button text class="guest" @click="router.push('/jobs')">
        先以游客身份逛逛 →
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const tab = ref('login')
const loading = ref(false)
const lf = reactive({ username: '', password: '' })
// 本系统面向求职者，注册界面不再让用户选角色（后端默认 jobseeker）
const rf = reactive({ username: '', password: '', nickname: '' })

function done() {
  ElMessage.success('欢迎，' + (auth.user?.nickname || auth.user?.username))
  router.push((route.query.redirect as string) || '/home')
}

async function doLogin() {
  if (!lf.username || !lf.password) return ElMessage.warning('请填写用户名和密码')
  loading.value = true
  try { await auth.login(lf.username, lf.password); done() } catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}

async function doRegister() {
  if (!rf.username || !rf.password) return ElMessage.warning('请填写用户名和密码')
  loading.value = true
  try {
    await auth.register({ username: rf.username, password: rf.password,
                          nickname: rf.nickname })
    done()
  } catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}
</script>

<style scoped>
/* 整页居中：浅青渐变底 + 顶部光晕，登录卡居中且比例收敛（不再左右分栏） */
.login-wrap {
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  padding: 40px 16px;
  background:
    radial-gradient(760px 380px at 50% -60px, rgba(0, 166, 167, .16), transparent 70%),
    linear-gradient(180deg, #f4fbfb 0%, #e9f5f7 100%);
}
.login-box { width: 100%; max-width: 420px; display: flex; flex-direction: column;
  align-items: center; }

/* 极简品牌头 */
.brand { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
.brand .logo {
  width: 40px; height: 40px; border-radius: 11px; font-size: 21px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #00a6a7, #12c2b4);
  box-shadow: 0 6px 16px rgba(0, 166, 167, .32);
}
.brand .name { font-size: 19px; font-weight: 800; color: #16233a; letter-spacing: .3px; }

/* 卡片：只留一层柔和投影，去掉多余边框，宽度收敛到 420 */
.box {
  width: 100%; border: 1px solid var(--zq-border); border-radius: 16px;
  background: #fff; box-shadow: 0 18px 44px rgba(16, 43, 51, .10);
}
.box :deep(.el-card__body) { padding: 22px 26px 26px; }
.box :deep(.el-tabs__item) { font-size: 15.5px; font-weight: 700; }
.box :deep(.el-tabs__nav-wrap::after) { height: 1px; }
.box :deep(.el-form-item) { margin-bottom: 16px; }
.box :deep(.el-form-item__label) { font-size: 13.5px; color: #5b6b7f; padding-bottom: 4px; }
.submit { width: 100%; height: 42px; font-size: 15.5px; font-weight: 700;
  letter-spacing: 2px; margin-top: 2px; }
.guest { margin-top: 14px; color: #5b6b7f; }

@media (max-width: 480px) {
  .login-wrap { padding: 28px 14px; }
  .box :deep(.el-card__body) { padding: 18px 18px 22px; }
}
</style>
