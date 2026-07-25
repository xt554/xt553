<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

interface Setting {
  key: string
  value: unknown
  description: string | null
  is_public: boolean
  updated_at: string
}

const loading = ref(false)
const settings = ref<Setting[]>([])
const dialog = ref(false)
const form = reactive({ key: '', valueText: '', description: '', is_public: false })

async function load() {
  loading.value = true
  try {
    settings.value = (await api.get<Setting[]>('/admin/settings')).data
  } finally {
    loading.value = false
  }
}

function edit(setting?: Setting) {
  Object.assign(form, {
    key: setting?.key || '',
    valueText: setting ? JSON.stringify(setting.value, null, 2) : '""',
    description: setting?.description || '',
    is_public: setting?.is_public || false,
  })
  dialog.value = true
}

async function save() {
  let value: unknown
  try {
    value = JSON.parse(form.valueText)
  } catch {
    ElMessage.error('值必须是合法 JSON，例如 "文本"、123、true 或 {"key":"value"}')
    return
  }
  await api.put(`/admin/settings/${encodeURIComponent(form.key)}`, {
    value,
    description: form.description || null,
    is_public: form.is_public,
  })
  ElMessage.success('配置已保存')
  dialog.value = false
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-toolbar">
      <h1 class="page-title" style="margin: 0">参数配置</h1>
      <el-button type="primary" @click="edit()">新增参数</el-button>
    </div>
    <el-alert title="敏感参数（JWT、API Token、钱包私钥）应保存在环境变量中，不要写入此处。" type="warning" :closable="false" style="margin-bottom: 16px" />
    <div class="panel">
      <el-table v-loading="loading" :data="settings">
        <el-table-column prop="key" label="键" min-width="220" />
        <el-table-column label="值" min-width="320">
          <template #default="{ row }"><span class="mono">{{ JSON.stringify(row.value) }}</span></template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="240" />
        <el-table-column label="公开" width="80">
          <template #default="{ row }"><el-tag :type="row.is_public ? 'warning' : 'info'">{{ row.is_public ? '是' : '否' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="edit(row)">编辑</el-button></template></el-table-column>
      </el-table>
    </div>
    <el-dialog v-model="dialog" title="系统参数" width="620px">
      <el-form label-width="80px">
        <el-form-item label="键"><el-input v-model="form.key" /></el-form-item>
        <el-form-item label="JSON 值"><el-input v-model="form.valueText" type="textarea" :rows="7" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" /></el-form-item>
        <el-form-item label="公开"><el-switch v-model="form.is_public" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>

