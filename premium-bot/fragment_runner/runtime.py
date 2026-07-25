
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.config import settings


class RuntimeState:
    def __init__(self) -> None:
        directory = Path(settings.fragment_runner_runtime_dir)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "health.json"
        self.data: dict[str, Any] = {
            "status": "STARTING",
            "updated_at": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
        }
        self.write()

    def update(self, **values: Any) -> None:
        self.data.update(values)
        self.data["updated_at"] = datetime.now(UTC).isoformat()
        self.data["pid"] = os.getpid()
        self.write()

    def write(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
