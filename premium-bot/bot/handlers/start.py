from datetime import datetime
from decimal import Decimal
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.api_client import BotAPIError, api_client
from bot.keyboards import (
    main_reply_keyboard,
    plans_keyboard,
    wallet_keyboard,
)
from bot.states import DepositFlow

router = Router()


ORDER_STATUS_LABELS = {
    "WAIT_PAY": "等待支付",
    "PAID": "已支付",
    "PROCESSING": "处理中",
    "SUCCESS": "已完成",
    "FAILED": "失败",
    "TIMEOUT": "已超时",
    "CANCELLED": "已取消",
}


DEPOSIT_STATUS_LABELS = {
    "WAIT_PAY": "等待支付",
    "PENDING": "等待确认",
    "CONFIRMED": "已到账",
    "SUCCESS": "已到账",
    "PAID": "已到账",
    "TIMEOUT": "已超时",
    "CANCELLED": "已取消",
    "FAILED": "失败",
}


def format_amount(value: Any) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def parse_datetime(value: str | None) -> str:
    if not value:
        return "-"

    try:
        parsed = datetime.fromisoformat(value).astimezone()
    except (ValueError, TypeError):
        return str(value)

    return parsed.strftime("%Y-%m-%d %H:%M")


async def show_menu(message: Message) -> None:
    try:
        if message.from_user:
            await api_client.register_user(
                message.from_user.id,
                message.from_user.username,
            )

        plans = await api_client.plans()

    except BotAPIError as exc:
        await message.answer(
            f"服务暂时不可用：{exc}",
            reply_markup=main_reply_keyboard(),
        )
        return

    await message.answer(
        "👑 <b>欢迎使用 Telegram Premium 商店</b>\n\n"
        "请选择下方功能：",
        reply_markup=main_reply_keyboard(),
    )

    await message.answer(
        "💎 <b>请选择套餐：</b>",
        reply_markup=plans_keyboard(plans),
    )


@router.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await show_menu(message)


