<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

interface Stats {
  total_users: number
  total_orders: number
  today_orders: number
  paid_revenue: string
  wallet_liability: string
  status_counts: Record<string, number>
}

const loading = ref(true)
const stats = ref<Stats>({
  total_users: 0,
  total_orders: 0,
  today_orders: 0,
  paid_revenue: '0',
  wallet_liability: '0',
  status_counts: {},
})

const statusNames: Record<string, string> = {
  WAIT_PAY: '等待付款',
  PAID: '已付款',
  PROCESSING: '处理中',
  SUCCESS: '成功',
  FAILED: '失败',
  TIMEOUT: '超时',
}

async function load() {
  loading.value = true
  try {
    stats.value = (await api.get('/admin/stats')).data
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <h1 class="page-title">数据概览</h1>
    <div class="stats-grid">
      <div class="stat-card">
        <span class="stat-label">累计用户</span>
        <div class="stat-value">{{ stats.total_users }}</div>
      </div>
      <div class="stat-card">
        <span class="stat-label">累计订单</span>
        <div class="stat-value">{{ stats.total_orders }}</div>
      </div>
      <div class="stat-card">
        <span class="stat-label">今日订单</span>
        <div class="stat-value">{{ stats.today_orders }}</div>
      </div>
      <div class="stat-card">
        <span class="stat-label">成功订单收益</span>
        <div class="stat-value">{{ stats.paid_revenue }} <small>USDT</small></div>
      </div>
      <div class="stat-card">
        <span class="stat-label">用户钱包余额</span>
        <div class="stat-value">{{ stats.wallet_liability }} <small>USDT</small></div>
      </div>
    </div>
    <div class="panel">
      <div class="page-toolbar">
        <h3 style="margin: 0">订单状态分布</h3>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </div>
      <div class="status-grid">
        <div v-for="(label, key) in statusNames" :key="key" class="status-item">
          <span class="muted">{{ label }}</span>
          <span class="status-count">{{ stats.status_counts[key] || 0 }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
