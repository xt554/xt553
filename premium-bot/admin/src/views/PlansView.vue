<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import type { Plan } from '../types'

const loading = ref(false)
const dialog = ref(false)
const editing = ref<Plan | null>(null)
const plans = ref<Plan[]>([])
const form = reactive({
  code: '',
  name: '',
  months: 3,
  price: 29,
  currency: 'USDT',
  sort_order: 0,
  is_active: true,
})

async function load() {
  loading.value = true
  try {
    plans.value = (await api.get<Plan[]>('/admin/plans')).data
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, { code: '', name: '', months: 3, price: 29, currency: 'USDT', sort_order: 0, is_active: true })
  dialog.value = true
}

function openEdit(plan: Plan) {
  editing.value = plan
  Object.assign(form, { ...plan, price: Number(plan.price) })
  dialog.value = true
}

async function save() {
  if (editing.value) {
    await api.patch(`/admin/plans/${editing.value.id}`, {
      name: form.name,
      price: form.price,
      sort_order: form.sort_order,
      is_active: form.is_active,
    })
  } else {
    await api.post('/admin/plans', form)
  }
  ElMessage.success('套餐已保存')
  dialog.value = false
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-toolbar">
      <h1 class="page-title" style="margin: 0">套餐管理</h1>
      <el-button type="primary" @click="openCreate">新增套餐</el-button>
    </div>
    <div class="panel">
      <el-table v-loading="loading" :data="plans">
        <el-table-column prop="code" label="代码" min-width="150" />
        <el-table-column prop="name" label="名称" min-width="200" />
        <el-table-column prop="months" label="月数" width="90" />
        <el-table-column label="价格" width="130">
          <template #default="{ row }">{{ row.price }} {{ row.currency }}</template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="80" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '下架' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }"><el-button link type="primary" @click="openEdit(row)">编辑</el-button></template>
        </el-table-column>
      </el-table>
    </div>
    <el-dialog v-model="dialog" :title="editing ? '编辑套餐' : '新增套餐'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="代码"><el-input v-model="form.code" :disabled="Boolean(editing)" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="月数"><el-input-number v-model="form.months" :disabled="Boolean(editing)" :min="1" /></el-form-item>
        <el-form-item label="价格"><el-input-number v-model="form.price" :precision="2" :min="0.01" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="form.sort_order" /></el-form-item>
        <el-form-item label="状态"><el-switch v-model="form.is_active" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>

