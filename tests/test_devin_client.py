import httpx
import pytest

from secops_dispatcher.config import Settings
from secops_dispatcher.devin_client import DevinApiError, DevinDispatcher
from secops_dispatcher.models import VulnerabilityIssue

ISSUE = VulnerabilityIssue(
    repo="vandenplas/superset",
    number=7,
    title="CVE-2025-0001: urllib3 request smuggling",
    url="https://github.com/vandenplas/superset/issues/7",
    body="urllib3 < 2.5.0 is vulnerable; upgrade to 2.5.0.",
)


ORG = "org-1234"


def make_dispatcher(handler, **overrides) -> DevinDispatcher:
    settings = Settings(devin_api_key="cog_test_key", devin_org_id=ORG, **overrides)
    client = httpx.Client(
        base_url=settings.devin_api_base_url,
        headers={"Authorization": f"Bearer {settings.devin_api_key}"},
        transport=httpx.MockTransport(handler),
    )
    return DevinDispatcher(settings, client=client)


def test_requires_api_key() -> None:
    with pytest.raises(ValueError, match="DEVIN_API_KEY"):
        DevinDispatcher(Settings(devin_api_key="", devin_org_id=ORG))


def test_requires_org_id() -> None:
    with pytest.raises(ValueError, match="DEVIN_ORG_ID"):
        DevinDispatcher(Settings(devin_api_key="cog_test_key", devin_org_id=""))


def test_posts_session_request_and_returns_session_id() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers["Authorization"]
        captured["json"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "session_id": "devin-abc123",
                "url": "https://app.devin.ai/sessions/abc123",
                "is_new_session": True,
            },
        )

    assert make_dispatcher(handler).dispatch(ISSUE) == "devin-abc123"
    assert captured["url"] == f"https://api.devin.ai/v3/organizations/{ORG}/sessions"
    assert captured["auth"] == "Bearer cog_test_key"

    payload = captured["json"]
    assert payload["repos"] == ["vandenplas/superset"]
    assert payload["title"] == "Remediate vandenplas/superset#7: " + ISSUE.title
    assert payload["tags"] == ["secops-dispatcher", "vulnerability"]
    assert "playbook_id" not in payload
    assert "max_acu_limit" not in payload
    assert "create_as_user_id" not in payload

    prompt = payload["prompt"]
    assert ISSUE.url in prompt
    assert "Starting remediation" in prompt
    assert "In Progress" in prompt
    assert "In Review" in prompt
    assert "AGENTS.md" in prompt
    assert "Superset SVM" in prompt
    assert "urllib3 < 2.5.0 is vulnerable" in prompt
    assert "{{" not in prompt


def test_optional_session_tuning_is_forwarded() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"session_id": "devin-1"})

    dispatcher = make_dispatcher(
        handler,
        devin_playbook_id="playbook-xyz",
        devin_max_acu_limit=25,
        devin_create_as_user_id="user-42",
    )
    dispatcher.dispatch(ISSUE)
    assert captured["json"]["playbook_id"] == "playbook-xyz"
    assert captured["json"]["max_acu_limit"] == 25
    assert captured["json"]["create_as_user_id"] == "user-42"


@pytest.mark.parametrize("status", [401, 429, 500])
def test_api_errors_raise(status: int) -> None:
    dispatcher = make_dispatcher(lambda request: httpx.Response(status, json={"detail": "nope"}))
    with pytest.raises(DevinApiError, match=str(status)):
        dispatcher.dispatch(ISSUE)


def test_transport_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(DevinApiError, match="could not reach the Devin API"):
        make_dispatcher(handler).dispatch(ISSUE)


def test_response_without_session_id_raises() -> None:
    dispatcher = make_dispatcher(lambda request: httpx.Response(200, json={"url": "x"}))
    with pytest.raises(DevinApiError, match="no session_id"):
        dispatcher.dispatch(ISSUE)


def test_api_key_is_not_in_error_messages() -> None:
    dispatcher = make_dispatcher(
        lambda request: httpx.Response(403, text="forbidden for cog_other_key")
    )
    with pytest.raises(DevinApiError) as excinfo:
        dispatcher.dispatch(ISSUE)
    assert "cog_test_key" not in str(excinfo.value)
