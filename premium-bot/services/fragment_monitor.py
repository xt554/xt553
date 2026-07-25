
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.enums import FragmentRunnerStatus
from database.models import FragmentAccount, FragmentRunnerInstance

log = logging.getLogger(__name__)


async def _send_alert(text: str) -> None:
    if not settings.telegram_bot_token or not settings.fragment_runner_alert_chat_id_list:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=15) as client:
        for chat_id in settings.fragment_runner_alert_chat_id_list:
            try:
                response = await client.post(url, json={"chat_id": chat_id, "text": text})
                response.raise_for_status()
            except Exception:
                log.exception("Failed to send stale Fragment runner alert")


async def monitor_fragment_runners(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.fragment_runner_stale_seconds)
    stale = list(
        (
            await session.scalars(
                select(FragmentRunnerInstance)
                .where(
                    FragmentRunnerInstance.last_heartbeat_at < cutoff,
                    FragmentRunnerInstance.status != FragmentRunnerStatus.OFFLINE.value,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for runner in stale:
        runner.status = FragmentRunnerStatus.OFFLINE.value
        runner.last_error = "Runner heartbeat is stale"
        runner.last_error_at = now
        accounts = list(
            (
                await session.scalars(
                    select(FragmentAccount).where(
                        FragmentAccount.lease_runner_id == runner.runner_id,
                        FragmentAccount.lease_expires_at < now,
                    )
                )
            ).all()
        )
        for account in accounts:
            account.lease_runner_id = None
            account.lease_job_id = None
            account.lease_expires_at = None
        await _send_alert(
            f"⚠ Fragment Runner 已离线\nRunner: {runner.runner_id}\n最后心跳: {runner.last_heartbeat_at}"
        )
    return len(stale)
