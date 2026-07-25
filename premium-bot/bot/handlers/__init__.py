from aiogram import Router

from bot.handlers import order, start, wallet

router = Router()
router.include_router(start.router)
router.include_router(wallet.router)
router.include_router(order.router)
