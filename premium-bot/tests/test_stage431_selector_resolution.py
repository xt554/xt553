from __future__ import annotations

from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from core.config import settings
from fragment_runner.selectors import SelectorRegistry


@pytest.fixture
def selector_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "selectors.json"
    source.write_text(
        '{"premium_entry":["text=Buy Telegram Premium"],'
        '"username":["input[name=username]"],'
        '"months":{"3":["button:has-text(\\"3 months\\")"]},'
        '"continue":["button:has-text(\\"Continue\\")"],'
        '"login_required":[],"logged_in":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "fragment_runner_username_selector", "")
    monkeypatch.setattr(settings, "fragment_runner_continue_selector", "")
    monkeypatch.setattr(settings, "fragment_runner_months_selector_template", "")
    monkeypatch.setattr(settings, "fragment_runner_login_required_selector", "")
    monkeypatch.setattr(settings, "fragment_runner_logged_in_selector", "")
    return source


@pytest.mark.asyncio
async def test_visible_duplicate_is_selected_instead_of_hidden_first(selector_file: Path) -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        page = await browser.new_page()
        await page.set_content(
            """
            <a style='display:none'>Buy Telegram Premium</a>
            <a id='visible-entry'>Buy Telegram Premium</a>
            """
        )
        registry = SelectorRegistry(selector_file)
        target = await registry.first_visible(page, registry.candidates("premium_entry"))
        assert target is not None
        assert target.match_index == 1
        assert await target.locator(page).get_attribute("id") == "visible-entry"
        await browser.close()


@pytest.mark.asyncio
async def test_purchase_entry_can_be_found_in_iframe(selector_file: Path) -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        page = await browser.new_page()
        await page.set_content(
            """
            <iframe srcdoc="<a id='frame-entry'>Buy Telegram Premium</a>"></iframe>
            """
        )
        registry = SelectorRegistry(selector_file)
        target = await registry.wait_first_visible(
            page,
            registry.candidates("premium_entry"),
            timeout_ms=3_000,
        )
        assert target is not None
        assert target.frame_index == 1
        assert await target.locator(page).get_attribute("id") == "frame-entry"
        await browser.close()
