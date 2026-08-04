import pytest

from secops_dispatcher.config import Settings
from secops_dispatcher.devin_client import DevinDispatcher
from secops_dispatcher.dispatch import DryRunDispatcher, select_dispatcher
from secops_dispatcher.models import VulnerabilityIssue
from secops_dispatcher.playbook import render_prompt

ISSUE = VulnerabilityIssue(
    repo="vandenplas/superset",
    number=12,
    title="CVE-2025-9999 in requests",
    url="https://github.com/vandenplas/superset/issues/12",
    body="  requests 2.31.0 is affected  ",
)


def test_prompt_covers_every_required_step() -> None:
    prompt = render_prompt(ISSUE, Settings())

    # The six steps the dispatcher must instruct the agent to perform, in order.
    markers = [
        "Starting remediation",
        "In Progress",
        f"branch from `{Settings().target_base_branch}`",
        "Upgrade the vulnerable package",
        "AGENTS.md",
        "In Review",
        "link the issue to the pull request",
    ]
    positions = [prompt.index(marker) for marker in markers]
    assert positions == sorted(positions), "playbook steps are out of order"


def test_prompt_substitutes_issue_and_project_details() -> None:
    prompt = render_prompt(ISSUE, Settings())
    assert "issue #12" in prompt
    assert ISSUE.url in prompt
    assert "requests 2.31.0 is affected" in prompt
    assert "Superset SVM" in prompt
    assert "https://github.com/users/vandenplas/projects/2" in prompt
    assert "{{" not in prompt


def test_prompt_handles_empty_issue_body() -> None:
    issue = ISSUE.model_copy(update={"body": ""})
    assert "(the issue has no description)" in render_prompt(issue, Settings())


def test_prompt_uses_the_configured_base_branch() -> None:
    prompt = render_prompt(ISSUE, Settings(target_base_branch="trunk"))
    assert "branch from `trunk`" in prompt
    assert "`main`" not in prompt


def test_prompt_keeps_the_verification_step_without_the_demo_label() -> None:
    prompt = render_prompt(ISSUE, Settings())
    assert "Read `AGENTS.md`" in prompt
    assert "Skip verification" not in prompt


def test_demo_label_replaces_verification_with_a_fast_path() -> None:
    issue = ISSUE.model_copy(update={"labels": ["vulnerability", "demo"]})
    prompt = render_prompt(issue, Settings())
    assert "Skip verification" in prompt
    assert "do not merge" in prompt
    # The whole point of the fast path: no test suite and no lockfile regeneration.
    assert "do **not** run the test suite" in prompt
    assert "Read `AGENTS.md`" not in prompt
    assert "{{" not in prompt


def test_demo_label_is_configurable_and_matched_exactly() -> None:
    issue = ISSUE.model_copy(update={"labels": ["vulnerability", "demo"]})
    settings = Settings(demo_label="fast-path")
    assert "Read `AGENTS.md`" in render_prompt(issue, settings)

    labelled = ISSUE.model_copy(update={"labels": ["vulnerability", "fast-path"]})
    assert "`fast-path` label" in render_prompt(labelled, settings)


def test_empty_demo_label_disables_the_fast_path() -> None:
    issue = ISSUE.model_copy(update={"labels": ["vulnerability", ""]})
    assert "Read `AGENTS.md`" in render_prompt(issue, Settings(demo_label=""))


def test_prompt_explains_how_to_move_the_board_when_a_token_is_configured() -> None:
    prompt = render_prompt(ISSUE, Settings(github_project_token="ghp_board"))
    assert "GITHUB_PROJECT_TOKEN" in prompt
    assert "updateProjectV2ItemFieldValue" in prompt
    # GraphQL coordinates come from the project URL, not from separate settings.
    assert 'user(login: "vandenplas")' in prompt
    assert "projectV2(number: 2)" in prompt
    assert "{{" not in prompt


def test_prompt_warns_about_board_access_without_a_token() -> None:
    prompt = render_prompt(ISSUE, Settings(github_project_token=""))
    assert "GITHUB_PROJECT_TOKEN" not in prompt
    assert "FORBIDDEN" in prompt
    assert "{{" not in prompt


def test_prompt_uses_organization_projects_when_the_url_says_so() -> None:
    settings = Settings(
        github_project_url="https://github.com/orgs/acme/projects/7",
        github_project_token="ghp_board",
    )
    assert 'organization(login: "acme")' in render_prompt(ISSUE, settings)
    assert "projectV2(number: 7)" in render_prompt(ISSUE, settings)


def test_prompt_follows_configured_project() -> None:
    settings = Settings(github_project_name="Other Board", github_project_url="https://x/y")
    # An unparseable project URL must still render, just without GraphQL coordinates.
    prompt = render_prompt(ISSUE, settings)
    assert "Other Board" in prompt
    assert "https://x/y" in prompt
    assert "Superset SVM" not in prompt


def test_dry_run_dispatcher_logs_prompt_and_returns_no_session(caplog) -> None:
    dispatcher = DryRunDispatcher(Settings())
    with caplog.at_level("INFO"):
        assert dispatcher.dispatch(ISSUE) is None
    assert "dry run" in caplog.text
    assert "Starting remediation" in caplog.text
    assert dispatcher.dispatched == [ISSUE]


@pytest.mark.parametrize(
    ("settings", "expected_type", "expected_mode"),
    [
        (Settings(devin_api_key="cog_k", devin_org_id="org-1"), DevinDispatcher, "devin-api"),
        (
            Settings(devin_api_key="cog_k", devin_org_id="org-1", dry_run=True),
            DryRunDispatcher,
            "dry-run",
        ),
        (
            Settings(devin_api_key="", devin_org_id="org-1"),
            DryRunDispatcher,
            "dry-run (DEVIN_API_KEY not set)",
        ),
        (
            Settings(devin_api_key="cog_k", devin_org_id=""),
            DryRunDispatcher,
            "dry-run (DEVIN_ORG_ID not set)",
        ),
        (
            Settings(devin_api_key="", devin_org_id=""),
            DryRunDispatcher,
            "dry-run (DEVIN_API_KEY and DEVIN_ORG_ID not set)",
        ),
    ],
)
def test_select_dispatcher(settings, expected_type, expected_mode) -> None:
    dispatcher, mode = select_dispatcher(settings)
    assert isinstance(dispatcher, expected_type)
    assert mode == expected_mode
