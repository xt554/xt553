from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from api.deps import CurrentUser, DbSession
from api.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from core.config import settings
from core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from database.models import User
from services.audit import add_audit_log

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.role),
        expires_in=settings.jwt_access_token_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: DbSession) -> TokenResponse:
    user = await session.scalar(select(User).where(User.username == payload.username))
    if (
        user is None
        or not user.password_hash
        or not verify_password(payload.password, user.password_hash)
        or not user.is_active
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    user.last_login_at = datetime.now(UTC)
    add_audit_log(
        session,
        action="auth.login",
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    await session.commit()
    return _tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, session: DbSession) -> TokenResponse:
    try:
        token = decode_token(payload.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user = await session.get(User, token["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is inactive")
    return _tokens(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser,
    session: DbSession,
) -> MessageResponse:
    if not user.password_hash or not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "当前密码错误")
    if payload.current_password == payload.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "新密码不能与当前密码相同")
    user.password_hash = hash_password(payload.new_password)
    add_audit_log(
        session,
        action="auth.change_password",
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    await session.commit()
    return MessageResponse(message="密码已更新")
