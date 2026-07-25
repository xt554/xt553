from aiogram.fsm.state import State, StatesGroup


class OrderFlow(StatesGroup):
    waiting_username = State()
    waiting_payment_confirm = State()
    waiting_recharge_choice = State()
    waiting_recharge_amount = State()
    waiting_recharge_network = State()
    waiting_deposit_payment = State()


class DepositFlow(StatesGroup):
    waiting_amount = State()
    waiting_network = State()
