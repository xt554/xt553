from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, utcnow
from database.enums import (
    DepositStatus,
    OrderStatus,
    PaymentMethod,
    PaymentNetwork,
    PaymentStatus,
    RefundStatus,
    UserRole,
)


def uuid_str() -> str:
    return str(uuid4())


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), index=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default=UserRole.USER.value, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    orders: Mapped[list[Order]] = relationship(back_populates="user")
    wallet_accounts: Mapped[list[UserWallet]] = relationship(back_populates="user")
    deposit_orders: Mapped[list[DepositOrder]] = relationship(back_populates="user")


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    months: Mapped[int] = mapped_column(Integer, unique=True)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(16), default="USDT")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    orders: Mapped[list[Order]] = relationship(back_populates="plan")


class Wallet(TimestampMixin, Base):
    __tablename__ = "wallets"
    __table_args__ = (UniqueConstraint("network", "address", name="uq_wallet_network_address"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(128))
    network: Mapped[str] = mapped_column(String(16), index=True)
    address: Mapped[str] = mapped_column(String(128), index=True)
    token_contract: Mapped[str | None] = mapped_column(String(128))
    token_decimals: Mapped[int] = mapped_column(Integer, default=6)
    min_confirmations: Mapped[int] = mapped_column(Integer, default=20)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_scanned_block: Mapped[int | None] = mapped_column(BigInteger)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    orders: Mapped[list[Order]] = relationship(back_populates="wallet")
    deposit_orders: Mapped[list[DepositOrder]] = relationship(back_populates="receive_wallet")


class OrderSequence(Base):
    __tablename__ = "order_sequences"

    sequence_date: Mapped[date] = mapped_column(Date, primary_key=True)
    current_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index(
            "ix_order_payment_match",
            "network",
            "payment_address",
            "payment_amount",
            "status",
        ),
        Index("ix_order_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), index=True)
    wallet_id: Mapped[str | None] = mapped_column(ForeignKey("wallets.id"), index=True)
    target_username: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default=OrderStatus.WAIT_PAY.value, index=True)
    payment_method: Mapped[str] = mapped_column(
        String(24), default=PaymentMethod.ONCHAIN.value, index=True
    )
    network: Mapped[str] = mapped_column(String(16), default=PaymentNetwork.TRC20.value, index=True)
    currency: Mapped[str] = mapped_column(String(16), default="USDT")
    quoted_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    payment_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    payment_address: Mapped[str] = mapped_column(String(128))
    tx_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    premium_reference: Mapped[str | None] = mapped_column(String(128), index=True)
    callback_url: Mapped[str | None] = mapped_column(String(500))
    balance_payment_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    balance_refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfillment_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_fulfillment_error: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    manual_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    user: Mapped[User] = relationship(back_populates="orders", lazy="selectin")
    plan: Mapped[Plan] = relationship(back_populates="orders", lazy="selectin")
    wallet: Mapped[Wallet | None] = relationship(back_populates="orders", lazy="selectin")
    payments: Mapped[list[PaymentTransaction]] = relationship(back_populates="order")
    history: Mapped[list[OrderStatusHistory]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    refunds: Mapped[list[Refund]] = relationship(back_populates="order")
    fragment_jobs: Mapped[list[FragmentJob]] = relationship(back_populates="order")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(String(24), default="SYSTEM")
    actor_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    order: Mapped[Order] = relationship(back_populates="history")


class PaymentTransaction(TimestampMixin, Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("network", "tx_hash", "log_index", name="uq_chain_transaction"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), index=True)
    deposit_order_id: Mapped[str | None] = mapped_column(
        ForeignKey("deposit_orders.id"), index=True
    )
    network: Mapped[str] = mapped_column(String(16), index=True)
    tx_hash: Mapped[str] = mapped_column(String(128), index=True)
    log_index: Mapped[int] = mapped_column(Integer, default=0)
    block_number: Mapped[int | None] = mapped_column(BigInteger)
    block_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    from_address: Mapped[str | None] = mapped_column(String(128))
    to_address: Mapped[str] = mapped_column(String(128), index=True)
    token_contract: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    confirmations: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(24), default=PaymentStatus.DETECTED.value, index=True
    )
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    order: Mapped[Order | None] = relationship(back_populates="payments")
    deposit_order: Mapped[DepositOrder | None] = relationship(back_populates="payments")


class UserWallet(TimestampMixin, Base):
    __tablename__ = "user_wallets"
    __table_args__ = (UniqueConstraint("user_id", "currency", name="uq_user_wallet_currency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    currency: Mapped[str] = mapped_column(String(16), default="USDT")
    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), nullable=False
    )
    total_deposited: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), nullable=False
    )
    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    user: Mapped[User] = relationship(back_populates="wallet_accounts")
    ledger_entries: Mapped[list[WalletLedgerEntry]] = relationship(back_populates="wallet")
    deposit_orders: Mapped[list[DepositOrder]] = relationship(back_populates="user_wallet")


