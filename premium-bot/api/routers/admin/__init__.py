from fastapi import APIRouter

from api.routers.admin import (
    fragment_runners,
    logs,
    orders,
    plans,
    settings,
    stats,
    ton,
    users,
    wallet_accounts,
    wallets,
)

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(stats.router)
router.include_router(fragment_runners.router)
router.include_router(ton.router)
router.include_router(users.router)
router.include_router(plans.router)
router.include_router(orders.router)
router.include_router(wallets.router)
router.include_router(wallet_accounts.router)
router.include_router(logs.router)
router.include_router(settings.router)
