import pytest

from secops_dispatcher.config import Settings


@pytest.fixture(autouse=True)
def ignore_dotenv() -> None:
    """Keep a developer's local .env out of the tests, which assert on default settings."""
    original = Settings.model_config["env_file"]
    Settings.model_config["env_file"] = None
    yield
    Settings.model_config["env_file"] = original
