from enum import StrEnum


class UserRole(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class OrderStatus(StrEnum):
    WAIT_PAY = "WAIT_PAY"
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    WAIT_FRAGMENT = "WAIT_FRAGMENT"
    WAIT_SIGN = "WAIT_SIGN"
    BROADCASTED = "BROADCASTED"
    CONFIRMING = "CONFIRMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    TIMEOUT = "TIMEOUT"

    # Legacy value kept only so old callbacks/data can be interpreted during rollout.
    SUCCESS = "SUCCESS"


class PaymentNetwork(StrEnum):
    TRC20 = "TRC20"
    BEP20 = "BEP20"
    ERC20 = "ERC20"


class PaymentStatus(StrEnum):
    DETECTED = "DETECTED"
    CONFIRMED = "CONFIRMED"
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"
    REFUNDED = "REFUNDED"


class DepositStatus(StrEnum):
    WAIT_PAY = "WAIT_PAY"
    CONFIRMED = "CONFIRMED"
    TIMEOUT = "TIMEOUT"


class PaymentMethod(StrEnum):
    ONCHAIN = "ONCHAIN"
    WALLET_BALANCE = "WALLET_BALANCE"


class WalletEntryType(StrEnum):
    DEPOSIT = "DEPOSIT"
    ORDER_PAYMENT = "ORDER_PAYMENT"
    ORDER_REFUND = "ORDER_REFUND"
    ADMIN_CREDIT = "ADMIN_CREDIT"
    ADMIN_DEBIT = "ADMIN_DEBIT"


class RefundStatus(StrEnum):
    REQUESTED = "REQUESTED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.WAIT_PAY: {OrderStatus.PAID, OrderStatus.TIMEOUT},
    OrderStatus.PAID: {OrderStatus.PROCESSING, OrderStatus.FAILED, OrderStatus.MANUAL_REVIEW},
    OrderStatus.PROCESSING: {
        OrderStatus.WAIT_FRAGMENT,
        OrderStatus.WAIT_SIGN,
        OrderStatus.COMPLETED,
        OrderStatus.FAILED,
        OrderStatus.MANUAL_REVIEW,
    },
    OrderStatus.WAIT_FRAGMENT: {
        OrderStatus.WAIT_SIGN,
        OrderStatus.COMPLETED,
        OrderStatus.FAILED,
        OrderStatus.MANUAL_REVIEW,
    },
    OrderStatus.WAIT_SIGN: {
        OrderStatus.BROADCASTED,
        OrderStatus.FAILED,
        OrderStatus.MANUAL_REVIEW,
    },
    OrderStatus.BROADCASTED: {
        OrderStatus.CONFIRMING,
        OrderStatus.FAILED,
        OrderStatus.MANUAL_REVIEW,
    },
    OrderStatus.CONFIRMING: {
        OrderStatus.COMPLETED,
        OrderStatus.FAILED,
        OrderStatus.MANUAL_REVIEW,
    },
    OrderStatus.MANUAL_REVIEW: {
        OrderStatus.PROCESSING,
        OrderStatus.WAIT_FRAGMENT,
        OrderStatus.WAIT_SIGN,
        OrderStatus.COMPLETED,
        OrderStatus.FAILED,
    },
    OrderStatus.FAILED: {OrderStatus.PROCESSING, OrderStatus.REFUNDED, OrderStatus.MANUAL_REVIEW},
    OrderStatus.REFUNDED: {OrderStatus.PROCESSING},
    OrderStatus.TIMEOUT: {OrderStatus.PAID},
    OrderStatus.COMPLETED: set(),
    OrderStatus.SUCCESS: set(),
}


def can_transition(current: OrderStatus | str, target: OrderStatus | str) -> bool:
    return OrderStatus(target) in ORDER_TRANSITIONS[OrderStatus(current)]


class HotWalletStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DRAINING = "DRAINING"
    DISABLED = "DISABLED"


class WalletReservationStatus(StrEnum):
    RESERVED = "RESERVED"
    CONSUMED = "CONSUMED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class TonTransactionStatus(StrEnum):
    CREATED = "CREATED"
    SIGNING = "SIGNING"
    BROADCASTED = "BROADCASTED"
    SIMULATED = "SIMULATED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    RETRY_WAIT = "RETRY_WAIT"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    SELECTOR_ERROR = "SELECTOR_ERROR"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class FragmentJobStatus(StrEnum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    WAIT_CAPTURE = "WAIT_CAPTURE"
    CAPTURED = "CAPTURED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY_WAIT = "RETRY_WAIT"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    SELECTOR_ERROR = "SELECTOR_ERROR"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    CANCELLED = "CANCELLED"


class FragmentAccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


class FragmentRunnerStatus(StrEnum):
    STARTING = "STARTING"
    IDLE = "IDLE"
    BUSY = "BUSY"
    ONLINE = "ONLINE"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    SELECTOR_ERROR = "SELECTOR_ERROR"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"


class FragmentSelectorStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    OK = "OK"
    FAILED = "FAILED"
