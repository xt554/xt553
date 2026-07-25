from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.api_client import BotAPIError, api_client
from bot.keyboards import deposit_networks_keyboard, wallet_keyboard
from bot.states import DepositFlow

router = Router()

ENTRY_LABELS = {
    "DEPOSIT": "充值到账",
    "ORDER_PAYMENT": "订单支付",
    "ORDER_REFUND": "订单退款",
    "ADMIN_CREDIT": "人工加款",
    "ADMIN_DEBIT": "人工扣款",
}


def format_amount(value: str | Decimal) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def format_wallet(wallet: dict[str, Any]) -> str:
    return "\n".join(
        [
            "💰 <b>我的 USDT 钱包</b>",
            "",
            f"<b>可用余额：</b><code>{format_amount(wallet['available_balance'])} USDT</code>",
            f"<b>累计充值：</b>{format_amount(wallet['total_deposited'])} USDT",
            f"<b>累计消费：</b>{format_amount(wallet['total_spent'])} USDT",
            "",
            "购买套餐时系统会自动检测余额；余额不足可按需要充值。",
        ]
    )


async def load_wallet(telegram_id: int, username: str | None) -> dict[str, Any]:
    await api_client.register_user(telegram_id, username)
    return await api_client.wallet(telegram_id)


@router.message(Command("wallet"))
async def wallet_command(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    await state.clear()
    try:
        wallet = await load_wallet(
            message.from_user.id,
            message.from_user.username,
        )
    except BotAPIError as exc:
        await message.answer(f"钱包暂时不可用：{exc}")
        return
    await message.answer(format_wallet(wallet), reply_markup=wallet_keyboard())


@router.callback_query(F.data == "wallet:home")
async def wallet_home(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        return
    await state.clear()
    try:
        wallet = await load_wallet(
            callback.from_user.id,
            callback.from_user.username,
        )
    except BotAPIError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_wallet(wallet),
            reply_markup=wallet_keyboard(),
        )


@router.callback_query(F.data == "wallet:deposit")
async def start_deposit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DepositFlow.waiting_amount)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text("请输入充值金额（USDT）：\n\n例如：<code>50</code>")


@router.message(DepositFlow.waiting_amount)
async def receive_deposit_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = Decimal((message.text or "").strip())
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("金额格式不正确，请输入大于 0 的数字。")
        return
    try:
        networks = await api_client.networks()
    except BotAPIError as exc:
        await state.clear()
        await message.answer(f"充值暂时不可用：{exc}")
        return
    if not networks:
        await state.clear()
        await message.answer("当前没有可用的 USDT 充值网络。")
        return
    await state.update_data(deposit_amount=format(amount, "f"))
    await state.set_state(DepositFlow.waiting_network)
    await message.answer(
        "请选择充值网络：",
        reply_markup=deposit_networks_keyboard(networks),
    )


@router.callback_query(
    DepositFlow.waiting_network,
    F.data.startswith("deposit-network:"),
)
async def choose_deposit_network(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if not callback.from_user:
        return
    data = await state.get_data()
    try:
        deposit = await api_client.create_deposit(
            telegram_id=callback.from_user.id,
            amount=data["deposit_amount"],
            network=(callback.data or "").split(":", 1)[1],
        )
    except (BotAPIError, KeyError) as exc:
        await state.clear()
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_text(f"创建充值单失败：{exc}\n发送 /wallet 重试。")
        return
    await state.clear()
    await callback.answer("充值单已创建")
    expires = datetime.fromisoformat(deposit["expires_at"]).astimezone()
    text = "\n".join(
        [
            "➕ <b>钱包充值</b>",
            "",
            f"<b>充值单号：</b><code>{deposit['deposit_no']}</code>",
            f"<b>网络：</b>{deposit['network']}",
            f"<b>精确金额：</b><code>{format_amount(deposit['payment_amount'])} USDT</code>",
            f"<b>收款地址：</b>\n<code>{deposit['payment_address']}</code>",
            f"<b>付款截止：</b>{expires:%Y-%m-%d %H:%M:%S}",
            "",
            "⚠️ 请严格按上述网络与精确金额转账。达到确认数后余额会自动到账。",
        ]
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text)


@router.callback_query(F.data == "wallet:ledger")
async def wallet_ledger(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    try:
        entries = await api_client.wallet_ledger(callback.from_user.id)
    except BotAPIError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    lines = ["📒 <b>最近余额明细</b>", ""]
    if not entries:
        lines.append("暂无余额变动。")
    for entry in entries:
        created = datetime.fromisoformat(entry["created_at"]).astimezone()
        amount = Decimal(str(entry["amount"]))
        sign = "+" if amount > 0 else ""
        lines.extend(
            [
                (
                    f"{created:%m-%d %H:%M} · "
                    f"{ENTRY_LABELS.get(entry['entry_type'], entry['entry_type'])}"
                ),
                (
                    f"<code>{sign}{format_amount(amount)} USDT</code>"
                    f"　余额 {format_amount(entry['balance_after'])}"
                ),
                "",
            ]
        )
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=wallet_keyboard(),
        )
