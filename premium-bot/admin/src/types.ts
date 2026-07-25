export interface Plan {
  id: string
  code: string
  name: string
  months: number
  price: string
  currency: string
  is_active: boolean
  sort_order: number
  created_at: string
}

export interface User {
  id: string
  telegram_id: number | null
  telegram_username: string | null
  username: string | null
  email: string | null
  role: string
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

export interface Order {
  id: string
  order_no: string
  user_id: string
  target_username: string
  status: string
  payment_method: 'ONCHAIN' | 'WALLET_BALANCE'
  network: string
  currency: string
  quoted_amount: string
  payment_amount: string
  payment_address: string
  tx_hash: string | null
  expires_at: string
  paid_at: string | null
  processing_at: string | null
  completed_at: string | null
  failure_reason: string | null
  premium_reference: string | null
  balance_payment_attempt: number
  balance_refunded_at: string | null
  fulfillment_attempts: number
  last_fulfillment_error: string | null
  next_retry_at: string | null
  manual_review_at: string | null
  created_at: string
  updated_at: string
  plan: Plan
  history?: Array<{
    from_status: string | null
    to_status: string
    reason: string | null
    actor_type: string
    created_at: string
  }>
  payments?: Array<{
    network: string
    tx_hash: string
    amount: string
    confirmations: number
    status: string
  }>
}

export interface Wallet {
  id: string
  name: string
  network: string
  address: string
  token_contract: string | null
  token_decimals: number
  min_confirmations: number
  is_enabled: boolean
  last_scanned_block: number | null
  last_scanned_at: string | null
  created_at: string
}

export interface WalletAccount {
  id: string
  user_id: string
  telegram_id: number | null
  telegram_username: string | null
  username: string | null
  currency: string
  available_balance: string
  total_deposited: string
  total_spent: string
  created_at: string
  updated_at: string
}

export interface WalletLedgerEntry {
  id: string
  entry_type: string
  amount: string
  balance_after: string
  reference_type: string
  reference_id: string
  description: string | null
  created_at: string
}

export interface DepositOrder {
  id: string
  deposit_no: string
  user_id: string
  telegram_id: number | null
  telegram_username: string | null
  username: string | null
  network: string
  currency: string
  requested_amount: string
  payment_amount: string
  payment_address: string
  status: 'WAIT_PAY' | 'CONFIRMED' | 'TIMEOUT'
  tx_hash: string | null
  expires_at: string
  confirmed_at: string | null
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}


export interface FragmentRunnerSummary {
  online_runners: number
  stale_runners: number
  active_accounts: number
  login_required_accounts: number
  queued_jobs: number
  retry_wait_jobs: number
  manual_review_jobs: number
}

export interface FragmentRunnerInstance {
  runner_id: string
  status: string
  mode: string
  version: string
  browser_healthy: boolean
  api_healthy: boolean
  fragment_reachable: boolean
  login_status: string
  selector_status: string
  current_job_id: string | null
  current_account_code: string | null
  queue_depth: number
  page_url: string | null
  last_heartbeat_at: string
  last_claim_at: string | null
  last_success_at: string | null
  last_error_at: string | null
  last_error: string | null
  runtime_metadata: Record<string, unknown> | null
}

export interface FragmentAccount {
  id: string
  code: string
  display_name: string
  profile_name: string
  status: string
  priority: number
  is_enabled: boolean
  lease_runner_id: string | null
  lease_job_id: string | null
  lease_expires_at: string | null
  last_login_at: string | null
  last_success_at: string | null
  last_failure_at: string | null
  cookie_updated_at: string | null
  selector_checked_at: string | null
  selector_status: string
  last_page_url: string | null
  last_error: string | null
}

export interface FragmentJob {
  id: string
  order_id: string
  order_no: string | null
  target_username: string | null
  account_id: string | null
  account_code: string | null
  status: string
  runner_id: string | null
  wallet_code: string | null
  profile_name: string | null
  attempt_count: number
  max_attempts: number
  next_retry_at: string | null
  retry_delay_seconds: number | null
  failure_kind: string | null
  lease_expires_at: string | null
  started_at: string | null
  captured_at: string | null
  finished_at: string | null
  page_url: string | null
  screenshot_path: string | null
  trace_path: string | null
  html_path: string | null
  console_path: string | null
  last_error: string | null
  created_at: string
  updated_at: string
}
