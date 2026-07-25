<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { auth } from '../auth'

const route = useRoute()
const router = useRouter()
const collapsed = ref(false)
const passwordDialog = ref(false)
const passwordLoading = ref(false)
const passwordForm = reactive({
  current_password: '',
  new_password: '',
  confirm_password: '',
})

const items = [
  { path: '/', title: '数据概览', icon: 'DataAnalysis' },
  { path: '/orders', title: '订单管理', icon: 'Tickets' },
  { path: '/users', title: '用户管理', icon: 'User' },
  { path: '/wallet-accounts', title: '用户钱包', icon: 'Coin' },
  { path: '/plans', title: '套餐管理', icon: 'Goods' },
  { path: '/wallets', title: '收款钱包', icon: 'Wallet' },
  { path: '/fragment-runners', title: 'Fragment Runner', icon: 'Monitor' },
  { path: '/logs', title: '系统日志', icon: 'Document' },
  { path: '/settings', title: '参数配置', icon: 'Setting' },
]

onMounted(async () => {
  if (!auth.state.user) {
    try {
      await auth.me()
    } catch {
      // The API interceptor redirects expired sessions.
    }
  }
})

function logout() {
  auth.logout()
  router.push('/login')
}

async function changePassword() {
  if (passwordForm.new_password.length < 12) {
    ElMessage.error('新密码至少 12 位')
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.error('两次输入的新密码不一致')
    return
  }
  passwordLoading.value = true
  try {
    await api.post('/auth/change-password', {
      current_password: passwordForm.current_password,
      new_password: passwordForm.new_password,
    })
    ElMessage.success('密码已更新，请重新登录')
    passwordDialog.value = false
    logout()
  } finally {
    passwordLoading.value = false
  }
}
</script>

<template>
  <div class="admin-shell">
    <aside class="sidebar" :class="{ collapsed }">
      <div class="brand">
        <span class="brand-mark">P</span>
        <span v-if="!collapsed">Premium Admin</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        :collapse="collapsed"
        background-color="transparent"
        text-color="#aeb8cc"
        active-text-color="#ffffff"
      >
        <el-menu-item v-for="item in items" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>
    </aside>
    <section class="main-column">
      <header class="topbar">
        <el-button text circle @click="collapsed = !collapsed">
          <el-icon><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
        </el-button>
        <div class="topbar-user">
          <span>{{ auth.state.user?.username || '管理员' }}</span>
          <el-button text type="primary" @click="passwordDialog = true">修改密码</el-button>
          <el-button text type="danger" @click="logout">退出登录</el-button>
        </div>
      </header>
      <main class="content"><router-view /></main>
    </section>
    <el-dialog v-model="passwordDialog" title="修改密码" width="460px">
      <el-form label-width="90px">
        <el-form-item label="当前密码">
          <el-input v-model="passwordForm.current_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="passwordForm.confirm_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialog = false">取消</el-button>
        <el-button type="primary" :loading="passwordLoading" @click="changePassword">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
