<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import type { Wallet } from '../types'

const wallets = ref<Wallet[]>([])
const loading = ref(false)
const dialog = ref(false)
const editing = ref<Wallet | null>(null)
const form = reactive({
  name: '',
  network: 'TRC20',
  address: '',
  token_contract: '',
  token_decimals: 6,
  min_confirmations: 20,
  is_enabled: true,
})

async function load() {
  loading.value = true
  try {
    wallets.value = (await api.get<Wallet[]>('/admin/wallets')).data
  } finally {
    loading.value = false
  }
}

function create() {
  editing.value = null
  Object.assign(form, { name: '', network: 'TRC20', address: '', token_contract: '', token_decimals: 6, min_confirmations: 20, is_enabled: true })
  dialog.value = true
}

function networkChanged(network: string) {
  form.token_decimals = network === 'BEP20' ? 18 : 6
}

function edit(wallet: Wallet) {
  editing.value = wallet
  Object.assign(form, { ...wallet, token_contract: wallet.token_contract || '' })
  dialog.value = true
}

async function save() {
  if (editing.value) {
    await api.patch(`/admin/wallets/${editing.value.id}`, {
      name: form.name,
      token_contract: form.token_contract || null,
      token_decimals: form.token_decimals,
      min_confirmations: form.min_confirmations,
      is_enabled: form.is_enabled,
    })
  } else {
    await api.post('/admin/wallets', { ...form, token_contract: form.token_contract || null })
  }
  ElMessage.success('钱包已保存')
  dialog.value = false
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-toolbar">
      <h1 class="page-title" style="margin: 0">钱包管理</h1>
      <el-button type="primary" @click="create">添加收款钱包</el-button>
    </div>
    <div class="panel">
      <el-table v-loading="loading" :data="wallets">
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column prop="network" label="网络" width="90" />
        <el-table-column label="地址" min-width="300">
          <template #default="{ row }"><span class="mono">{{ row.address }}</span></template>
        </el-table-column>
        <el-table-column prop="min_confirmations" label="确认数" width="90" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><el-tag :type="row.is_enabled ? 'success' : 'info'">{{ row.is_enabled ? '启用' : '停用' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="last_scanned_at" label="最近扫描" min-width="170" />
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="edit(row)">编辑</el-button></template></el-table-column>
      </el-table>
    </div>
    <el-dialog v-model="dialog" :title="editing ? '编辑钱包' : '添加钱包'" width="600px">
      <el-form label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="网络">
          <el-select v-model="form.network" :disabled="Boolean(editing)" style="width: 100%" @change="networkChanged">
            <el-option v-for="item in ['TRC20','BEP20','ERC20']" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="收款地址"><el-input v-model="form.address" :disabled="Boolean(editing)" /></el-form-item>
        <el-form-item label="USDT 合约"><el-input v-model="form.token_contract" /></el-form-item>
        <el-form-item label="Token 精度"><el-input-number v-model="form.token_decimals" :min="0" :max="18" /></el-form-item>
        <el-form-item label="确认数"><el-input-number v-model="form.min_confirmations" :min="1" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.is_enabled" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>
