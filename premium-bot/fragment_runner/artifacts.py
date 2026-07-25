from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page

from core.config import settings

log = logging.getLogger("fragment_runner.artifacts")


@dataclass
class ArtifactSet:
    screenshot_path: str | None = None
    trace_path: str | None = None
    html_path: str | None = None
    console_path: str | None = None

    def as_payload(self) -> dict[str, str | None]:
        return {
            "screenshot_path": self.screenshot_path,
            "trace_path": self.trace_path,
            "html_path": self.html_path,
            "console_path": self.console_path,
        }


class ArtifactRecorder:
    def __init__(self, job_id: str):
        day = datetime.now(UTC).strftime("%Y%m%d")
        self.root = Path(settings.fragment_runner_artifact_dir).resolve()
        self.directory = self.root / day / job_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.console: list[dict[str, Any]] = []
        self.trace_started = False

    def relative(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.root))

    def _event(self, event_type: str, text: str, **extra: Any) -> None:
        item: dict[str, Any] = {
            "type": event_type,
            "text": text,
            "time": datetime.now(UTC).isoformat(),
        }
        item.update(extra)
        self.console.append(item)

    def _artifact_error(self, artifact: str, exc: Exception) -> None:
        message = f"Failed to save {artifact}: {type(exc).__name__}: {exc}"
        self._event("artifact_error", message, artifact=artifact)
        log.exception(message)

    def attach_console(self, page: Page) -> None:
        page.on(
            "console",
            lambda message: self._event("console", message.text, level=message.type),
        )
        page.on(
            "pageerror",
            lambda error: self._event("pageerror", str(error)),
        )

    async def start_trace(self, context: BrowserContext) -> None:
        if not settings.fragment_runner_trace_enabled:
            return
        try:
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)
            self.trace_started = True
        except Exception as exc:
            self._artifact_error("trace_start", exc)

    @staticmethod
    def _live_page(context: BrowserContext, preferred: Page) -> Page | None:
        try:
            if not preferred.is_closed():
                return preferred
        except Exception:
            pass
        for candidate in reversed(context.pages):
            try:
                if not candidate.is_closed():
                    return candidate
            except Exception:
                continue
        return None

    async def _save_screenshot(self, page: Page, path: Path) -> bool:
        try:
            await page.screenshot(path=str(path), full_page=True, timeout=15_000)
            return True
        except Exception as first_exc:
            self._artifact_error("failure_full_page_screenshot", first_exc)
        try:
            await page.screenshot(path=str(path), full_page=False, timeout=15_000)
            return True
        except Exception as second_exc:
            self._artifact_error("failure_viewport_screenshot", second_exc)
            return False

    async def finish(
        self, context: BrowserContext, page: Page, *, failed: bool
    ) -> ArtifactSet:
        result = ArtifactSet()
        live_page = self._live_page(context, page)

        if failed and settings.fragment_runner_screenshot_enabled:
            path = self.directory / "failure.png"
            if live_page is None:
                self._event(
                    "artifact_error",
                    "Failed to save screenshot: no open Playwright page remained",
                    artifact="failure_screenshot",
                )
            elif await self._save_screenshot(live_page, path):
                result.screenshot_path = self.relative(path)

        if failed and settings.fragment_runner_html_snapshot_enabled:
            path = self.directory / "page.html"
            if live_page is None:
                self._event(
                    "artifact_error",
                    "Failed to save HTML snapshot: no open Playwright page remained",
                    artifact="page_html",
                )
            else:
                try:
                    path.write_text(await live_page.content(), encoding="utf-8")
                    result.html_path = self.relative(path)
                except Exception as exc:
                    self._artifact_error("page_html", exc)

        if self.trace_started:
            path = self.directory / ("failure-trace.zip" if failed else "trace.zip")
            try:
                await context.tracing.stop(path=str(path))
                result.trace_path = self.relative(path)
            except Exception as exc:
                self._artifact_error("failure_trace" if failed else "trace", exc)
            finally:
                self.trace_started = False

        # Always write console.json after all artifact attempts so screenshot/HTML/
        # trace failures are visible instead of being silently swallowed.
        path = self.directory / "console.json"
        try:
            path.write_text(
                json.dumps(self.console, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result.console_path = self.relative(path)
        except Exception as exc:
            log.exception("Failed to save console artifact: %s", exc)

        return result
