from celery import Celery

from core.config import settings
from core.logging import configure_logging

configure_logging()

celery_app = Celery(
    "premium_bot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["worker.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    task_routes={
        "worker.tasks.fulfill_order": {"queue": "fulfillment"},
        "worker.tasks.scan_payments": {"queue": "payments"},
        "worker.tasks.*": {"queue": "default"},
    },
    beat_schedule={
        "expire-unpaid-orders": {
            "task": "worker.tasks.expire_orders",
            "schedule": 60.0,
        },
        "expire-wallet-deposits": {
            "task": "worker.tasks.expire_deposits",
            "schedule": 60.0,
        },
        "scan-usdt-payments": {
            "task": "worker.tasks.scan_payments",
            "schedule": 15.0,
        },
        "poll-processing-orders": {
            "task": "worker.tasks.poll_processing_orders",
            "schedule": 60.0,
        },
        "expire-ton-wallet-reservations": {
            "task": "worker.tasks.expire_ton_reservations",
            "schedule": 60.0,
        },
        "reconcile-ton-transactions": {
            "task": "worker.tasks.reconcile_ton_transactions",
            "schedule": 20.0,
        },
        "sync-ton-hot-wallets": {
            "task": "worker.tasks.sync_ton_wallets",
            "schedule": 60.0,
        },
        "monitor-fragment-runners": {
            "task": "worker.tasks.monitor_fragment_runners",
            "schedule": 60.0,
        },
    },
)
