<script setup lang="ts">
import { reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useRouter } from 'vue-router'
import { auth } from '../auth'

const router = useRouter()
const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ username: 'admin', password: '' })
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, min: 8, message: '密码至少 8 位', trigger: 'blur' }],
}

async function submit() {
  if (!await formRef.value?.validate()) return
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    await router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-form ref="formRef" :model="form" :rules="rules" class="login-card" @keyup.enter="submit">
      <h1 class="login-title">Premium Bot</h1>
      <p class="login-subtitle">管理控制台</p>
      <el-form-item prop="username">
        <el-input v-model="form.username" size="large" placeholder="用户名">
          <template #prefix><el-icon><User /></el-icon></template>
        </el-input>
      </el-form-item>
      <el-form-item prop="password">
        <el-input v-model="form.password" type="password" size="large" show-password placeholder="密码">
          <template #prefix><el-icon><Lock /></el-icon></template>
        </el-input>
      </el-form-item>
      <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="submit">
        登录
      </el-button>
    </el-form>
  </div>
</template>

