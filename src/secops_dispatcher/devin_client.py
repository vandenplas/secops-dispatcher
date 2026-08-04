import logging

import httpx

from .config import Settings
from .models import VulnerabilityIssue
from .playbook import render_prompt

logger = logging.getLogger(__name__)


class DevinApiError(RuntimeError):
    """Raised when the Devin API does not accept a session request."""


class DevinDispatcher:
    """Starts a Devin session that remediates the vulnerability described by an issue."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.devin_api_key:
            raise ValueError("DEVIN_API_KEY is required to dispatch to the Devin API")
        if not settings.devin_org_id:
            raise ValueError("DEVIN_ORG_ID is required to dispatch to the Devin API")
        self._settings = settings
        self._client = client or httpx.Client(
            base_url=settings.devin_api_base_url,
            headers={"Authorization": f"Bearer {settings.devin_api_key}"},
            timeout=settings.devin_request_timeout_seconds,
        )

    @property
    def sessions_path(self) -> str:
        return f"/v3/organizations/{self._settings.devin_org_id}/sessions"

    def dispatch(self, issue: VulnerabilityIssue) -> str:
        settings = self._settings
        payload: dict[str, object] = {
            "prompt": render_prompt(issue, settings),
            "title": f"Remediate {issue.key}: {issue.title}",
            "tags": ["secops-dispatcher", "vulnerability"],
            "repos": [issue.repo],
        }
        if settings.devin_playbook_id:
            payload["playbook_id"] = settings.devin_playbook_id
        if settings.devin_max_acu_limit is not None:
            payload["max_acu_limit"] = settings.devin_max_acu_limit
        # Attribute the session to a human so it shows up in their session list.
        if settings.devin_create_as_user_id:
            payload["create_as_user_id"] = settings.devin_create_as_user_id

        try:
            response = self._client.post(self.sessions_path, json=payload)
        except httpx.HTTPError as exc:
            raise DevinApiError(f"could not reach the Devin API: {exc}") from exc

        if response.status_code >= 400:
            # The body can echo the prompt but never the API key, which only travels in the header.
            raise DevinApiError(f"Devin API returned {response.status_code}: {response.text[:500]}")

        body = response.json()
        session_id = body.get("session_id")
        if not session_id:
            raise DevinApiError(f"Devin API response has no session_id: {body}")

        logger.info(
            "dispatched %s to Devin session %s (%s)", issue.key, session_id, body.get("url", "")
        )
        return session_id

    def close(self) -> None:
        self._client.close()
