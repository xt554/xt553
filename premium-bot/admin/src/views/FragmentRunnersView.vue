
<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import type {
  FragmentAccount,
  FragmentJob,
  FragmentRunnerInstance,
  FragmentRunnerSummary,
  Page,
} from '../types'

const loading = ref(false)
const summary = ref<FragmentRunnerSummary>({
  online_runners: 0,
  stale_runners: 0,
  active_accounts: 0,
  login_required_accounts: 0,
  queued_jobs: 0,
  retry_wait_jobs: 0,
  manual_review_jobs: 0,
})
const runners = ref<FragmentRunnerInstance[]>([])
const accounts = ref<FragmentAccount[]>([])
const jobs = ref<FragmentJob[]>([])
const jobPage = reactive({ current: 1, size: 20, total: 0 })
const filters = reactive({ status: '', search: '' })
const accountDialog = ref(false)
const accountForm = reactive({ code: '', display_name: '', profile_name: '', priority: 100, is_enabled: true })
let timer: number | undefined

const statCards = computed(() => [
  ['在线 Runner', summary.value.online_runners],
  ['失联 Runner', summary.value.stale_runners],
  ['可用账号', summary.value.active_accounts],
  ['登录失效', summary.value.login_required_accounts],
  ['等待任务', summary.value.queued_jobs],
  ['退避重试', summary.value.retry_wait_jobs],
])

function tagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (['ONLINE', 'IDLE', 'ACTIVE', 'OK', 'COMPLETED', 'CAPTURED'].includes(status)) return 'success'
  if (['BUSY', 'CLAIMED', 'WAIT_CAPTURE', 'QUEUED', 'RETRY_WAIT'].includes(status)) return 'warning'
  if (['LOGIN_REQUIRED', 'SELECTOR_ERROR', 'ERROR', 'FAILED'].includes(status)) return 'danger'
  return 'info'
}

function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

async function loadJobs() {
  const { data } = await api.get<Page<FragmentJob>>('/admin/fragment-runners/jobs', {
    params: {
      page: jobPage.current,
      page_size: jobPage.size,
      status: filters.status || undefined,
      search: filters.search || undefined,
    },
  })
  jobs.value = data.items
  jobPage.total = data.total
}

async function load() {
  loading.value = true
  try {
    const [summaryRes, runnersRes, accountsRes] = await Promise.all([
      api.get<FragmentRunnerSummary>('/admin/fragment-runners/summary'),
      api.get<FragmentRunnerInstance[]>('/admin/fragment-runners/instances'),
      api.get<FragmentAccount[]>('/admin/fragment-runners/accounts'),
    ])
    summary.value = summaryRes.data
    runners.value = runnersRes.data
    accounts.value = accountsRes.data
    await loadJobs()
  } finally {
    loading.value = false
  }
}

async function saveAccount() {
  await api.post('/admin/fragment-runners/accounts', accountForm)
  ElMessage.success('Fragment 账号已创建')
  accountDialog.value = false
  Object.assign(accountForm, { code: '', display_name: '', profile_name: '', priority: 100, is_enabled: true })
  await load()
}

async function setAccount(account: FragmentAccount, status: string) {
  await api.patch(`/admin/fragment-runners/accounts/${account.id}`, { status })
  ElMessage.success('账号状态已更新')
  await load()
}

async function releaseAccount(account: FragmentAccount) {
  await api.post(`/admin/fragment-runners/accounts/${account.id}/release`)
  ElMessage.success('账号租约已释放')
  await load()
}

async function retryJob(job: FragmentJob) {
  await api.post(`/admin/fragment-runners/jobs/${job.id}/retry`)
  ElMessage.success('任务已重新入队')
  await load()
}

