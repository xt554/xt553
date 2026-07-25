<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { api } from '../api'
import type { Page, User } from '../types'

const loading = ref(false)
const search = ref('')
const page = reactive({ current: 1, size: 20, total: 0 })
const users = ref<User[]>([])

async function load() {
  loading.value = true
  try {
    const { data } = await api.get<Page<User>>('/admin/users', {
      params: { page: page.current, page_size: page.size, search: search.value || undefined },
    })
    users.value = data.items
    page.total = data.total
  } finally {
    loading.value = false
  }
}

async function toggle(user: User) {
  const action = user.is_active ? '禁用' : '启用'
  await ElMessageBox.confirm(`确定${action}该用户？`, '确认操作', { type: 'warning' })
  await api.patch(`/admin/users/${user.id}`, { is_active: !user.is_active })
  await load()
}

function searchNow() {
  page.current = 1
  load()
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="page-title">用户管理</h1>
    <div class="panel">
      <div class="page-toolbar">
        <el-input v-model="search" clearable placeholder="用户名 / Telegram / 邮箱" style="width: 300px" @keyup.enter="searchNow" />
        <el-button type="primary" @click="searchNow">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="users">
        <el-table-column prop="id" label="用户 ID" min-width="210" />
        <el-table-column label="Telegram" min-width="160">
          <template #default="{ row }">{{ row.telegram_username || row.telegram_id || '-' }}</template>
        </el-table-column>
        <el-table-column prop="username" label="后台用户名" min-width="130" />
        <el-table-column prop="role" label="角色" width="90" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">{{ row.is_active ? '正常' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" min-width="170" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link :type="row.is_active ? 'danger' : 'success'" @click="toggle(row)">
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination
          v-model:current-page="page.current"
          v-model:page-size="page.size"
          layout="total, prev, pager, next"
          :total="page.total"
          @current-change="load"
        />
      </div>
    </div>
  </div>
</template>

