from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORMModel):
    id: str
    telegram_id: int | None
    telegram_username: str | None
    username: str | None
    email: str | None
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserUpdate(BaseModel):
    is_active: bool


class TelegramUserUpsert(BaseModel):
    telegram_id: int
    telegram_username: str | None = Field(default=None, max_length=64)


class PlanOut(ORMModel):
    id: str
    code: str
    name: str
    months: int
    price: Decimal
    currency: str
    is_active: bool
    sort_order: int
    created_at: datetime


class PlanCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_]{3,32}$")
    name: str = Field(min_length=2, max_length=128)
    months: int = Field(ge=1, le=120)
    price: Decimal = Field(gt=0, decimal_places=6)
    currency: str = Field(default="USDT", max_length=16)
    is_active: bool = True
    sort_order: int = 0


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    price: Decimal | None = Field(default=None, gt=0, decimal_places=6)
    is_active: bool | None = None
    sort_order: int | None = None


class WalletOut(ORMModel):
    id: str
    name: str
    network: str
    address: str
    token_contract: str | None
    token_decimals: int
    min_confirmations: int
    is_enabled: bool
    last_scanned_block: int | None
    last_scanned_at: datetime | None
    created_at: datetime


class WalletCreate(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    network: str
    address: str = Field(min_length=20, max_length=128)
    token_contract: str | None = Field(default=None, max_length=128)
    token_decimals: int = Field(default=6, ge=0, le=18)
    min_confirmations: int = Field(default=20, ge=1, le=1000)
    is_enabled: bool = True


class WalletUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    token_contract: str | None = Field(default=None, max_length=128)
    token_decimals: int | None = Field(default=None, ge=0, le=18)
    min_confirmations: int | None = Field(default=None, ge=1, le=1000)
    is_enabled: bool | None = None


class OrderCreateInternal(BaseModel):
    telegram_id: int
    plan_id: str
    target_username: str
    network: str | None = None
    payment_method: str = "ONCHAIN"
    callback_url: HttpUrl | None = None


class OrderOut(ORMModel):
    id: str
    order_no: str
    user_id: str
    target_username: str
    status: str
    payment_method: str
    network: str
    currency: str
    quoted_amount: Decimal
    payment_amount: Decimal
    payment_address: str
    tx_hash: str | None
    expires_at: datetime
    paid_at: datetime | None
    processing_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None
    premium_reference: str | None
    balance_payment_attempt: int
    balance_refunded_at: datetime | None
    fulfillment_attempts: int
    last_fulfillment_error: str | None
    next_retry_at: datetime | None
    manual_review_at: datetime | None
    created_at: datetime
    updated_at: datetime
    plan: PlanOut


class OrderStatusHistoryOut(ORMModel):
    from_status: str | None
    to_status: str
    reason: str | None
    actor_type: str
    created_at: datetime


class PaymentOut(ORMModel):
    network: str
    tx_hash: str
    from_address: str | None
    to_address: str
    amount: Decimal
    confirmations: int
    status: str
    block_number: int | None
    block_time: datetime | None


class OrderDetail(OrderOut):
    history: list[OrderStatusHistoryOut] = []
    payments: list[PaymentOut] = []


class NetworkOut(BaseModel):
    code: str
    label: str


class UserWalletOut(ORMModel):
    id: str
    user_id: str
    currency: str
    available_balance: Decimal
    total_deposited: Decimal
    total_spent: Decimal
    created_at: datetime
    updated_at: datetime


class WalletLedgerEntryOut(ORMModel):
    id: str
    entry_type: str
    amount: Decimal
    balance_after: Decimal
    reference_type: str
    reference_id: str
    description: str | None
    created_at: datetime


class DepositCreateInternal(BaseModel):
    telegram_id: int
    amount: Decimal = Field(gt=0, decimal_places=6)
    network: str


class DepositOrderOut(ORMModel):
    id: str
    deposit_no: str
    user_id: str
    user_wallet_id: str
    network: str
    currency: str
    requested_amount: Decimal
    payment_amount: Decimal
    payment_address: str
    status: str
    tx_hash: str | None
    expires_at: datetime
    confirmed_at: datetime | None
    created_at: datetime


class DepositOrderAdminOut(DepositOrderOut):
    telegram_id: int | None
    telegram_username: str | None
    username: str | None


class WalletAccountAdminOut(UserWalletOut):
    telegram_id: int | None
    telegram_username: str | None
    username: str | None


class WalletAdjustment(BaseModel):
    direction: str = Field(pattern=r"^(CREDIT|DEBIT)$")
    amount: Decimal = Field(gt=0, decimal_places=6)
    reason: str = Field(min_length=3, max_length=500)


class PaymentWebhook(BaseModel):
    network: str
    tx_hash: str
    to_address: str
    amount: Decimal
    confirmations: int = Field(ge=0)
    log_index: int = 0
    block_number: int | None = None
    block_time: datetime | None = None
    from_address: str | None = None
    token_contract: str | None = None
    raw_data: dict[str, Any] | None = None


class PremiumWebhook(BaseModel):
    reference: str
    status: str
    message: str = ""


class SettingOut(ORMModel):
    key: str
    value: Any
    description: str | None
    is_public: bool
    updated_at: datetime


class SettingUpdate(BaseModel):
    value: Any
    description: str | None = Field(default=None, max_length=500)
    is_public: bool = False


class AuditLogOut(ORMModel):
    id: int
    actor_id: str | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime


class RefundRequest(BaseModel):
    destination_address: str = Field(min_length=20, max_length=128)
    amount: Decimal | None = Field(default=None, gt=0, decimal_places=6)


class RefundOut(ORMModel):
    id: str
    order_id: str
    destination_address: str
    network: str
    amount: Decimal
    status: str
    provider_reference: str | None
    tx_hash: str | None
    failure_reason: str | None
    created_at: datetime


class DashboardStats(BaseModel):
    total_users: int
    total_orders: int
    today_orders: int
    paid_revenue: Decimal
    wallet_liability: Decimal
    status_counts: dict[str, int]


class Page(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int

class FragmentCaptureIn(BaseModel):
    order_id: str = Field(min_length=36, max_length=36)
    request: dict[str, Any]
    expected_amount_nano: int = Field(gt=0)


class FragmentCaptureOut(BaseModel):
    transaction_id: str
    wallet_code: str
    status: str
    external_message_hash: str | None = None
    broadcasted: bool = False
    signer_mode: str | None = None


class TonHotWalletOut(ORMModel):
    id: str
    wallet_code: str
    address: str
    wallet_version: str
    status: str
    priority: int
    balance_nano: int
    reserved_nano: int
    single_limit_nano: int
    daily_limit_nano: int
    daily_spent_nano: int
    minimum_balance_nano: int
    target_balance_nano: int
    maximum_balance_nano: int
    consecutive_failure_count: int
    last_seqno: int | None
    last_used_at: datetime | None
    disabled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TonHotWalletCreate(BaseModel):
    wallet_code: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,32}$")
    address: str = Field(min_length=16, max_length=128)
    wallet_version: str = Field(default="v4r2", max_length=32)
    priority: int = Field(default=100, ge=0, le=10_000)
    balance_nano: int = Field(default=0, ge=0)
    single_limit_nano: int = Field(gt=0)
    daily_limit_nano: int = Field(gt=0)
    minimum_balance_nano: int = Field(default=0, ge=0)
    target_balance_nano: int = Field(default=0, ge=0)
    maximum_balance_nano: int = Field(default=0, ge=0)


class TonHotWalletUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=24)
    priority: int | None = Field(default=None, ge=0, le=10_000)
    single_limit_nano: int | None = Field(default=None, gt=0)
    daily_limit_nano: int | None = Field(default=None, gt=0)
    minimum_balance_nano: int | None = Field(default=None, ge=0)
    target_balance_nano: int | None = Field(default=None, ge=0)
    maximum_balance_nano: int | None = Field(default=None, ge=0)


