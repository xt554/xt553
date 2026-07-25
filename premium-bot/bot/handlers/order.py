from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.api_client import BotAPIError, api_client
from bot.keyboards import (
    deposit_networks_keyboard,
    insufficient_balance_keyboard,
    order_keyboard,
    pending_deposit_keyboard,
    recharge_amount_keyboard,
    wallet_payment_confirm_keyboard,
)
from bot.states import OrderFlow
from services.errors import ValidationError
from services.orders import normalize_telegram_username

router = Router()

STATUS_LABELS = {
    "WAIT_PAY": "等待付款",
    "PAID": "已付款",
    "PROCESSING": "正在处理",
    "WAIT_FRAGMENT": "等待 Fragment 执行",
    "WAIT_SIGN": "等待 TON 签名",
    "BROADCASTED": "交易已广播",
    "CONFIRMING": "链上确认中",
    "COMPLETED": "已完成",
    "SUCCESS": "已完成（旧状态）",
    "FAILED": "处理失败",
    "REFUNDED": "已退款",
    "MANUAL_REVIEW": "人工审核",
    "TIMEOUT": "订单超时",
}

MIN_RECHARGE = Decimal("5")
MAX_RECHARGE = Decimal("10000")


def format_amount(value: str | Decimal) -> str:
    amount = Decimal(str(value))
    return format(amount.normalize(), "f")


def format_order(order: dict) -> str:
    plan = order["plan"]
    status = order["status"]
    lines = [
        f"<b>订单号：</b><code>{order['order_no']}</code>",
        f"<b>套餐：</b>{plan['name']}",
        f"<b>Telegram：</b>{order['target_username']}",
        "<b>支付方式：</b>钱包余额",
        f"<b>状态：</b>{STATUS_LABELS.get(status, status)}",
        "",
    ]
    if status == "PAID":
        lines.append("✅ 钱包支付成功，正在进入处理队列……")
    elif status in {"PROCESSING", "WAIT_FRAGMENT", "WAIT_SIGN", "BROADCASTED", "CONFIRMING"}:
        lines.append("⏳ 订单正在真实发货流程中，请稍后刷新状态。")
    elif status in {"COMPLETED", "SUCCESS"}:
        lines.append("🎉 Telegram Premium 已确认赠送成功。感谢您的购买！")
    elif status == "MANUAL_REVIEW":
        lines.append("⚠️ 订单已进入人工审核，余额不会重复扣除。")
    elif status == "REFUNDED":
        lines.append("💰 发货失败，本次钱包付款已自动退回。")
    elif status == "FAILED":
        lines.append("处理失败，系统正在执行退款或等待人工处理。")
    return "\n".join(lines)


def balance_text(plan: dict, target: str, balance: Decimal) -> str:
    price = Decimal(str(plan["price"]))
    if balance >= price:
        return "\n".join(
            [
                "💰 <b>钱包余额支付</b>",
                "",
                f"<b>套餐：</b>{plan['name']}",
                f"<b>Telegram：</b>{target}",
                f"<b>价格：</b><code>{format_amount(price)} USDT</code>",
                f"<b>钱包余额：</b><code>{format_amount(balance)} USDT</code>",
                "",
                "余额充足，确认后将立即扣款并自动发货。",
            ]
        )
    shortage = price - balance
    return "\n".join(
        [
            "⚠️ <b>钱包余额不足</b>",
            "",
            f"<b>套餐：</b>{plan['name']}",
            f"<b>Telegram：</b>{target}",
            f"<b>价格：</b><code>{format_amount(price)} USDT</code>",
            f"<b>钱包余额：</b><code>{format_amount(balance)} USDT</code>",
            f"<b>还差：</b><code>{format_amount(shortage)} USDT</code>",
            "",
            "您可以根据需要选择任意充值金额。",
        ]
    )


async def load_plan(plan_id: str) -> dict:
    plans = await api_client.plans()
    for plan in plans:
        if str(plan["id"]) == str(plan_id):
            return plan
    raise BotAPIError("套餐不存在或已下架")