async function downloadArtifact(job: FragmentJob, kind: string) {
  const response = await api.get(`/admin/fragment-runners/jobs/${job.id}/artifacts/${kind}`, { responseType: 'blob' })
  const url = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${job.order_no || job.id}-${kind}`
  anchor.click()
  URL.revokeObjectURL(url)
}

function searchJobs() {
  jobPage.current = 1
  loadJobs()
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 15000)
})
onUnmounted(() => {
  if (timer !== undefined) window.clearInterval(timer)
})
</script>

<template>
  <div v-loading="loading">
    <div class="page-toolbar">
      <h1 class="page-title" style="margin: 0">Fragment Runner</h1>
      <div>
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="accountDialog = true">添加 Fragment 账号</el-button>
      </div>
    </div>

    <div class="stats-grid">
      <div v-for="item in statCards" :key="item[0]" class="stat-card">
        <span class="stat-label">{{ item[0] }}</span>
        <div class="stat-value">{{ item[1] }}</div>
      </div>
    </div>

    <el-tabs>
      <el-tab-pane label="Runner 状态">
        <div class="panel">
          <el-table :data="runners">
            <el-table-column prop="runner_id" label="Runner" min-width="190" />
            <el-table-column label="状态" width="120">
              <template #default="{ row }"><el-tag :type="tagType(row.status)">{{ row.status }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="mode" label="模式" width="100" />
            <el-table-column prop="version" label="版本" width="90" />
            <el-table-column label="浏览器" width="90"><template #default="{ row }">{{ row.browser_healthy ? '正常' : '空闲/异常' }}</template></el-table-column>
            <el-table-column label="登录" width="120"><template #default="{ row }"><el-tag :type="tagType(row.login_status)">{{ row.login_status }}</el-tag></template></el-table-column>
            <el-table-column label="选择器" width="120"><template #default="{ row }"><el-tag :type="tagType(row.selector_status)">{{ row.selector_status }}</el-tag></template></el-table-column>
            <el-table-column prop="current_account_code" label="当前账号" min-width="130" />
            <el-table-column prop="queue_depth" label="队列" width="70" />
            <el-table-column label="心跳" min-width="180"><template #default="{ row }">{{ formatTime(row.last_heartbeat_at) }}</template></el-table-column>
            <el-table-column prop="last_error" label="最近错误" min-width="260" show-overflow-tooltip />
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Fragment 账号">
        <div class="panel">
          <el-table :data="accounts">
            <el-table-column prop="code" label="编码" min-width="140" />
            <el-table-column prop="display_name" label="名称" min-width="150" />
            <el-table-column prop="profile_name" label="浏览器 Profile" min-width="170" />
            <el-table-column label="状态" width="130"><template #default="{ row }"><el-tag :type="tagType(row.status)">{{ row.status }}</el-tag></template></el-table-column>
            <el-table-column label="Cookie 更新" min-width="180"><template #default="{ row }">{{ formatTime(row.cookie_updated_at) }}</template></el-table-column>
            <el-table-column label="选择器" width="110"><template #default="{ row }"><el-tag :type="tagType(row.selector_status)">{{ row.selector_status }}</el-tag></template></el-table-column>
            <el-table-column prop="lease_runner_id" label="租约 Runner" min-width="150" />
            <el-table-column label="租约到期" min-width="180"><template #default="{ row }">{{ formatTime(row.lease_expires_at) }}</template></el-table-column>
            <el-table-column prop="last_error" label="最近错误" min-width="240" show-overflow-tooltip />
            <el-table-column label="操作" width="230" fixed="right">
              <template #default="{ row }">
                <el-button link type="success" @click="setAccount(row, 'ACTIVE')">启用</el-button>
                <el-button link type="warning" @click="setAccount(row, 'PAUSED')">暂停</el-button>
                <el-button link type="primary" @click="releaseAccount(row)">释放租约</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="任务与诊断">
        <div class="panel">
          <div class="page-toolbar">
            <div style="display: flex; gap: 10px">
              <el-input v-model="filters.search" clearable placeholder="订单号/用户名/Runner" style="width: 240px" @keyup.enter="searchJobs" />
              <el-select v-model="filters.status" clearable placeholder="任务状态" style="width: 170px">
                <el-option v-for="item in ['QUEUED','CLAIMED','RETRY_WAIT','LOGIN_REQUIRED','SELECTOR_ERROR','MANUAL_REVIEW','FAILED','COMPLETED']" :key="item" :label="item" :value="item" />
              </el-select>
              <el-button type="primary" @click="searchJobs">查询</el-button>
            </div>
          </div>
          <el-table :data="jobs">
            <el-table-column prop="order_no" label="订单号" min-width="170" />
            <el-table-column prop="target_username" label="Telegram" min-width="130" />
            <el-table-column prop="account_code" label="账号" min-width="120" />
            <el-table-column label="状态" width="140"><template #default="{ row }"><el-tag :type="tagType(row.status)">{{ row.status }}</el-tag></template></el-table-column>
            <el-table-column label="尝试" width="80"><template #default="{ row }">{{ row.attempt_count }}/{{ row.max_attempts }}</template></el-table-column>
            <el-table-column label="下次重试" min-width="180"><template #default="{ row }">{{ formatTime(row.next_retry_at) }}</template></el-table-column>
            <el-table-column prop="failure_kind" label="错误类型" min-width="140" />
            <el-table-column prop="last_error" label="错误详情" min-width="260" show-overflow-tooltip />
            <el-table-column label="诊断" width="220">
              <template #default="{ row }">
                <el-button v-if="row.screenshot_path" link type="primary" @click="downloadArtifact(row, 'screenshot')">截图</el-button>
                <el-button v-if="row.trace_path" link type="primary" @click="downloadArtifact(row, 'trace')">Trace</el-button>
                <el-button v-if="row.html_path" link type="primary" @click="downloadArtifact(row, 'html')">HTML</el-button>
                <el-button v-if="row.console_path" link type="primary" @click="downloadArtifact(row, 'console')">Console</el-button>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="retryJob(row)">重试</el-button></template></el-table-column>
          </el-table>
          <el-pagination v-model:current-page="jobPage.current" :page-size="jobPage.size" :total="jobPage.total" layout="prev, pager, next, total" @current-change="loadJobs" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="accountDialog" title="添加 Fragment 账号" width="560px">
      <el-form label-width="120px">
        <el-form-item label="账号编码"><el-input v-model="accountForm.code" placeholder="fragment-02" /></el-form-item>
        <el-form-item label="显示名称"><el-input v-model="accountForm.display_name" placeholder="Fragment 账号 2" /></el-form-item>
        <el-form-item label="Profile 名称"><el-input v-model="accountForm.profile_name" placeholder="fragment-02" /></el-form-item>
        <el-form-item label="优先级"><el-input-number v-model="accountForm.priority" :min="0" :max="10000" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="accountForm.is_enabled" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="accountDialog = false">取消</el-button><el-button type="primary" @click="saveAccount">保存</el-button></template>
    </el-dialog>
  </div>
</template>