class TonHotWalletBalanceUpdate(BaseModel):
    balance_nano: int = Field(ge=0)
    last_seqno: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=3, max_length=255)


class TonWhitelistOut(ORMModel):
    id: str
    destination: str
    label: str | None
    enabled: bool
    maximum_single_nano: int | None
    valid_from: datetime | None
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime


class TonWhitelistCreate(BaseModel):
    destination: str = Field(min_length=16, max_length=128)
    label: str | None = Field(default=None, max_length=128)
    enabled: bool = True
    maximum_single_nano: int | None = Field(default=None, gt=0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class TonWhitelistUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None
    maximum_single_nano: int | None = Field(default=None, gt=0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class TonTransactionOut(ORMModel):
    id: str
    order_id: str
    wallet_id: str
    request_id: str
    idempotency_key: str
    seqno: int | None
    valid_until: int | None
    source_address: str | None
    destination: str
    amount_nano: int
    payload_hash: str | None
    capture_fingerprint: str | None
    signer_request_id: str | None
    signer_mode: str | None
    attempt_count: int
    last_error: str | None
    external_message_hash: str | None
    tx_hash: str | None
    tx_lt: str | None
    status: str
    broadcast_at: datetime | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TonReservationOut(ORMModel):
    id: str
    order_id: str
    wallet_id: str
    reserved_nano: int
    status: str
    expires_at: datetime
    released_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CircuitBreakerOut(ORMModel):
    breaker_key: str
    state: str
    failure_count: int
    opened_at: datetime | None
    cooldown_until: datetime | None
    reason: str | None
    created_at: datetime
    updated_at: datetime


class TonSchemaOut(ORMModel):
    schema_hash: str
    enabled: bool
    sample_count: int
    first_destination: str | None
    last_destination: str | None
    last_payload_hash: str | None
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TonSchemaUpdate(BaseModel):
    enabled: bool


class FragmentRunnerClaimIn(BaseModel):
    runner_id: str = Field(min_length=3, max_length=64)


class FragmentRunnerJobOut(BaseModel):
    id: str
    order_id: str
    order_no: str
    target_username: str
    months: int
    wallet_code: str | None = None
    account_code: str
    account_display_name: str
    profile_name: str
    status: str
    attempt_count: int
    max_attempts: int


class FragmentRunnerHeartbeatIn(BaseModel):
    runner_id: str = Field(min_length=3, max_length=64)
    page_url: str | None = Field(default=None, max_length=500)


class FragmentRunnerStatusIn(BaseModel):
    runner_id: str = Field(min_length=3, max_length=64)
    status: str = Field(min_length=2, max_length=24)
    mode: str = Field(min_length=2, max_length=24)
    version: str = Field(min_length=1, max_length=32)
    browser_healthy: bool = False
    api_healthy: bool = True
    fragment_reachable: bool = False
    login_status: str = Field(default="UNKNOWN", max_length=24)
    selector_status: str = Field(default="UNKNOWN", max_length=24)
    current_job_id: str | None = Field(default=None, max_length=36)
    current_account_code: str | None = Field(default=None, max_length=64)
    page_url: str | None = Field(default=None, max_length=500)
    last_error: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, Any] | None = None


class FragmentRunnerCaptureIn(BaseModel):
    runner_id: str = Field(min_length=3, max_length=64)
    request: dict[str, Any]
    expected_amount_nano: int = Field(gt=0)
    page_url: str | None = Field(default=None, max_length=500)
    screenshot_path: str | None = Field(default=None, max_length=500)
    trace_path: str | None = Field(default=None, max_length=500)
    html_path: str | None = Field(default=None, max_length=500)
    console_path: str | None = Field(default=None, max_length=500)
    selector_snapshot: dict[str, Any] | None = None


class FragmentRunnerFailIn(BaseModel):
    runner_id: str = Field(min_length=3, max_length=64)
    error: str = Field(min_length=1, max_length=4000)
    manual_review: bool = False
    retryable: bool = True
    failure_kind: str = Field(default="RUNNER_ERROR", max_length=64)
    page_url: str | None = Field(default=None, max_length=500)
    screenshot_path: str | None = Field(default=None, max_length=500)
    trace_path: str | None = Field(default=None, max_length=500)
    html_path: str | None = Field(default=None, max_length=500)
    console_path: str | None = Field(default=None, max_length=500)
    selector_snapshot: dict[str, Any] | None = None


class FragmentAccountOut(ORMModel):
    id: str
    code: str
    display_name: str
    profile_name: str
    status: str
    priority: int
    is_enabled: bool
    lease_runner_id: str | None
    lease_job_id: str | None
    lease_expires_at: datetime | None
    last_login_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    cookie_updated_at: datetime | None
    selector_checked_at: datetime | None
    selector_status: str
    last_page_url: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class FragmentAccountCreate(BaseModel):
    code: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,64}$")
    display_name: str = Field(min_length=2, max_length=128)
    profile_name: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,128}$")
    priority: int = Field(default=100, ge=0, le=10000)
    is_enabled: bool = True


class FragmentAccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=128)
    status: str | None = Field(default=None, max_length=24)
    priority: int | None = Field(default=None, ge=0, le=10000)
    is_enabled: bool | None = None


class FragmentRunnerInstanceOut(ORMModel):
    runner_id: str
    status: str
    mode: str
    version: str
    browser_healthy: bool
    api_healthy: bool
    fragment_reachable: bool
    login_status: str
    selector_status: str
    current_job_id: str | None
    current_account_code: str | None
    queue_depth: int
    page_url: str | None
    last_heartbeat_at: datetime
    last_claim_at: datetime | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None
    runtime_metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class FragmentJobAdminOut(ORMModel):
    id: str
    order_id: str
    account_id: str | None
    status: str
    runner_id: str | None
    wallet_code: str | None
    profile_name: str | None
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None
    retry_delay_seconds: int | None
    failure_kind: str | None
    lease_expires_at: datetime | None
    started_at: datetime | None
    captured_at: datetime | None
    finished_at: datetime | None
    page_url: str | None
    screenshot_path: str | None
    trace_path: str | None
    html_path: str | None
    console_path: str | None
    selector_snapshot: dict[str, Any] | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    order_no: str | None = None
    target_username: str | None = None
    account_code: str | None = None


class FragmentRunnerSummary(BaseModel):
    online_runners: int
    stale_runners: int
    active_accounts: int
    login_required_accounts: int
    queued_jobs: int
    retry_wait_jobs: int
    manual_review_jobs: int
