
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException

from core.config import settings

app = FastAPI(title="Fragment Runner Health", docs_url=None, redoc_url=None)


def read_state() -> dict:
    path = Path(settings.fragment_runner_runtime_dir) / "health.json"
    if not path.exists():
        raise HTTPException(503, "runner state is unavailable")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "runner state is invalid") from exc


@app.get("/health/live")
async def live() -> dict:
    state = read_state()
    updated = datetime.fromisoformat(state["updated_at"])
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    age = (datetime.now(UTC) - updated).total_seconds()
    if age > settings.fragment_runner_stale_seconds:
        raise HTTPException(503, f"runner heartbeat is stale: {age:.0f}s")
    return {"status": "ok", "runner": state.get("status"), "age_seconds": round(age, 2)}


@app.get("/health/ready")
async def ready() -> dict:
    state = read_state()
    if state.get("status") in {"ERROR", "OFFLINE"}:
        raise HTTPException(503, "runner is not ready")
    return state
