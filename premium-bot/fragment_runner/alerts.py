
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from core.config import settings

log = logging.getLogger(__name__)


class AlertManager:
    def __init__(self) -> None:
        directory = Path(settings.fragment_runner_runtime_dir)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "alerts.json"
        try:
            self.sent = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.sent = {}

    def _allowed(self, key: str) -> bool:
        value = self.sent.get(key)
        if not value:
            return True
        previous = datetime.fromisoformat(value)
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=UTC)
        return datetime.now(UTC) - previous >= timedelta(
            seconds=settings.fragment_runner_alert_cooldown_seconds
        )

    async def send(self, key: str, text: str) -> None:
        if not settings.telegram_bot_token or not settings.fragment_runner_alert_chat_id_list:
            log.warning("Runner alert suppressed because Telegram alert recipients are not configured: %s", text)
            return
        if not self._allowed(key):
            return
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=15) as client:
            for chat_id in settings.fragment_runner_alert_chat_id_list:
                try:
                    response = await client.post(url, json={"chat_id": chat_id, "text": text})
                    response.raise_for_status()
                except Exception:
                    log.exception("Failed to send Fragment runner alert to %s", chat_id)
        self.sent[key] = datetime.now(UTC).isoformat()
        self.path.write_text(json.dumps(self.sent, indent=2), encoding="utf-8")
