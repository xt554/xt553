from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import Locator, Page

from core.config import settings


@dataclass(frozen=True)
class ResolvedTarget:
    selector: str
    match_index: int
    frame_index: int
    frame_url: str
    source: str = "selector"

    def as_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "match_index": self.match_index,
            "frame_index": self.frame_index,
            "frame_url": self.frame_url,
            "source": self.source,
        }

    def locator(self, page: Page) -> Locator:
        frames = page.frames
        if not frames:
            raise RuntimeError("Page has no frames")
        frame_index = min(self.frame_index, len(frames) - 1)
        frame = frames[frame_index]
        if self.source == "text_exact":
            return frame.get_by_text(self.selector, exact=True).nth(self.match_index)
        if self.source == "text_contains":
            return frame.get_by_text(self.selector, exact=False).nth(self.match_index)
        return frame.locator(self.selector).nth(self.match_index)


@dataclass
class SelectorCheck:
    ok: bool
    resolved: dict[str, Any]
    missing: list[str]
    targets: dict[str, ResolvedTarget] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "resolved": self.resolved, "missing": self.missing}


class SelectorRegistry:
    def __init__(self, path: str | Path | None = None):
        source = Path(path or settings.fragment_runner_selector_file)
        self.data: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
        if settings.fragment_runner_username_selector:
            self.data["username"] = [settings.fragment_runner_username_selector] + list(
                self.data.get("username", [])
            )
        if settings.fragment_runner_continue_selector:
            self.data["continue"] = [settings.fragment_runner_continue_selector] + list(
                self.data.get("continue", [])
            )
        if settings.fragment_runner_login_required_selector:
            self.data["login_required"] = [settings.fragment_runner_login_required_selector] + list(
                self.data.get("login_required", [])
            )
        if settings.fragment_runner_logged_in_selector:
            self.data["logged_in"] = [settings.fragment_runner_logged_in_selector] + list(
                self.data.get("logged_in", [])
            )

    def candidates(self, key: str, months: int | None = None) -> list[str]:
        if key == "months":
            configured = self.data.get("months", {}).get(str(months), [])
            if settings.fragment_runner_months_selector_template and months:
                return [settings.fragment_runner_months_selector_template.format(months=months)] + list(
                    configured
                )
            return list(configured)
        return list(self.data.get(key, []))

    @staticmethod
    async def _visible_match_count(locator: Locator) -> list[int]:
        visible: list[int] = []
        count = await locator.count()
        # A selector accidentally matching the entire page should not make the
        # self-check unbounded. Fragment currently has only a handful of duplicates.
        for index in range(min(count, 100)):
            try:
                if await locator.nth(index).is_visible():
                    visible.append(index)
            except Exception:
                continue
        return visible

    async def first_visible(
        self,
        page: Page,
        candidates: list[str],
    ) -> ResolvedTarget | None:
        # Search every frame and every matched node. The previous implementation
        # used locator.first, which produced false negatives whenever Fragment kept
        # a hidden responsive duplicate before the visible card.
        for frame_index, frame in enumerate(page.frames):
            for selector in candidates:
                try:
                    locator = frame.locator(selector)
                    visible = await self._visible_match_count(locator)
                    if visible:
                        return ResolvedTarget(
                            selector=selector,
                            match_index=visible[0],
                            frame_index=frame_index,
                            frame_url=frame.url,
                        )
                except Exception:
                    continue
        return None

    async def first_visible_text(
        self,
        page: Page,
        labels: list[str],
    ) -> ResolvedTarget | None:
        # Semantic fallback for Fragment cards whose clickable wrapper changes but
        # whose user-visible action label remains stable.
        for exact in (True, False):
            for frame_index, frame in enumerate(page.frames):
                for label in labels:
                    try:
                        locator = frame.get_by_text(label, exact=exact)
                        visible = await self._visible_match_count(locator)
                        if visible:
                            return ResolvedTarget(
                                selector=label,
                                match_index=visible[0],
                                frame_index=frame_index,
                                frame_url=frame.url,
                                source="text_exact" if exact else "text_contains",
                            )
                    except Exception:
                        continue
        return None

    async def wait_first_visible(
        self,
        page: Page,
        candidates: list[str],
        *,
        timeout_ms: int = 10_000,
        poll_ms: int = 250,
    ) -> ResolvedTarget | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout_ms / 1000)
        while loop.time() < deadline:
            resolved = await self.first_visible(page, candidates)
            if resolved:
                return resolved
            await page.wait_for_timeout(poll_ms)
        return None

    async def wait_visible_text(
        self,
        page: Page,
        labels: list[str],
        *,
        timeout_ms: int = 10_000,
        poll_ms: int = 250,
    ) -> ResolvedTarget | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout_ms / 1000)
        while loop.time() < deadline:
            resolved = await self.first_visible_text(page, labels)
            if resolved:
                return resolved
            await page.wait_for_timeout(poll_ms)
        return None

    async def click(self, page: Page, target: ResolvedTarget, *, timeout_ms: int = 10_000) -> None:
        locator = target.locator(page)
        try:
            await locator.click(timeout=timeout_ms)
            return
        except Exception:
            # Some Fragment layouts attach the navigation handler to a parent card
            # while the text is rendered in a nested heading. Click the closest
            # interactive ancestor, or a nested interactive child as a fallback.
            await locator.evaluate(
                """
                element => {
                    const interactive =
                        element.closest('a,button,[role="button"],[onclick]') ||
                        element.querySelector('a,button,[role="button"],[onclick]') ||
                        element;
                    interactive.click();
                }
                """
            )

    async def fill(self, page: Page, target: ResolvedTarget, value: str) -> None:
        await target.locator(page).fill(value)

    async def login_required(self, page: Page) -> bool:
        if "/login" in page.url.lower():
            return True
        return bool(await self.first_visible(page, self.candidates("login_required")))

    async def open_purchase_form(self, page: Page) -> tuple[Page, SelectorCheck]:
        """Open the actual Premium purchase form from Fragment's action landing page."""
        username = await self.wait_first_visible(
            page,
            self.candidates("username"),
            timeout_ms=3_000,
        )
        if username:
            return page, SelectorCheck(
                ok=True,
                resolved={"username": username.as_dict()},
                missing=[],
                targets={"username": username},
            )

        # Fragment hydrates the action card after DOMContentLoaded. Wait for it,
        # instead of checking only once immediately after navigation.
        entry = await self.wait_first_visible(
            page,
            self.candidates("premium_entry"),
            timeout_ms=20_000,
        )
        if not entry:
            entry = await self.wait_visible_text(
                page,
                ["Buy Telegram Premium", "购买 Telegram Premium"],
                timeout_ms=5_000,
            )
        if not entry:
            return page, SelectorCheck(ok=False, resolved={}, missing=["premium_entry"])

        pages_before = list(page.context.pages)
        try:
            await self.click(page, entry, timeout_ms=10_000)
            await page.wait_for_timeout(1_000)
        except Exception:
            return page, SelectorCheck(
                ok=False,
                resolved={"premium_entry": entry.as_dict()},
                missing=["purchase_form_navigation"],
                targets={"premium_entry": entry},
            )

        # Handle both same-tab navigation and a newly opened page.
        current_page = page
        new_pages = [candidate for candidate in page.context.pages if candidate not in pages_before]
        if new_pages:
            current_page = new_pages[-1]
            with suppress(Exception):
                await current_page.wait_for_load_state("domcontentloaded", timeout=15_000)

        username = await self.wait_first_visible(
            current_page,
            self.candidates("username"),
            timeout_ms=20_000,
        )
        if not username:
            return current_page, SelectorCheck(
                ok=False,
                resolved={"premium_entry": entry.as_dict()},
                missing=["username_after_entry"],
                targets={"premium_entry": entry},
            )

        return current_page, SelectorCheck(
            ok=True,
            resolved={
                "premium_entry": entry.as_dict(),
                "username": username.as_dict(),
            },
            missing=[],
            targets={"premium_entry": entry, "username": username},
        )

    async def check_username_page(self, page: Page) -> SelectorCheck:
        username = await self.first_visible(page, self.candidates("username"))
        if not username:
            return SelectorCheck(ok=False, resolved={}, missing=["username"])
        return SelectorCheck(
            ok=True,
            resolved={"username": username.as_dict()},
            missing=[],
            targets={"username": username},
        )

    async def check_months_page(self, page: Page, months: int) -> SelectorCheck:
        resolved: dict[str, Any] = {}
        targets: dict[str, ResolvedTarget] = {}
        missing: list[str] = []
        month_target = await self.first_visible(page, self.candidates("months", months))
        if month_target:
            resolved["months"] = month_target.as_dict()
            targets["months"] = month_target
        else:
            missing.append("months")
        continue_target = await self.first_visible(page, self.candidates("continue"))
        if continue_target:
            resolved["continue"] = continue_target.as_dict()
            targets["continue"] = continue_target
        else:
            missing.append("continue")
        return SelectorCheck(
            ok=not missing,
            resolved=resolved,
            missing=missing,
            targets=targets,
        )

    async def check_purchase_page(self, page: Page, months: int) -> SelectorCheck:
        resolved: dict[str, Any] = {}
        targets: dict[str, ResolvedTarget] = {}
        missing: list[str] = []
        for key in ("username", "months", "continue"):
            target = await self.first_visible(page, self.candidates(key, months))
            if target:
                resolved[key] = target.as_dict()
                targets[key] = target
            else:
                missing.append(key)
        return SelectorCheck(
            ok=not missing,
            resolved=resolved,
            missing=missing,
            targets=targets,
        )