async def show_balance_result(message: Message, state: FSMContext, telegram_id: int) -> None:
    data = await state.get_data()
    plan = await load_plan(data["plan_id"])
    wallet = await api_client.wallet(telegram_id)
    balance = Decimal(str(wallet["available_balance"]))
    await state.update_data(plan=plan)
    if balance >= Decimal(str(plan["price"])):
        await state.set_state(OrderFlow.waiting_payment_confirm)
        await message.edit_text(
            balance_text(plan, data["target_username"], balance),
            reply_markup=wallet_payment_confirm_keyboard(),
        )
    else:
        await state.set_state(OrderFlow.waiting_recharge_choice)
        await message.edit_text(
            balance_text(plan, data["target_username"], balance),
            reply_markup=insufficient_balance_keyboard(),
        )


@router.callback_query(F.data.startswith("plan:"))
async def choose_plan(callback: CallbackQuery, state: FSMContext) -> None:
    plan_id = (callback.data or "").split(":", 1)[1]
    await state.update_data(plan_id=plan_id)
    await state.set_state(OrderFlow.waiting_username)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "请输入要开通 Premium 的 Telegram 用户名：\n\n例如：<code>@xt542</code>"
        )


@router.message(OrderFlow.waiting_username)
async def receive_username(message: Message, state: FSMContext) -> None:
    try:
        target = normalize_telegram_username(message.text or "")
    except ValidationError as exc:
        await message.answer(f"{exc.message}\n请重新输入，例如：<code>@xt542</code>")
        return
    if not message.from_user:
        await state.clear()
        return
    await state.update_data(target_username=target)
    try:
        plan = await load_plan((await state.get_data())["plan_id"])
        wallet = await api_client.wallet(message.from_user.id)
    except (BotAPIError, KeyError) as exc:
        await state.clear()
        await message.answer(f"服务暂时不可用：{exc}")
        return
    balance = Decimal(str(wallet["available_balance"]))
    await state.update_data(plan=plan)
    if balance >= Decimal(str(plan["price"])):
        await state.set_state(OrderFlow.waiting_payment_confirm)
        await message.answer(
            balance_text(plan, target, balance),
            reply_markup=wallet_payment_confirm_keyboard(),
        )
    else:
        await state.set_state(OrderFlow.waiting_recharge_choice)
        await message.answer(
            balance_text(plan, target, balance),
            reply_markup=insufficient_balance_keyboard(),
        )


@router.callback_query(OrderFlow.waiting_payment_confirm, F.data == "pay:wallet-confirm")
async def confirm_wallet_payment(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        return
    data = await state.get_data()
    try:
        order = await api_client.create_order(
            telegram_id=callback.from_user.id,
            plan_id=data["plan_id"],
            target_username=data["target_username"],
            network=None,
            payment_method="WALLET_BALANCE",
        )
    except (BotAPIError, KeyError) as exc:
        await callback.answer(str(exc), show_alert=True)
        # Keep the purchase state so a balance race can be recovered by recharging.
        if isinstance(callback.message, Message):
            try:
                await show_balance_result(callback.message, state, callback.from_user.id)
            except BotAPIError:
                pass
        return
    await state.clear()
    await callback.answer("支付成功")
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_order(order),
            reply_markup=order_keyboard(order["order_no"]),
        )


@router.callback_query(OrderFlow.waiting_recharge_choice, F.data == "order:recharge")
async def choose_recharge_amount(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderFlow.waiting_recharge_choice)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "💳 <b>充值钱包</b>\n\n请选择充值金额，或输入自定义金额：",
            reply_markup=recharge_amount_keyboard(),
        )


