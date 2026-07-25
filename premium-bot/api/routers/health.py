from fastapi import APIRouter, HTTPException
from redis.asyncio import Redis
from sqlalchemy import text

from api.deps import DbSession
from core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(session: DbSession) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
        redis = Redis.from_url(settings.redis_url)
        try:
            await redis.ping()
        finally:
            await redis.aclose()
    except Exception as exc:
        raise HTTPException(503, "Dependencies are not ready") from exc
    return {"status": "ready"}
