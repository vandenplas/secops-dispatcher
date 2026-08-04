import re
from functools import lru_cache
from importlib import resources

from .config import Settings
from .models import VulnerabilityIssue

PLACEHOLDER = re.compile(r"{{(\w+)}}")
PROMPT_PACKAGE = "secops_dispatcher.prompts"

# Told to the agent when no project token is configured, so it does not mistake the project's own
# automation for its own board moves.
NO_BOARD_TOKEN = (
    "No project token is configured for this session, and your GitHub credentials most likely "
    "cannot write to the project (`updateProjectV2ItemFieldValue` fails with `FORBIDDEN: Resource "
    "not accessible by integration`). Attempt each board move anyway, then read the item's "
    "`Status` back and check who set it. If you could not make the move yourself, say so "
    "explicitly in your resolution comment instead of reporting the step as done."
)


@lru_cache
def load_template(name: str) -> str:
    return resources.files(PROMPT_PACKAGE).joinpath(name).read_text(encoding="utf-8")


def _substitute(template: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"remediation template references unknown placeholder {{{{{key}}}}}")
        return values[key]

    return PLACEHOLDER.sub(replace, template)


def render_prompt(issue: VulnerabilityIssue, settings: Settings) -> str:
    """Fill the remediation playbook template with issue and project details.

    Uses `{{name}}` placeholders rather than str.format so the markdown body can contain braces
    (code samples, JSON) without escaping.
    """
    kind, owner, number = settings.project_ref or ("user", "", 0)
    values = {
        "repo": issue.repo,
        "issue_number": str(issue.number),
        "issue_title": issue.title,
        "issue_url": issue.url,
        "issue_body": issue.body.strip() or "(the issue has no description)",
        "project_name": settings.github_project_name,
        "project_url": settings.github_project_url,
        "project_owner_kind": kind,
        "project_owner": owner,
        "project_number": str(number),
        "base_branch": settings.target_base_branch,
    }
    values["board_access"] = (
        _substitute(load_template("board_access.md"), values).strip()
        if settings.github_project_token
        else NO_BOARD_TOKEN
    )
    return _substitute(load_template("remediation.md"), values)
