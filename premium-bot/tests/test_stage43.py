
from pathlib import Path

from core.config import settings
from database.enums import FragmentJobStatus
from fragment_runner.selectors import SelectorRegistry
from services.fragment_jobs import retry_delay


def test_stage43_statuses_exist() -> None:
    assert FragmentJobStatus.RETRY_WAIT.value == "RETRY_WAIT"
    assert FragmentJobStatus.LOGIN_REQUIRED.value == "LOGIN_REQUIRED"
    assert FragmentJobStatus.SELECTOR_ERROR.value == "SELECTOR_ERROR"


def test_retry_delay_is_exponential_and_capped(monkeypatch) -> None:
    monkeypatch.setattr(settings, "fragment_runner_retry_base_seconds", 10)
    monkeypatch.setattr(settings, "fragment_runner_retry_max_seconds", 60)
    assert retry_delay(1) == 10
    assert retry_delay(2) == 20
    assert retry_delay(3) == 40
    assert retry_delay(4) == 60
    assert retry_delay(10) == 60


def test_account_parser(monkeypatch) -> None:
    monkeypatch.setattr(settings, "fragment_runner_accounts", "one=profile-one,two=profile-two")
    assert settings.fragment_runner_account_list == [
        ("one", "profile-one"),
        ("two", "profile-two"),
    ]


def test_selector_registry_loads_required_groups(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "selectors.json"
    source.write_text(
        '{"premium_entry":["#entry"],"username":["#u"],"months":{"3":["#m"]},"continue":["#c"],"login_required":[],"logged_in":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "fragment_runner_username_selector", "")
    monkeypatch.setattr(settings, "fragment_runner_continue_selector", "")
    monkeypatch.setattr(settings, "fragment_runner_months_selector_template", "")
    monkeypatch.setattr(settings, "fragment_runner_login_required_selector", "")
    monkeypatch.setattr(settings, "fragment_runner_logged_in_selector", "")
    registry = SelectorRegistry(source)
    assert registry.candidates("premium_entry") == ["#entry"]
    assert registry.candidates("username") == ["#u"]
    assert registry.candidates("months", 3) == ["#m"]
    assert registry.candidates("continue") == ["#c"]
