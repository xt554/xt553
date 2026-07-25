from fastapi import APIRouter
from sqlalchemy import select

from api.deps import AdminUser, DbSession
from api.schemas import WalletCreate, WalletOut, WalletUpdate
from database.enums import PaymentNetwork
from database.models import Wallet
from services.audit import add_audit_log
from services.errors import NotFoundError, ValidationError

router = APIRouter(prefix="/wallets")


@router.get("", response_model=list[WalletOut])
async def list_wallets(session: DbSession, _: AdminUser) -> list[Wallet]:
    return list((await session.scalars(select(Wallet).order_by(Wallet.network, Wallet.name))).all())


@router.post("", response_model=WalletOut)
async def create_wallet(payload: WalletCreate, session: DbSession, admin: AdminUser) -> Wallet:
    try:
        network = PaymentNetwork(payload.network.upper())
    except ValueError as exc:
        raise ValidationError("不支持的网络") from exc
    values = payload.model_dump()
    values["network"] = network.value
    wallet = Wallet(**values)
    session.add(wallet)
    await session.flush()
    add_audit_log(
        session,
        action="wallet.create",
        actor_id=admin.id,
        target_type="wallet",
        target_id=wallet.id,
        details={"name": wallet.name, "network": wallet.network, "address": wallet.address},
    )
    await session.commit()
    return wallet


@router.patch("/{wallet_id}", response_model=WalletOut)
async def update_wallet(
    wallet_id: str,
    payload: WalletUpdate,
    session: DbSession,
    admin: AdminUser,
) -> Wallet:
    wallet = await session.get(Wallet, wallet_id)
    if wallet is None:
        raise NotFoundError("钱包不存在")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(wallet, key, value)
    add_audit_log(
        session,
        action="wallet.update",
        actor_id=admin.id,
        target_type="wallet",
        target_id=wallet.id,
        details=changes,
    )
    await session.commit()
    return wallet


@router.delete("/{wallet_id}", response_model=WalletOut)
async def disable_wallet(wallet_id: str, session: DbSession, admin: AdminUser) -> Wallet:
    wallet = await session.get(Wallet, wallet_id)
    if wallet is None:
        raise NotFoundError("钱包不存在")
    wallet.is_enabled = False
    add_audit_log(
        session,
        action="wallet.disable",
        actor_id=admin.id,
        target_type="wallet",
        target_id=wallet.id,
    )
    await session.commit()
    return wallet