@router.message(F.text == "💎 购买会员星星")
async def reply_buy(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()

    try:
        plans = await api_client.plans()
    except BotAPIError as exc:
        await message.answer(f"获取套餐失败：{exc}")
        return

    if not plans:
        await message.answer("当前暂无可购买套餐。")
        return

    await message.answer(
        "💎 <b>请选择套餐：</b>",
        reply_markup=plans_keyboard(plans),
    )


@router.message(F.text == "📦 我的订单")
async def reply_orders(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.from_user:
        return

    await state.clear()

    try:
        orders = await api_client.orders(
            message.from_user.id,
            limit=10,
        )
    except BotAPIError as exc:
        await message.answer(f"获取订单失败：{exc}")
        return

    if not orders:
        await message.answer(
            "📦 暂无订单记录。",
            reply_markup=main_reply_keyboard(),
        )
        return

    lines = [
        "📦 <b>我的订单</b>",
        "",
    ]

    for order in orders:
        status = ORDER_STATUS_LABELS.get(
            str(order.get("status", "")),
            str(order.get("status", "-")),
        )

        months = order.get("plan_months")
        if months:
            plan_name = f"{months}个月 Premium"
        else:
            plan_name = str(
                order.get("plan_name")
                or order.get("plan_id")
                or "Premium 套餐"
            )

        amount = (
            order.get("quoted_amount")
            or order.get("amount")
            or "0"
        )

        currency = order.get("currency", "USDT")

        lines.extend(
            [
                f"订单号：<code>{order.get('order_no', '-')}</code>",
                f"套餐：{plan_name}",
                f"开通用户：{order.get('target_username', '-')}",
                f"金额：{format_amount(amount)} {currency}",
                f"状态：{status}",
                f"时间：{parse_datetime(order.get('created_at'))}",
                "────────────",
            ]
        )

    await message.answer(
        "\n".join(lines),
        reply_markup=main_reply_keyboard(),
    )


@router.message(F.text == "👛 我的钱包")
async def reply_wallet(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.from_user:
        return

    await state.clear()

    try:
        await api_client.register_user(
            message.from_user.id,
            message.from_user.username,
        )

        wallet = await api_client.wallet(
            message.from_user.id,
        )

    except BotAPIError as exc:
        await message.answer(f"钱包暂时不可用：{exc}")
        return

    text = "\n".join(
        [
            "👛 <b>我的钱包</b>",
            "",
            (
                "<b>可用余额：</b>"
                f"<code>{format_amount(wallet['available_balance'])} USDT</code>"
            ),
            (
                "<b>累计充值：</b>"
                f"{format_amount(wallet['total_deposited'])} USDT"
            ),
            (
                "<b>累计消费：</b>"
                f"{format_amount(wallet['total_spent'])} USDT"
            ),
        ]
    )

    await message.answer(
        text,
        reply_markup=wallet_keyboard(),
    )


@router.message(F.text == "💰 充值钱包")
async def reply_recharge(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.from_user:
        return

    try:
        await api_client.register_user(
            message.from_user.id,
            message.from_user.username,
        )
    except BotAPIError as exc:
        await message.answer(f"充值暂时不可用：{exc}")
        return

    await state.set_state(DepositFlow.waiting_amount)

    await message.answer(
        "💰 <b>充值钱包</b>\n\n"
        "请输入需要充值的 USDT 金额。\n\n"
        "例如：<code>50</code>"
    )


@router.message(F.text == "📜 充值记录")
async def reply_deposit_records(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.from_user:
        return

    await state.clear()

    try:
        deposits = await api_client.deposits(
            message.from_user.id,
            limit=10,
        )
    except BotAPIError as exc:
        await message.answer(f"获取充值记录失败：{exc}")
        return

    if not deposits:
        await message.answer(
            "📜 暂无充值记录。",
            reply_markup=main_reply_keyboard(),
        )
        return

    lines = [
        "📜 <b>最近充值记录</b>",
        "",
    ]

    for deposit in deposits:
        status = DEPOSIT_STATUS_LABELS.get(
            str(deposit.get("status", "")),
            str(deposit.get("status", "-")),
        )

        amount = (
            deposit.get("payment_amount")
            or deposit.get("requested_amount")
            or deposit.get("amount")
            or "0"
        )

        currency = deposit.get("currency", "USDT")

        lines.extend(
            [
                (
                    "充值单号："
                    f"<code>{deposit.get('deposit_no', '-')}</code>"
                ),
                f"金额：{format_amount(amount)} {currency}",
                f"网络：{deposit.get('network', '-')}",
                f"状态：{status}",
                f"时间：{parse_datetime(deposit.get('created_at'))}",
                "────────────",
            ]
        )

    await message.answer(
        "\n".join(lines),
        reply_markup=main_reply_keyboard(),
    )


@router.message(F.text == "📞 在线客服")
async def reply_support(message: Message) -> None:
    await message.answer(
        "📞 <b>在线客服</b>\n\n"
        "请联系：@你的客服用户名",
        reply_markup=main_reply_keyboard(),
    )


@router.message(F.text == "⚙️ 个人中心")
async def reply_profile(message: Message) -> None:
    if not message.from_user:
        return

    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "未设置"
    )

    await message.answer(
        "⚙️ <b>个人中心</b>\n\n"
        f"Telegram ID：<code>{message.from_user.id}</code>\n"
        f"用户名：{username}\n"
        f"昵称：{message.from_user.full_name}",
        reply_markup=main_reply_keyboard(),
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "<b>可用命令</b>\n"
        "/start - 打开主菜单\n"
        "/wallet - 钱包余额与充值\n"
        "/status 订单号 - 查询订单\n"
        "/cancel - 取消当前操作",
        reply_markup=main_reply_keyboard(),
    )


@router.message(Command("cancel"))
async def cancel_command(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()

    await message.answer(
        "当前操作已取消。",
        reply_markup=main_reply_keyboard(),
    )


@router.callback_query(F.data == "menu")
async def menu_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()

    if isinstance(callback.message, Message):
        await show_menu(callback.message)


@router.callback_query(F.data == "cancel")
async def cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer("已取消")
    await state.clear()

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "当前操作已取消。"
        )

        await callback.message.answer(
            "请选择下方功能：",
            reply_markup=main_reply_keyboard(),
        )