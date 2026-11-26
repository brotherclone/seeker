"""Suite-wide isolation: tests never read Gabe's real macOS Keychain."""

import pytest

from seeker.config import Keychain


@pytest.fixture(autouse=True)
def no_real_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Keychain, "get", lambda self: None)
