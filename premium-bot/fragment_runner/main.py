
from __future__ import annotations

import asyncio
import logging
import os
import socket
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from core.config import settings
from fragment_runner.alerts import AlertManager
from fragment_runner.artifacts import ArtifactRecorder, ArtifactSet
from fragment_runner.client import RunnerApiClient
from fragment_runner.errors import LoginRequired, RunnerFailure, SelectorFailure
from fragment_runner.runtime import RuntimeState
from fragment_runner.selectors import SelectorCheck, SelectorRegistry

log = logging.getLogger("fragment_runner")
logging.basicConfig(level=settings.log_level)
RUNNER_ID = os.getenv("FRAGMENT_RUNNER_ID", socket.gethostname())


class ProductionRunner:
    def __init__(self) -> None:
        self.api = RunnerApiClient()
        self.runtime = RuntimeState()
        self.alerts = AlertManager()
        self.selectors = SelectorRegistry()
        self.current_job: dict[str, Any] | None = None
        self.page_url: str | None = None
        self.browser_healthy = False
        self.api_healthy = False
        self.fragment_reachable = False
        self.login_status = "UNKNOWN"
        self.selector_status = "UNKNOWN"
        self.last_error: str | None = None
        self.status_value = "STARTING"
        self.stop = asyncio.Event()

    def status_payload(self) -> dict[str, Any]:
        return {
            "runner_id": RUNNER_ID,
            "status": self.status_value,
            "mode": settings.fragment_runner_mode,
            "version": settings.fragment_runner_version,
            "browser_healthy": self.browser_healthy,
            "api_healthy": self.api_healthy,
            "fragment_reachable": self.fragment_reachable,
            "login_status": self.login_status,
            "selector_status": self.selector_status,
            "current_job_id": self.current_job.get("id") if self.current_job else None,
            "current_account_code": self.current_job.get("account_code") if self.current_job else None,
            "page_url": self.page_url,
            "last_error": self.last_error,
            "metadata": {"pid": os.getpid(), "hostname": socket.gethostname()},
        }

    async def publish_status(self) -> None:
        self.runtime.update(**self.status_payload())
        try:
            await self.api.status(self.status_payload())
            self.api_healthy = True
            self.runtime.update(**self.status_payload())
        except Exception:
            self.api_healthy = False
            self.runtime.update(**self.status_payload())
            log.exception("Failed to publish runner status")

    async def status_loop(self) -> None:
        while not self.stop.is_set():
            await self.publish_status()
            try:
                await asyncio.wait_for(
                    self.stop.wait(), timeout=settings.fragment_runner_heartbeat_seconds
                )
            except TimeoutError:
                pass

    async def job_heartbeat(self, job_id: str) -> None:
        while self.current_job and self.current_job.get("id") == job_id:
            try:
                response = await self.api.request(
                    "POST",
                    f"/{job_id}/heartbeat",
                    json={"runner_id": RUNNER_ID, "page_url": self.page_url},
                )
                response.raise_for_status()
                self.api_healthy = True
            except Exception:
                self.api_healthy = False
                log.exception("Job heartbeat failed: %s", job_id)
            await asyncio.sleep(max(5, settings.fragment_runner_heartbeat_seconds))

    async def capture_from_page(self, page: Page) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + settings.fragment_runner_timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            value = await page.evaluate(
                "() => window.__drainFragmentTonCaptures ? window.__drainFragmentTonCaptures() : []"
            )
            if value:
                item = value[-1]
                return item.get("request") or item.get("payload") or item
            await asyncio.sleep(1)
        raise RunnerFailure(
            "TON Connect request was not captured",
            kind="CAPTURE_TIMEOUT",
            retryable=True,
        )

    async def save_storage_state(self, context: BrowserContext, profile_dir: Path) -> None:
        path = profile_dir / "storage_state.json"
        await context.storage_state(path=str(path))

    async def interact(
        self,
        page: Page,
        job: dict[str, Any],
        selector_snapshot: dict[str, Any],
    ) -> None:
        username_check = await self.selectors.check_username_page(page)
        selector_snapshot["username_stage"] = username_check.as_dict()
        if not username_check.ok:
            raise SelectorFailure(
                f"Fragment username stage self-check failed: {', '.join(username_check.missing)}"
            )

        self.selector_status = "OK"
        if settings.fragment_runner_mode.lower() == "observe":
            raise RunnerFailure(
                "Runner observe mode: Premium entry and username form verified; automatic interaction is disabled",
                kind="OBSERVE_MODE",
                retryable=False,
                manual_review=True,
            )

        await self.selectors.fill(
            page,
            username_check.targets["username"],
            job["target_username"].lstrip("@"),
        )

        # Some Fragment layouts show the month choices immediately. Others require
        # a harmless Next/Continue step after resolving the Telegram username.
        month_selector = await self.selectors.wait_first_visible(
            page,
            self.selectors.candidates("months", job["months"]),
            timeout_ms=2_000,
        )
        if not month_selector:
            step_continue = await self.selectors.wait_first_visible(
                page,
                self.selectors.candidates("continue"),
                timeout_ms=8_000,
            )
            if not step_continue:
                raise SelectorFailure(
                    "Fragment username stage has neither month options nor a Continue button"
                )
            selector_snapshot["username_continue"] = step_continue.as_dict()
            await self.selectors.click(page, step_continue, timeout_ms=10_000)
            await page.wait_for_timeout(750)
            month_selector = await self.selectors.wait_first_visible(
                page,
                self.selectors.candidates("months", job["months"]),
                timeout_ms=15_000,
            )

        if not month_selector:
            raise SelectorFailure(
                f"Fragment month selector is missing for {job['months']} months"
            )
        selector_snapshot["months"] = month_selector.as_dict()
        await self.selectors.click(page, month_selector, timeout_ms=10_000)

        final_continue = await self.selectors.wait_first_visible(
            page,
            self.selectors.candidates("continue"),
            timeout_ms=10_000,
        )
        if not final_continue:
            raise SelectorFailure("Fragment final Continue/Buy button is missing")
        selector_snapshot["final_continue"] = final_continue.as_dict()

        if not settings.fragment_runner_auto_click:
            raise RunnerFailure(
                "FRAGMENT_RUNNER_AUTO_CLICK=false; final purchase click is disabled",
                kind="AUTO_CLICK_DISABLED",
                retryable=False,
                manual_review=True,
            )
        await self.selectors.click(page, final_continue, timeout_ms=10_000)

    async def report_failure(
        self,
        job: dict[str, Any],
        exc: Exception,
        artifacts: ArtifactSet,
        selector_snapshot: dict[str, Any] | None,
    ) -> None:
        failure = exc if isinstance(exc, RunnerFailure) else RunnerFailure(
            str(exc), kind="BROWSER_OR_NETWORK", retryable=True
        )
        self.last_error = str(failure)
        if self.status_value not in {"LOGIN_REQUIRED", "SELECTOR_ERROR"}:
            self.status_value = "DEGRADED" if failure.retryable else "ERROR"
        response = await self.api.request(
            "POST",
            f"/{job['id']}/fail",
            json={
                "runner_id": RUNNER_ID,
                "error": str(failure),
                "manual_review": failure.manual_review,
                "retryable": failure.retryable,
                "failure_kind": failure.kind,
                "page_url": self.page_url,
                "selector_snapshot": selector_snapshot,
                **artifacts.as_payload(),
            },
        )
        response.raise_for_status()
        log.error(
            "Fragment job failed: %s",
            job["id"],
            exc_info=(type(exc), exc, exc.__traceback__),
        )

    async def execute(self, job: dict[str, Any]) -> None:
        profile_dir = Path(settings.fragment_runner_profile_dir) / job["profile_name"]
        profile_dir.mkdir(parents=True, exist_ok=True)
        recorder = ArtifactRecorder(job["id"])
        context: BrowserContext | None = None
        page: Page | None = None
        artifacts = ArtifactSet()
        selector_snapshot: dict[str, Any] | None = None
        failure_report_started = False
        heartbeat = asyncio.create_task(self.job_heartbeat(job["id"]))
        try:
            async with async_playwright() as pw:
                try:
                    context = await pw.chromium.launch_persistent_context(
                        str(profile_dir),
                        headless=settings.fragment_runner_headless,
                    )
                    self.browser_healthy = True
                    page = context.pages[0] if context.pages else await context.new_page()
                    recorder.attach_console(page)
                    await recorder.start_trace(context)
                    hook = Path("/app/browser/fragment_hook.js").read_text(encoding="utf-8")
                    await context.add_init_script(hook)
                    url = (
                        settings.fragment_runner_base_url.rstrip("/")
                        + settings.fragment_runner_purchase_path
                    )
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=settings.fragment_runner_timeout_seconds * 1000,
                    )
                    self.page_url = page.url
                    self.fragment_reachable = True
                    if await self.selectors.login_required(page):
                        self.login_status = "LOGIN_REQUIRED"
                        self.status_value = "LOGIN_REQUIRED"
                        await self.alerts.send(
                            f"login:{job['account_code']}",
                            f"⚠ Fragment 账号 {job['account_display_name']} 登录已失效。\nRunner: {RUNNER_ID}\n页面: {page.url}",
                        )
                        raise LoginRequired()
                    self.login_status = "OK"
                    await self.save_storage_state(context, profile_dir)

                    # Fragment /premium currently opens on an action landing card.
                    # Enter the purchase form before checking username/months/continue.
                    page, entry_check = await self.selectors.open_purchase_form(page)
                    recorder.attach_console(page)
                    self.page_url = page.url
                    selector_snapshot = {"entry": entry_check.as_dict()}
                    if not entry_check.ok:
                        self.selector_status = "FAILED"
                        self.status_value = "SELECTOR_ERROR"
                        await self.alerts.send(
                            "selector:premium-entry",
                            "⚠ Fragment Premium 入口或表单导航自检失败。\n"
                            f"缺失: {', '.join(entry_check.missing)}\n页面: {page.url}",
                        )
                        raise SelectorFailure(
                            f"Fragment premium entry self-check failed: {', '.join(entry_check.missing)}"
                        )

                    await self.interact(page, job, selector_snapshot)
                    request = await self.capture_from_page(page)
                    params = request.get("params", request)
                    amount = int((params.get("messages") or [{}])[0].get("amount", 0))
                    if amount <= 0:
                        raise RunnerFailure(
                            "Captured request has no valid amount",
                            kind="INVALID_CAPTURE",
                            retryable=False,
                            manual_review=True,
                        )
                    artifacts = await recorder.finish(context, page, failed=False)
                    response = await self.api.request(
                        "POST",
                        f"/{job['id']}/capture",
                        json={
                            "runner_id": RUNNER_ID,
                            "request": request,
                            "expected_amount_nano": amount,
                            "page_url": page.url,
                            "selector_snapshot": selector_snapshot,
                            **artifacts.as_payload(),
                        },
                    )
                    response.raise_for_status()
                    self.status_value = "ONLINE"
                    self.last_error = None
                    log.info("Captured job=%s result=%s", job["id"], response.text)
                except Exception as exc:
                    # Capture diagnostics before leaving async_playwright(). Exiting the
                    # Playwright context closes every page/browser target, which previously
                    # caused TargetClosedError for screenshot, HTML and trace recording.
                    if context and page:
                        failure_artifacts = await recorder.finish(
                            context, page, failed=True
                        )
                        failure_artifacts.trace_path = (
                            failure_artifacts.trace_path or artifacts.trace_path
                        )
                        failure_artifacts.console_path = (
                            failure_artifacts.console_path or artifacts.console_path
                        )
                        artifacts = failure_artifacts
                    failure_report_started = True
                    await self.report_failure(
                        job, exc, artifacts, selector_snapshot
                    )
                finally:
                    if context:
                        with suppress(Exception):
                            await context.close()
        except Exception as exc:
            # Covers failures while entering Playwright itself or while reporting the
            # original failure. Do not submit the same job failure twice.
            if not failure_report_started:
                await self.report_failure(job, exc, artifacts, selector_snapshot)
            else:
                log.error(
                    "Failure reporting or Playwright teardown failed for job=%s",
                    job["id"],
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
        finally:
            self.current_job = None
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            self.browser_healthy = False
            if self.status_value not in {"LOGIN_REQUIRED", "SELECTOR_ERROR"}:
                self.status_value = "IDLE"
            await self.publish_status()

    async def run(self) -> None:
        if not settings.fragment_runner_enabled:
            log.warning("FRAGMENT_RUNNER_ENABLED=false; runner is idle")
        self.status_value = "IDLE"
        status_task = asyncio.create_task(self.status_loop())
        try:
            while not self.stop.is_set():
                if not settings.fragment_runner_enabled:
                    self.status_value = "IDLE"
                    await asyncio.sleep(settings.fragment_runner_poll_seconds)
                    continue
                try:
                    response = await self.api.request(
                        "POST", "/claim", json={"runner_id": RUNNER_ID}
                    )
                    self.api_healthy = True
                    if response.status_code == 204:
                        self.status_value = "IDLE"
                        await asyncio.sleep(settings.fragment_runner_poll_seconds)
                        continue
                    response.raise_for_status()
                    self.current_job = response.json()
                    self.status_value = "BUSY"
                    await self.publish_status()
                    await self.execute(self.current_job)
                except Exception as exc:
                    self.api_healthy = False
                    self.status_value = "ERROR"
                    self.last_error = str(exc)
                    self.runtime.update(**self.status_payload())
                    log.exception("Runner loop error")
                    await asyncio.sleep(settings.fragment_runner_poll_seconds)
        finally:
            self.stop.set()
            status_task.cancel()
            with suppress(asyncio.CancelledError):
                await status_task
            await self.api.close()


async def main() -> None:
    await ProductionRunner().run()


if __name__ == "__main__":
    asyncio.run(main())
