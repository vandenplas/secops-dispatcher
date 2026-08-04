import json

import pytest
from fastapi.testclient import TestClient

from secops_dispatcher.app import create_app
from secops_dispatcher.config import Settings
from secops_dispatcher.dispatch import DryRunDispatcher
from secops_dispatcher.signature import expected_signature

SECRET = "hook-secret"


@pytest.fixture
def dispatcher() -> DryRunDispatcher:
    return DryRunDispatcher(Settings())


@pytest.fixture
def client(dispatcher: DryRunDispatcher) -> TestClient:
    settings = Settings(github_webhook_secret=SECRET, target_repo="vandenplas/superset")
    return TestClient(create_app(settings, dispatcher))


def issue_payload(
    action: str = "labeled",
    labels: list[str] | None = None,
    added_label: str | None = "vulnerability",
    repo: str = "vandenplas/superset",
    state: str = "open",
    number: int = 42,
) -> dict:
    payload: dict = {
        "action": action,
        "repository": {"full_name": repo},
        "issue": {
            "number": number,
            "title": "CVE-2025-0001 in urllib3",
            "state": state,
            "html_url": f"https://github.com/{repo}/issues/{number}",
            "body": "Upgrade urllib3 to 2.5.0",
            "labels": [{"name": name} for name in (labels or ["vulnerability"])],
        },
    }
    if added_label is not None:
        payload["label"] = {"name": added_label}
    return payload


def post(client: TestClient, payload: dict, event: str = "issues", secret: str = SECRET):
    body = json.dumps(payload).encode()
    return client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": "delivery-1",
            "X-Hub-Signature-256": expected_signature(secret, body),
            "Content-Type": "application/json",
        },
    )


def test_ping_is_acknowledged(client: TestClient) -> None:
    response = post(client, {"zen": "Keep it logically awesome."}, event="ping")
    assert response.status_code == 200
    assert response.json() == {"status": "pong"}


def test_labeled_vulnerability_issue_is_dispatched(
    client: TestClient, dispatcher: DryRunDispatcher
) -> None:
    response = post(client, issue_payload())
    assert response.status_code == 200
    assert response.json()["status"] == "dispatched"
    assert [issue.key for issue in dispatcher.dispatched] == ["vandenplas/superset#42"]
    assert dispatcher.dispatched[0].body == "Upgrade urllib3 to 2.5.0"


def test_opened_issue_with_label_is_dispatched(
    client: TestClient, dispatcher: DryRunDispatcher
) -> None:
    payload = issue_payload(action="opened", added_label=None)
    assert post(client, payload).json()["status"] == "dispatched"
    assert len(dispatcher.dispatched) == 1


def test_missing_signature_is_rejected(client: TestClient, dispatcher: DryRunDispatcher) -> None:
    response = client.post(
        "/webhooks/github", json=issue_payload(), headers={"X-GitHub-Event": "issues"}
    )
    assert response.status_code == 401
    assert dispatcher.dispatched == []


def test_wrong_signature_is_rejected(client: TestClient, dispatcher: DryRunDispatcher) -> None:
    response = post(client, issue_payload(), secret="wrong-secret")
    assert response.status_code == 401
    assert dispatcher.dispatched == []


def test_tampered_body_is_rejected(client: TestClient, dispatcher: DryRunDispatcher) -> None:
    body = json.dumps(issue_payload()).encode()
    response = client.post(
        "/webhooks/github",
        content=body.replace(b"42", b"43"),
        headers={
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": expected_signature(SECRET, body),
        },
    )
    assert response.status_code == 401
    assert dispatcher.dispatched == []


def test_unconfigured_secret_rejects_delivery(dispatcher: DryRunDispatcher) -> None:
    client = TestClient(create_app(Settings(github_webhook_secret=""), dispatcher))
    response = post(client, issue_payload(), secret="anything")
    assert response.status_code == 503
    assert dispatcher.dispatched == []


@pytest.mark.parametrize(
    ("payload", "reason_fragment"),
    [
        (issue_payload(labels=["bug"], added_label="bug"), "not labelled vulnerability"),
        (issue_payload(action="closed"), "not dispatchable"),
        (issue_payload(action="edited"), "not dispatchable"),
        (issue_payload(state="closed"), "issue is closed"),
        (issue_payload(repo="vandenplas/other"), "not the target repo"),
        (
            issue_payload(labels=["vulnerability", "priority"], added_label="priority"),
            "added label priority is not vulnerability",
        ),
    ],
)
def test_non_dispatchable_events_are_ignored(
    client: TestClient, dispatcher: DryRunDispatcher, payload: dict, reason_fragment: str
) -> None:
    response = post(client, payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ignored"
    assert reason_fragment in body["reason"]
    assert dispatcher.dispatched == []


def test_other_event_types_are_ignored(client: TestClient, dispatcher: DryRunDispatcher) -> None:
    response = post(client, {"action": "opened"}, event="pull_request")
    assert response.json()["status"] == "ignored"
    assert dispatcher.dispatched == []


def test_malformed_issues_payload_is_unprocessable(client: TestClient) -> None:
    assert post(client, {"action": "labeled"}).status_code == 422


def test_redelivery_does_not_dispatch_twice(
    client: TestClient, dispatcher: DryRunDispatcher
) -> None:
    payload = issue_payload()
    assert post(client, payload).json()["status"] == "dispatched"
    second = post(client, payload)
    assert second.json() == {"status": "duplicate", "issue": "vandenplas/superset#42"}
    assert len(dispatcher.dispatched) == 1


def test_failed_dispatch_can_be_retried(client: TestClient) -> None:
    class FlakyDispatcher:
        def __init__(self) -> None:
            self.calls = 0

        def dispatch(self, issue):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("devin api unavailable")
            return "session-1"

    flaky = FlakyDispatcher()
    settings = Settings(github_webhook_secret=SECRET)
    retry_client = TestClient(create_app(settings, flaky), raise_server_exceptions=False)

    assert post(retry_client, issue_payload()).status_code == 502
    assert post(retry_client, issue_payload()).json()["status"] == "dispatched"
    assert flaky.calls == 2
