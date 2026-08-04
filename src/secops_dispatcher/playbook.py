import re
from functools import lru_cache
from importlib import resources

from .config import Settings
from .models import VulnerabilityIssue

PLACEHOLDER = re.compile(r"{{(\w+)}}")
TEMPLATE_RESOURCE = ("secops_dispatcher.prompts", "remediation.md")


@lru_cache
def load_template() -> str:
    package, name = TEMPLATE_RESOURCE
    return resources.files(package).joinpath(name).read_text(encoding="utf-8")


def render_prompt(issue: VulnerabilityIssue, settings: Settings) -> str:
    """Fill the remediation playbook template with issue and project details.

    Uses `{{name}}` placeholders rather than str.format so the markdown body can contain braces
    (code samples, JSON) without escaping.
    """
    values = {
        "repo": issue.repo,
        "issue_number": str(issue.number),
        "issue_title": issue.title,
        "issue_url": issue.url,
        "issue_body": issue.body.strip() or "(the issue has no description)",
        "project_name": settings.github_project_name,
        "project_url": settings.github_project_url,
        "base_branch": settings.target_base_branch,
    }

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"remediation template references unknown placeholder {{{{{key}}}}}")
        return values[key]

    return PLACEHOLDER.sub(substitute, load_template())
