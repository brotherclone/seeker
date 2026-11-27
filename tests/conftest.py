"""Suite-wide isolation: tests never read Gabe's real macOS Keychain, and never follow a
schedule workspace set in his shell."""

import pytest

from seeker.config import Keychain


@pytest.fixture(autouse=True)
def no_real_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Keychain, "get", lambda self: None)


@pytest.fixture(autouse=True)
def no_real_schedule_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEEKER_SCHEDULE_WORKSPACE", raising=False)
