from fastapi.testclient import TestClient

from secops_dispatcher.app import create_app
from secops_dispatcher.config import Settings


def make_client() -> TestClient:
    settings = Settings(devin_api_key="secret-key", github_webhook_secret="secret-hook")
    return TestClient(create_app(settings))


def test_healthz() -> None:
    assert make_client().get("/healthz").json() == {"status": "ok"}


def test_config_endpoint_redacts_secrets() -> None:
    body = make_client().get("/config").json()
    assert body["devin_api_key_set"] is True
    assert body["github_webhook_secret_set"] is True
    assert "devin_api_key" not in body
    assert "github_webhook_secret" not in body


def test_defaults() -> None:
    settings = Settings()
    assert settings.target_repo == "vandenplas/superset"
    assert settings.vulnerability_label == "vulnerability"
