from collections.abc import Iterator

import pytest

from secops_dispatcher.config import Settings


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the developer's environment out of the tests, which assert on default settings.

    Both a local .env and exported variables (a shell that has `GITHUB_PROJECT_TOKEN` set, say)
    would otherwise change the settings under test.
    """
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    original = Settings.model_config["env_file"]
    Settings.model_config["env_file"] = None
    yield
    Settings.model_config["env_file"] = original
