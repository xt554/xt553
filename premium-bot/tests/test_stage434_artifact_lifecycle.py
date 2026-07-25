from __future__ import annotations

from pathlib import Path


MAIN = Path(__file__).resolve().parents[1] / "fragment_runner" / "main.py"


def test_failure_artifacts_are_recorded_before_browser_close() -> None:
    source = MAIN.read_text(encoding="utf-8")
    finish_index = source.index("failure_artifacts = await recorder.finish")
    close_index = source.index("await context.close()", finish_index)
    assert finish_index < close_index


def test_execute_uses_inner_exception_handler_inside_playwright_scope() -> None:
    source = MAIN.read_text(encoding="utf-8")
    assert "async with async_playwright() as pw:\n                try:" in source
    assert "Capture diagnostics before leaving async_playwright()" in source
