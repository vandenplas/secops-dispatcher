import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

from .config import Settings
from .dispatch import Dispatcher, DispatchLedger, evaluate
from .models import IssueEvent
from .signature import verify_signature

logger = logging.getLogger(__name__)

EVENT_HEADER = "X-GitHub-Event"


def build_router(settings: Settings, dispatcher: Dispatcher, ledger: DispatchLedger) -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/github")
    async def github_webhook(
        request: Request,
        x_github_event: str = Header(default=""),
        x_github_delivery: str = Header(default=""),
        x_hub_signature_256: str | None = Header(default=None),
    ) -> dict[str, object]:
        if not settings.github_webhook_secret:
            logger.error(
                "rejecting delivery %s: GITHUB_WEBHOOK_SECRET is not set", x_github_delivery
            )
            raise HTTPException(status_code=503, detail="webhook secret is not configured")

        body = await request.body()
        if not verify_signature(settings.github_webhook_secret, body, x_hub_signature_256):
            logger.warning("rejecting delivery %s: invalid signature", x_github_delivery)
            raise HTTPException(status_code=401, detail="invalid signature")

        if x_github_event == "ping":
            return {"status": "pong"}

        if x_github_event != "issues":
            return {
                "status": "ignored",
                "reason": f"event {x_github_event or 'unknown'} is not issues",
            }

        try:
            event = IssueEvent.model_validate_json(body)
        except ValidationError as exc:
            logger.warning("rejecting delivery %s: unparsable issues payload", x_github_delivery)
            raise HTTPException(status_code=422, detail="unparsable issues payload") from exc

        decision = evaluate(event, settings)
        if not decision.dispatch or decision.issue is None:
            logger.info(
                "skipping %s#%s (%s): %s",
                event.repository.full_name,
                event.issue.number,
                event.action,
                decision.reason,
            )
            return {"status": "ignored", "reason": decision.reason}

        issue = decision.issue
        if not ledger.claim(issue):
            logger.info("skipping %s: already dispatched", issue.key)
            return {"status": "duplicate", "issue": issue.key}

        try:
            session_id = dispatcher.dispatch(issue)
        except Exception:
            ledger.release(issue)
            logger.exception("dispatch failed for %s", issue.key)
            raise HTTPException(status_code=502, detail="dispatch failed") from None

        return {"status": "dispatched", "issue": issue.key, "session_id": session_id}

    return router
