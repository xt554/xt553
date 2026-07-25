<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import type {
  DepositOrder,
  Page,
  WalletAccount,
  WalletLedgerEntry,
} from '../types'

const activeTab = ref('accounts')
const loading = ref(false)
const accounts = ref<WalletAccount[]>([])
const accountSearch = ref('')
const accountPage = reactive({ current: 1, size: 20, total: 0 })

const deposits = ref<DepositOrder[]>([])
const depositFilters = reactive({ search: '', status: '' })
const depositPage = reactive({ current: 1, size: 20, total: 0 })

const ledgerVisible = ref(false)
const ledgerLoading = ref(false)
const ledger = ref<WalletLedgerEntry[]>([])
const selectedWallet = ref<WalletAccount | null>(null)

const adjustVisible = ref(false)
const adjustLoading = ref(false)
const adjustment = reactive({
  direction: 'CREDIT',
  amount: '',
  reason: '',
})

const entryLabels: Record<string, string> = {
  DEPOSIT: '充值到账',
  ORDER_PAYMENT: '订单支付',
  ORDER_REFUND: '订单退款',
  ADMIN_CREDIT: '人工加款',
  ADMIN_DEBIT: '人工扣款',
}

const depositTag: Record<string, string> = {
  WAIT_PAY: 'warning',
  CONFIRMED: 'success',
  TIMEOUT: 'info',
}

function userLabel(item: WalletAccount | DepositOrder) {
  if (item.telegram_username) return `@${item.telegram_username.replace(/^@/, '')}`
  if (item.username) return item.username
  if (item.telegram_id) return `TG ${item.telegram_id}`
  return item.user_id
}

async function loadAccounts() {
  loading.value = true
  try {
    const { data } = await api.get<Page<WalletAccount>>('/admin/wallet-accounts', {
      params: {
        page: accountPage.current,
        page_size: accountPage.size,
        search: accountSearch.value || undefined,
      },
    })
    accounts.value = data.items
    accountPage.total = data.total
  } finally {
    loading.value = false
  }
}

async function loadDeposits() {
  loading.value = true
  try {
    const { data } = await api.get<Page<DepositOrder>>('/admin/wallet-accounts/deposits', {
      params: {
        page: depositPage.current,
        page_size: depositPage.size,
        search: depositFilters.search || undefined,
        status: depositFilters.status || undefined,
      },
    })
    deposits.value = data.items
    depositPage.total = data.total
  } finally {
    loading.value = false
  }
}

function searchAccounts() {
  accountPage.current = 1
  loadAccounts()
}

function searchDeposits() {
  depositPage.current = 1
  loadDeposits()
}

async function openLedger(wallet: WalletAccount) {
  selectedWallet.value = wallet
  ledgerVisible.value = true
  ledgerLoading.value = true
  try {
    ledger.value = (
      await api.get<WalletLedgerEntry[]>(
        `/admin/wallet-accounts/${wallet.id}/ledger`,
      )
    ).data
  } finally {
    ledgerLoading.value = false
  }
}

function openAdjustment(wallet: WalletAccount, direction: 'CREDIT' | 'DEBIT') {
  selectedWallet.value = wallet
  adjustment.direction = direction
  adjustment.amount = ''
  adjustment.reason = ''
  adjustVisible.value = true
}

async function submitAdjustment() {
  if (!selectedWallet.value || Number(adjustment.amount) <= 0) {
    ElMessage.error('请输入正确的调账金额')
    return
  }
  if (adjustment.reason.trim().length < 3) {
    ElMessage.error('请填写至少 3 个字的调账原因')
    return
  }
  adjustLoading.value = true
  try {
    await api.post(
      `/admin/wallet-accounts/${selectedWallet.value.id}/adjust`,
      adjustment,
    )
    ElMessage.success(
      adjustment.direction === 'CREDIT' ? '余额已增加' : '余额已扣减',
    )
    adjustVisible.value = false
    await loadAccounts()
  } finally {
    adjustLoading.value = false
  }
}

function changeTab(name: string | number) {
  if (name === 'deposits' && deposits.value.length === 0) loadDeposits()
}

onMounted(loadAccounts)
</script>

