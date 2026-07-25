<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import type { Page } from '../types'

interface AuditLog {
  id: number
  actor_id: string | null
  action: string
  target_type: string | null
  target_id: string | null
  details: Record<string, unknown> | null
  ip_address: string | null
  created_at: string
}

const loading = ref(false)
const action = ref('')
const logs = ref<AuditLog[]>([])
const page = reactive({ current: 1, size: 30, total: 0 })

async function load() {
  loading.value = true
  try {
    const { data } = await api.get<Page<AuditLog>>('/admin/logs', {
      params: { page: page.current, page_size: page.size, action: action.value || undefined },
    })
    logs.value = data.items
    page.total = data.total
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="page-title">系统日志</h1>
    <div class="panel">
      <div class="page-toolbar">
        <el-input v-model="action" clearable placeholder="按操作名称筛选" style="width: 280px" @keyup.enter="load" />
        <el-button type="primary" @click="load">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="logs">
        <el-table-column prop="created_at" label="时间" min-width="180" />
        <el-table-column prop="action" label="操作" min-width="160" />
        <el-table-column prop="actor_id" label="操作者" min-width="210" />
        <el-table-column label="对象" min-width="220">
          <template #default="{ row }">{{ row.target_type || '-' }} / {{ row.target_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="详情" min-width="280">
          <template #default="{ row }"><span class="mono">{{ row.details ? JSON.stringify(row.details) : '-' }}</span></template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination v-model:current-page="page.current" :page-size="page.size" layout="total, prev, pager, next" :total="page.total" @current-change="load" />
      </div>
    </div>
  </div>
</template>

