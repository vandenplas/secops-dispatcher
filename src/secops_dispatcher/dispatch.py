import logging
import threading
from dataclasses import dataclass
from typing import Protocol

from .config import Settings
from .models import IssueEvent, VulnerabilityIssue

logger = logging.getLogger(__name__)

# Actions that can make an open issue newly eligible for remediation.
DISPATCHABLE_ACTIONS = frozenset({"opened", "reopened", "labeled"})


@dataclass(frozen=True)
class Decision:
    """Whether an issue event should be dispatched, and the reason either way."""

    dispatch: bool
    reason: str
    issue: VulnerabilityIssue | None = None


def evaluate(event: IssueEvent, settings: Settings) -> Decision:
    """Decide whether an `issues` webhook event warrants a remediation dispatch."""
    if event.repository.full_name != settings.target_repo:
        return Decision(False, f"repository {event.repository.full_name} is not the target repo")

    if event.action not in DISPATCHABLE_ACTIONS:
        return Decision(False, f"action {event.action} is not dispatchable")

    if event.issue.state != "open":
        return Decision(False, f"issue is {event.issue.state}")

    label = settings.vulnerability_label
    if label not in event.issue.label_names:
        return Decision(False, f"issue is not labelled {label}")

    # A "labeled" event fires for every label; only the vulnerability label starts remediation,
    # otherwise adding an unrelated label to an already-labelled issue would re-dispatch it.
    if event.action == "labeled" and (event.label is None or event.label.name != label):
        added = event.label.name if event.label else "unknown"
        return Decision(False, f"added label {added} is not {label}")

    issue = VulnerabilityIssue(
        repo=event.repository.full_name,
        number=event.issue.number,
        title=event.issue.title,
        url=event.issue.html_url,
        body=event.issue.body or "",
    )
    return Decision(True, f"issue is labelled {label}", issue)


class Dispatcher(Protocol):
    """Starts remediation for an issue. Implemented against the Devin API in a later step."""

    def dispatch(self, issue: VulnerabilityIssue) -> str | None: ...


class LoggingDispatcher:
    """Placeholder dispatcher: records the issue instead of starting a Devin session."""

    def __init__(self) -> None:
        self.dispatched: list[VulnerabilityIssue] = []

    def dispatch(self, issue: VulnerabilityIssue) -> str | None:
        self.dispatched.append(issue)
        logger.info("would dispatch %s for remediation: %s", issue.key, issue.url)
        return None


class DispatchLedger:
    """Remembers dispatched issues so webhook retries and re-labelling don't duplicate work.

    In-memory only: restarting the container forgets history, which is acceptable while the
    dispatcher runs locally, but it is the natural seam for durable storage later.
    """

    def __init__(self) -> None:
        self._keys: set[str] = set()
        self._lock = threading.Lock()

    def claim(self, issue: VulnerabilityIssue) -> bool:
        """Register the issue, returning False if it was already dispatched."""
        with self._lock:
            if issue.key in self._keys:
                return False
            self._keys.add(issue.key)
            return True

    def release(self, issue: VulnerabilityIssue) -> None:
        """Undo a claim, so a failed dispatch can be retried by a later delivery."""
        with self._lock:
            self._keys.discard(issue.key)