@router.callback_query(F.data == "order:back-balance")
async def back_to_balance(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not isinstance(callback.message, Message):
        return
    await callback.answer()
    try:
        await show_balance_result(callback.message, state, callback.from_user.id)
    except (BotAPIError, KeyError) as exc:
        await state.clear()
        await callback.message.edit_text(f"服务暂时不可用：{exc}\n发送 /start 重试。")


async def prepare_recharge_networks(message: Message, state: FSMContext, amount: Decimal) -> None:
    if amount < MIN_RECHARGE or amount > MAX_RECHARGE:
        await message.answer(
            f"充值金额必须在 {format_amount(MIN_RECHARGE)}～{format_amount(MAX_RECHARGE)} USDT 之间。"
        )
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
    await state.update_data(recharge_amount=format(amount, "f"))
    await state.set_state(OrderFlow.waiting_recharge_network)
    await message.answer(
        f"充值金额：<code>{format_amount(amount)} USDT</code>\n\n请选择充值网络：",
        reply_markup=deposit_networks_keyboard(networks),
    )


@router.callback_query(
    OrderFlow.waiting_recharge_choice,
    F.data.startswith("recharge-amount:"),
)
async def recharge_amount_callback(callback: CallbackQuery, state: FSMContext) -> None:
    value = (callback.data or "").split(":", 1)[1]
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    if value == "custom":
        await state.set_state(OrderFlow.waiting_recharge_amount)
        await callback.message.edit_text(
            "✍ <b>自定义充值金额</b>\n\n"
            f"请输入 {format_amount(MIN_RECHARGE)}～{format_amount(MAX_RECHARGE)} USDT 之间的金额。\n"
            "例如：<code>28.5</code>"
        )
        return
    await prepare_recharge_networks(callback.message, state, Decimal(value))


@router.message(OrderFlow.waiting_recharge_amount)
async def custom_recharge_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = Decimal((message.text or "").strip())
        if not amount.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("金额格式不正确，请输入数字，例如：<code>28.5</code>")
        return
    await prepare_recharge_networks(message, state, amount)


@router.callback_query(
    OrderFlow.waiting_recharge_network,
    F.data.startswith("deposit-network:"),
)
async def create_purchase_deposit(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        return
    data = await state.get_data()
    try:
        deposit = await api_client.create_deposit(
            telegram_id=callback.from_user.id,
            amount=data["recharge_amount"],
            network=(callback.data or "").split(":", 1)[1],
        )
    except (BotAPIError, KeyError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.update_data(deposit_no=deposit["deposit_no"])
    await state.set_state(OrderFlow.waiting_deposit_payment)
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
            "到账后点击“刷新到账状态”，系统会自动返回刚才的购买流程。",
        ]
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text,
            reply_markup=pending_deposit_keyboard(deposit["deposit_no"]),
        )


@router.callback_query(F.data.startswith("deposit-status:"))
async def refresh_deposit_status(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        return
    deposit_no = (callback.data or "").split(":", 1)[1]
    try:
        deposit = await api_client.deposit(deposit_no, callback.from_user.id)
    except BotAPIError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    status = str(deposit["status"]).upper()
    if status not in {"PAID", "CONFIRMED", "SUCCESS"}:
        labels = {"WAIT_PAY": "等待付款", "TIMEOUT": "已超时", "FAILED": "处理失败"}
        await callback.answer(f"当前状态：{labels.get(status, status)}", show_alert=True)
        return
    await callback.answer("充值已到账")
    if not isinstance(callback.message, Message):
        return
    try:
        await show_balance_result(callback.message, state, callback.from_user.id)
    except (BotAPIError, KeyError) as exc:
        await state.clear()
        await callback.message.edit_text(f"充值已到账，但恢复购买失败：{exc}\n发送 /start 继续购买。")


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    if not message.from_user:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("用法：<code>/status NO202607240001</code>")
        return
    try:
        order = await api_client.order(parts[1].strip().upper(), message.from_user.id)
    except BotAPIError as exc:
        await message.answer(f"查询失败：{exc}")
        return
    await message.answer(format_order(order), reply_markup=order_keyboard(order["order_no"]))


@router.callback_query(F.data.startswith("status:"))
async def refresh_status(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    order_no = (callback.data or "").split(":", 1)[1]
    try:
        order = await api_client.order(order_no, callback.from_user.id)
    except BotAPIError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("状态已刷新")
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_order(order),
            reply_markup=order_keyboard(order["order_no"]),
        )
