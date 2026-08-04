import re
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# https://github.com/users/<login>/projects/<n> or https://github.com/orgs/<login>/projects/<n>
PROJECT_URL = re.compile(
    r"github\.com/(?P<kind>users|orgs)/(?P<login>[^/]+)/projects/(?P<number>\d+)"
)


def _empty_to_none(value: object) -> object:
    """Treat `KEY=` in a .env file as unset rather than as an invalid value."""
    return None if value == "" else value


OptionalInt = Annotated[int | None, BeforeValidator(_empty_to_none)]


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    # Repository whose vulnerability issues are dispatched, as "owner/name".
    target_repo: str = "vandenplas/superset"

    # Only issues carrying this label are dispatched.
    vulnerability_label: str = "vulnerability"

    # Branch the remediation work is based on: the target repo's default branch.
    target_base_branch: str = "master"

    # GitHub project used for issue tracking visibility.
    github_project_url: str = "https://github.com/users/vandenplas/projects/2"
    github_project_name: str = "Superset SVM"

    github_webhook_secret: str = Field(default="", repr=False)
    devin_api_key: str = Field(default="", repr=False)

    # GitHub PAT with the "project" scope, handed to the session so the agent can move the issue on
    # the board. The agent's own GitHub app credentials cannot write to Projects.
    github_project_token: str = Field(default="", repr=False)

    # Sessions are created through the v3 API, which is scoped to an organization.
    devin_api_base_url: str = "https://api.devin.ai"
    devin_org_id: str = ""
    devin_request_timeout_seconds: float = 30.0

    # Optional Devin session tuning.
    devin_playbook_id: str = ""
    devin_max_acu_limit: OptionalInt = None
    devin_create_as_user_id: str = ""

    # Log the rendered prompt instead of calling the Devin API. Useful for reviewing the
    # remediation instructions, or running the webhook plumbing without spending ACUs.
    dry_run: bool = False

    @property
    def project_ref(self) -> tuple[str, str, int] | None:
        """GraphQL coordinates of the tracking project: (owner kind, login, number).

        The owner kind is the GraphQL root field, so a user project is `user(login: ...)` while an
        organization project is `organization(login: ...)`.
        """
        match = PROJECT_URL.search(self.github_project_url)
        if not match:
            return None
        kind = "user" if match["kind"] == "users" else "organization"
        return kind, match["login"], int(match["number"])

    def redacted(self) -> dict[str, object]:
        """Config snapshot safe for logging: secrets are reported as set/unset only."""
        secrets = {"github_webhook_secret", "devin_api_key", "github_project_token"}
        data = self.model_dump(exclude=secrets)
        for name in secrets:
            data[f"{name}_set"] = bool(getattr(self, name))
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()