<template>
  <div>
    <h1 class="page-title">用户钱包</h1>
    <div class="panel">
      <el-tabs v-model="activeTab" @tab-change="changeTab">
        <el-tab-pane label="钱包账户" name="accounts">
          <div class="page-toolbar">
            <el-input
              v-model="accountSearch"
              clearable
              placeholder="Telegram / 用户名 / 邮箱"
              style="width: 280px"
              @keyup.enter="searchAccounts"
            />
            <el-button type="primary" @click="searchAccounts">查询</el-button>
          </div>
          <el-table v-loading="loading" :data="accounts">
            <el-table-column label="用户" min-width="180">
              <template #default="{ row }">{{ userLabel(row) }}</template>
            </el-table-column>
            <el-table-column label="可用余额" min-width="150">
              <template #default="{ row }"><b>{{ row.available_balance }} USDT</b></template>
            </el-table-column>
            <el-table-column label="累计充值" min-width="140">
              <template #default="{ row }">{{ row.total_deposited }} USDT</template>
            </el-table-column>
            <el-table-column label="累计消费" min-width="140">
              <template #default="{ row }">{{ row.total_spent }} USDT</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" min-width="175" />
            <el-table-column label="操作" width="210" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openLedger(row)">明细</el-button>
                <el-button link type="success" @click="openAdjustment(row, 'CREDIT')">加款</el-button>
                <el-button link type="danger" @click="openAdjustment(row, 'DEBIT')">扣款</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination">
            <el-pagination
              v-model:current-page="accountPage.current"
              :page-size="accountPage.size"
              layout="total, prev, pager, next"
              :total="accountPage.total"
              @current-change="loadAccounts"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="充值单" name="deposits">
          <div class="page-toolbar">
            <div class="filters">
              <el-input
                v-model="depositFilters.search"
                clearable
                placeholder="充值单号 / 交易哈希"
                style="width: 280px"
                @keyup.enter="searchDeposits"
              />
              <el-select v-model="depositFilters.status" clearable placeholder="状态" style="width: 140px">
                <el-option label="等待付款" value="WAIT_PAY" />
                <el-option label="已到账" value="CONFIRMED" />
                <el-option label="已超时" value="TIMEOUT" />
              </el-select>
            </div>
            <el-button type="primary" @click="searchDeposits">查询</el-button>
          </div>
          <el-table v-loading="loading" :data="deposits">
            <el-table-column prop="deposit_no" label="充值单号" min-width="190">
              <template #default="{ row }"><span class="mono">{{ row.deposit_no }}</span></template>
            </el-table-column>
            <el-table-column label="用户" min-width="160">
              <template #default="{ row }">{{ userLabel(row) }}</template>
            </el-table-column>
            <el-table-column label="金额" min-width="145">
              <template #default="{ row }">{{ row.payment_amount }} USDT</template>
            </el-table-column>
            <el-table-column prop="network" label="网络" width="90" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="depositTag[row.status]">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="tx_hash" label="交易哈希" min-width="210" show-overflow-tooltip />
            <el-table-column prop="created_at" label="创建时间" min-width="175" />
          </el-table>
          <div class="pagination">
            <el-pagination
              v-model:current-page="depositPage.current"
              :page-size="depositPage.size"
              layout="total, prev, pager, next"
              :total="depositPage.total"
              @current-change="loadDeposits"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-drawer
      v-model="ledgerVisible"
      :title="`余额明细 · ${selectedWallet ? userLabel(selectedWallet) : ''}`"
      size="720px"
    >
      <el-table v-loading="ledgerLoading" :data="ledger">
        <el-table-column prop="created_at" label="时间" min-width="170" />
        <el-table-column label="类型" min-width="120">
          <template #default="{ row }">{{ entryLabels[row.entry_type] || row.entry_type }}</template>
        </el-table-column>
        <el-table-column label="变动" min-width="125">
          <template #default="{ row }">
            <span :style="{ color: Number(row.amount) >= 0 ? '#16a34a' : '#dc2626' }">
              {{ Number(row.amount) > 0 ? '+' : '' }}{{ row.amount }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="balance_after" label="变动后余额" min-width="130" />
        <el-table-column prop="description" label="说明" min-width="190" />
      </el-table>
    </el-drawer>

    <el-dialog
      v-model="adjustVisible"
      :title="adjustment.direction === 'CREDIT' ? '人工加款' : '人工扣款'"
      width="480px"
    >
      <el-alert
        title="所有人工调账都会写入审计日志与钱包流水。"
        type="warning"
        :closable="false"
        style="margin-bottom: 18px"
      />
      <el-form label-width="90px">
        <el-form-item label="用户">{{ selectedWallet ? userLabel(selectedWallet) : '' }}</el-form-item>
        <el-form-item label="当前余额">{{ selectedWallet?.available_balance }} USDT</el-form-item>
        <el-form-item label="金额">
          <el-input v-model="adjustment.amount" type="number" min="0.000001">
            <template #append>USDT</template>
          </el-input>
        </el-form-item>
        <el-form-item label="原因">
          <el-input v-model="adjustment.reason" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustVisible = false">取消</el-button>
        <el-button
          :type="adjustment.direction === 'CREDIT' ? 'success' : 'danger'"
          :loading="adjustLoading"
          @click="submitAdjustment"
        >
          确认{{ adjustment.direction === 'CREDIT' ? '加款' : '扣款' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
