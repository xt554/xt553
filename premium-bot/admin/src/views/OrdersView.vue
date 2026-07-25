<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import type { Order, Page } from '../types'

const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const selected = ref<Order | null>(null)
const orders = ref<Order[]>([])
const filters = reactive({ search: '', status: '', network: '' })
const page = reactive({ current: 1, size: 20, total: 0 })

const statusType: Record<string, string> = {
  WAIT_PAY: 'warning',
  PAID: 'primary',
  PROCESSING: 'primary',
  WAIT_FRAGMENT: 'primary',
  WAIT_SIGN: 'warning',
  BROADCASTED: 'primary',
  CONFIRMING: 'primary',
  COMPLETED: 'success',
  SUCCESS: 'success',
  FAILED: 'danger',
  REFUNDED: 'info',
  MANUAL_REVIEW: 'warning',
  TIMEOUT: 'info',
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get<Page<Order>>('/admin/orders', {
      params: {
        page: page.current,
        page_size: page.size,
        search: filters.search || undefined,
        status: filters.status || undefined,
        network: filters.network || undefined,
      },
    })
    orders.value = data.items
    page.total = data.total
  } finally {
    loading.value = false
  }
}

function filterNow() {
  page.current = 1
  load()
}

async function openDetail(order: Order) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    selected.value = (await api.get<Order>(`/admin/orders/${order.id}`)).data
  } finally {
    detailLoading.value = false
  }
}

async function retry(order: Order) {
  await ElMessageBox.confirm('确定重新执行该订单的 Premium 发放？', '重试订单', { type: 'warning' })
  await api.post(`/admin/orders/${order.id}/retry`)
  ElMessage.success('已加入处理队列')
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="page-title">订单管理</h1>
    <div class="panel">
      <div class="page-toolbar">
        <div class="filters">
          <el-input v-model="filters.search" clearable placeholder="订单号 / Telegram" style="width: 240px" @keyup.enter="filterNow" />
          <el-select v-model="filters.status" clearable placeholder="订单状态" style="width: 140px">
            <el-option v-for="item in ['WAIT_PAY','PAID','PROCESSING','WAIT_FRAGMENT','WAIT_SIGN','BROADCASTED','CONFIRMING','COMPLETED','FAILED','REFUNDED','MANUAL_REVIEW','TIMEOUT']" :key="item" :label="item" :value="item" />
          </el-select>
          <el-select v-model="filters.network" clearable placeholder="网络" style="width: 120px">
            <el-option v-for="item in ['TRC20','BEP20','ERC20']" :key="item" :label="item" :value="item" />
          </el-select>
        </div>
        <el-button type="primary" @click="filterNow">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="orders">
        <el-table-column prop="order_no" label="订单号" min-width="165">
          <template #default="{ row }"><span class="mono">{{ row.order_no }}</span></template>
        </el-table-column>
        <el-table-column prop="target_username" label="Telegram" min-width="140" />
        <el-table-column label="套餐" min-width="150">
          <template #default="{ row }">{{ row.plan.name }}</template>
        </el-table-column>
        <el-table-column label="实付金额" min-width="130">
          <template #default="{ row }">{{ row.payment_amount }} USDT</template>
        </el-table-column>
        <el-table-column label="支付方式" min-width="120">
          <template #default="{ row }">{{ row.payment_method === 'WALLET_BALANCE' ? '钱包余额' : '链上支付' }}</template>
        </el-table-column>
        <el-table-column prop="network" label="网络" width="90" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType[row.status]">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="170" />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button v-if="['FAILED','REFUNDED','MANUAL_REVIEW'].includes(row.status)" link type="warning" @click="retry(row)">重试</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination
          v-model:current-page="page.current"
          :page-size="page.size"
          layout="total, prev, pager, next"
          :total="page.total"
          @current-change="load"
        />
      </div>
    </div>

    <el-drawer v-model="detailVisible" title="订单详情" size="620px">
      <div v-loading="detailLoading">
        <template v-if="selected">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="订单号">{{ selected.order_no }}</el-descriptions-item>
            <el-descriptions-item label="状态"><el-tag :type="statusType[selected.status]">{{ selected.status }}</el-tag></el-descriptions-item>
            <el-descriptions-item label="Telegram">{{ selected.target_username }}</el-descriptions-item>
            <el-descriptions-item label="套餐">{{ selected.plan.name }}</el-descriptions-item>
            <el-descriptions-item label="支付方式">{{ selected.payment_method === 'WALLET_BALANCE' ? '钱包余额' : 'USDT 链上支付' }}</el-descriptions-item>
            <el-descriptions-item label="金额">{{ selected.payment_amount }} USDT ({{ selected.network }})</el-descriptions-item>
            <el-descriptions-item label="收款地址"><span class="mono">{{ selected.payment_address }}</span></el-descriptions-item>
            <el-descriptions-item label="交易哈希"><span class="mono">{{ selected.tx_hash || '-' }}</span></el-descriptions-item>
            <el-descriptions-item label="发放参考号">{{ selected.premium_reference || '-' }}</el-descriptions-item>
            <el-descriptions-item label="失败原因">{{ selected.failure_reason || '-' }}</el-descriptions-item>
          </el-descriptions>
          <h3>状态记录</h3>
          <el-timeline>
            <el-timeline-item v-for="item in selected.history" :key="item.created_at" :timestamp="item.created_at">
              {{ item.from_status || 'NEW' }} → {{ item.to_status }}
              <div class="muted">{{ item.reason }}</div>
            </el-timeline-item>
          </el-timeline>
        </template>
      </div>
    </el-drawer>
  </div>
</template>
