from typing import Any

from aiogram.types import (
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def plans_keyboard(plans: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(
            text=f"{plan['months']}个月 · {plan['price']} {plan['currency']}",
            callback_data=f"plan:{plan['id']}",
        )
    builder.button(text="💰 我的钱包", callback_data="wallet:home")
    builder.adjust(1)
    return builder.as_markup()


def networks_keyboard(networks: list[dict[str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for network in networks:
        builder.button(text=network["label"], callback_data=f"network:{network['code']}")
    builder.button(text="取消", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def order_keyboard(order_no: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="刷新订单状态", callback_data=f"status:{order_no}")
    builder.button(text="返回套餐", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def wallet_payment_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ 立即支付", callback_data="pay:wallet-confirm")
    builder.button(text="⬅ 返回套餐", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def insufficient_balance_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 充值钱包", callback_data="order:recharge")
    builder.button(text="⬅ 返回套餐", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def recharge_amount_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for amount in ("10", "20", "50", "100", "200", "500"):
        builder.button(text=f"{amount} USDT", callback_data=f"recharge-amount:{amount}")
    builder.button(text="✍ 自定义金额", callback_data="recharge-amount:custom")
    builder.button(text="⬅ 返回", callback_data="order:back-balance")
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()


def pending_deposit_keyboard(deposit_no: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 刷新到账状态", callback_data=f"deposit-status:{deposit_no}")
    builder.button(text="取消", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def wallet_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ 充值", callback_data="wallet:deposit")
    builder.button(text="📒 余额明细", callback_data="wallet:ledger")
    builder.button(text="🛒 购买 Premium", callback_data="menu")
    builder.adjust(2, 1)
    return builder.as_markup()


def deposit_networks_keyboard(networks: list[dict[str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for network in networks:
        builder.button(text=network["label"], callback_data=f"deposit-network:{network['code']}")
    builder.button(text="取消", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💎 购买会员星星"),
                KeyboardButton(text="📦 我的订单"),
            ],
            [
                KeyboardButton(text="👛 我的钱包"),
                KeyboardButton(text="💰 充值钱包"),
            ],
            [
                KeyboardButton(text="📜 充值记录"),
                KeyboardButton(text="📞 在线客服"),
            ],
            [
                KeyboardButton(text="⚙️ 个人中心"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="请选择功能",
    )