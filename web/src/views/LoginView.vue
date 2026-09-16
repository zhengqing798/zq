<template>
  <div class="login-wrap">
    <!-- 左：品牌区（招聘网站的"登录页左栏"） -->
    <div class="login-left">
      <div class="logo-big">🎯</div>
      <h1>人岗匹配推荐系统</h1>
      <p class="slogan">8,836 个真实岗位 · 六维匹配打分 · 全部结论可溯源</p>
      <ul class="feat">
        <li>📄 粘贴或上传 PDF 简历，自动结构化解析</li>
        <li>🎯 六维加权匹配（技能 / 经验 / 学历 / 地域 / 薪资 / 证书）</li>
        <li>🏢 K-Means 岗位聚类画像与降维可视化</li>
        <li>💬 Agent 智能问答，答案带来源与工具轨迹</li>
      </ul>
      <div class="tip">游客也能体验全部核心功能；登录后可保存简历、收藏岗位、查看历史。</div>
    </div>

    <!-- 右：登录 / 注册 -->
    <div class="login-right">
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
              <el-button type="primary" size="large" style="width:100%" :loading="loading"
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
              <el-form-item label="角色">
                <el-radio-group v-model="rf.role">
                  <el-radio-button value="jobseeker">求职者</el-radio-button>
                  <el-radio-button value="employer">企业（预留）</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-button type="primary" size="large" style="width:100%" :loading="loading"
                         @click="doRegister">注册并登录</el-button>
            </el-form>
          </el-tab-pane>
        </el-tabs>
        <div class="muted" style="margin-top:10px;text-align:center">
          口令以 PBKDF2-HMAC-SHA256（20 万次迭代 + 随机盐）存储，不保存明文
        </div>
      </el-card>
      <el-button text @click="router.push('/jobs')" style="margin-top:8px">
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
const rf = reactive({ username: '', password: '', nickname: '', role: 'jobseeker' })

function done() {
  ElMessage.success('欢迎，' + (auth.user?.nickname || auth.user?.username))
  router.push((route.query.redirect as string) || '/jobs')
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
                          nickname: rf.nickname, role: rf.role })
    done()
  } catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh; display: grid; grid-template-columns: 1.15fr .85fr;
  background: linear-gradient(135deg, #00a6a7 0%, #12c2b4 45%, #43d6c4 100%);
}
.login-left { color: #fff; padding: 8vh 6vw; }
.logo-big { font-size: 46px; }
.login-left h1 { font-size: 32px; margin: 10px 0 6px; font-weight: 800; }
.slogan { font-size: 15px; opacity: .92; margin-bottom: 26px; }
.feat { list-style: none; padding: 0; line-height: 2.15; font-size: 15px; }
.feat li { opacity: .96; }
.tip { margin-top: 26px; font-size: 13px; opacity: .85;
  background: rgba(255,255,255,.14); padding: 10px 14px; border-radius: 10px; }
.login-right { display: flex; flex-direction: column; align-items: center;
  justify-content: center; background: #fff; padding: 24px; }
.box { width: 380px; border: none; }
@media (max-width: 900px) {
  .login-wrap { grid-template-columns: 1fr; }
  .login-left { padding: 6vh 8vw 2vh; }
}
</style>