class WalletLedgerEntry(Base):
    __tablename__ = "wallet_ledger_entries"
    __table_args__ = (Index("ix_wallet_ledger_wallet_created", "wallet_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("user_wallets.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    reference_type: Mapped[str] = mapped_column(String(32), index=True)
    reference_id: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    wallet: Mapped[UserWallet] = relationship(back_populates="ledger_entries")


class DepositOrder(TimestampMixin, Base):
    __tablename__ = "deposit_orders"
    __table_args__ = (
        Index(
            "ix_deposit_payment_match",
            "network",
            "payment_address",
            "payment_amount",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    deposit_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user_wallet_id: Mapped[str] = mapped_column(ForeignKey("user_wallets.id"), index=True)
    receive_wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    network: Mapped[str] = mapped_column(String(16), index=True)
    currency: Mapped[str] = mapped_column(String(16), default="USDT")
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    payment_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    payment_address: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(
        String(24), default=DepositStatus.WAIT_PAY.value, index=True
    )
    tx_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="deposit_orders")
    user_wallet: Mapped[UserWallet] = relationship(back_populates="deposit_orders")
    receive_wallet: Mapped[Wallet] = relationship(back_populates="deposit_orders")
    payments: Mapped[list[PaymentTransaction]] = relationship(back_populates="deposit_order")


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    destination_address: Mapped[str] = mapped_column(String(128))
    network: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    status: Mapped[str] = mapped_column(
        String(24), default=RefundStatus.REQUESTED.value, index=True
    )
    provider_reference: Mapped[str | None] = mapped_column(String(128))
    tx_hash: Mapped[str | None] = mapped_column(String(128))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    order: Mapped[Order] = relationship(back_populates="refunds")


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(String(500))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str | None] = mapped_column(String(64), index=True)
    target_id: Mapped[str | None] = mapped_column(String(64), index=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class WebhookDelivery(TimestampMixin, Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    event: Mapped[str] = mapped_column(String(64), index=True)
    target_url: Mapped[str] = mapped_column(String(500))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))



class FragmentAccount(TimestampMixin, Base):
    __tablename__ = "fragment_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    profile_name: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    lease_runner_id: Mapped[str | None] = mapped_column(String(64), index=True)
    lease_job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cookie_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selector_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selector_status: Mapped[str] = mapped_column(String(24), default="UNKNOWN", index=True)
    last_page_url: Mapped[str | None] = mapped_column(String(500))
    last_error: Mapped[str | None] = mapped_column(Text)

    jobs: Mapped[list[FragmentJob]] = relationship(back_populates="account")


class FragmentRunnerInstance(TimestampMixin, Base):
    __tablename__ = "fragment_runner_instances"

    runner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="STARTING", index=True)
    mode: Mapped[str] = mapped_column(String(24), default="observe")
    version: Mapped[str] = mapped_column(String(32), default="4.3.0")
    browser_healthy: Mapped[bool] = mapped_column(Boolean, default=False)
    api_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    fragment_reachable: Mapped[bool] = mapped_column(Boolean, default=False)
    login_status: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    selector_status: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    current_job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    current_account_code: Mapped[str | None] = mapped_column(String(64), index=True)
    queue_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_url: Mapped[str | None] = mapped_column(String(500))
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_claim_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    runtime_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class FragmentJob(TimestampMixin, Base):
    __tablename__ = "fragment_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("fragment_accounts.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    runner_id: Mapped[str | None] = mapped_column(String(64), index=True)
    wallet_code: Mapped[str | None] = mapped_column(String(32), index=True)
    profile_name: Mapped[str | None] = mapped_column(String(128))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    retry_delay_seconds: Mapped[int | None] = mapped_column(Integer)
    failure_kind: Mapped[str | None] = mapped_column(String(64), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quoted_ton_nano: Mapped[int | None] = mapped_column(BigInteger)
    captured_request: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    page_url: Mapped[str | None] = mapped_column(String(500))
    screenshot_path: Mapped[str | None] = mapped_column(String(500))
    trace_path: Mapped[str | None] = mapped_column(String(500))
    html_path: Mapped[str | None] = mapped_column(String(500))
    console_path: Mapped[str | None] = mapped_column(String(500))
    selector_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(Text)

    order: Mapped[Order] = relationship(back_populates="fragment_jobs", lazy="selectin")
    account: Mapped[FragmentAccount | None] = relationship(back_populates="jobs", lazy="selectin")

class HotWallet(TimestampMixin, Base):
    """TON fulfillment wallet metadata. No secret material is stored here."""

    __tablename__ = "hot_wallets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    wallet_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    address: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    wallet_version: Mapped[str] = mapped_column(String(32), default="v4r2")
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    balance_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    reserved_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    single_limit_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    daily_limit_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    daily_spent_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    spent_date: Mapped[date | None] = mapped_column(Date, index=True)
    minimum_balance_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    target_balance_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    maximum_balance_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    consecutive_failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seqno: Mapped[int | None] = mapped_column(BigInteger)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WalletReservation(TimestampMixin, Base):
    __tablename__ = "wallet_reservations"
    __table_args__ = (Index("ix_wallet_reservation_wallet_status", "wallet_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("hot_wallets.id"), index=True)
    reserved_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="RESERVED", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TonTransaction(TimestampMixin, Base):
    __tablename__ = "ton_transactions"
    __table_args__ = (
        UniqueConstraint("wallet_id", "seqno", name="uq_ton_wallet_seqno"),
        Index("ix_ton_transaction_hash", "tx_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("hot_wallets.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    seqno: Mapped[int | None] = mapped_column(BigInteger)
    valid_until: Mapped[int | None] = mapped_column(BigInteger)
    source_address: Mapped[str | None] = mapped_column(String(128), index=True)
    destination: Mapped[str] = mapped_column(String(128), index=True)
    amount_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(128))
    capture_fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)
    signer_request_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    signer_mode: Mapped[str | None] = mapped_column(String(32))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500))
    external_message_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    tx_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    tx_lt: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="CREATED", index=True)
    broadcast_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_chain_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class TonTransactionSchema(TimestampMixin, Base):
    __tablename__ = "ton_transaction_schemas"

    schema_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_destination: Mapped[str | None] = mapped_column(String(128))
    last_destination: Mapped[str | None] = mapped_column(String(128))
    last_payload_hash: Mapped[str | None] = mapped_column(String(128))
    approved_by: Mapped[str | None] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentWhitelist(TimestampMixin, Base):
    __tablename__ = "payment_whitelist"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    destination: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    maximum_single_nano: Mapped[int | None] = mapped_column(BigInteger)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CircuitBreaker(TimestampMixin, Base):
    __tablename__ = "circuit_breakers"

    breaker_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), default="CLOSED", index=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(500))
