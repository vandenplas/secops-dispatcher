from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # GitHub project used for issue tracking visibility.
    github_project_url: str = "https://github.com/users/vandenplas/projects/2"

    # Secrets. Left empty in the skeleton; consumed by later integrations.
    github_webhook_secret: str = Field(default="", repr=False)
    devin_api_key: str = Field(default="", repr=False)

    devin_api_base_url: str = "https://api.devin.ai/v1"

    def redacted(self) -> dict[str, object]:
        """Config snapshot safe for logging: secrets are reported as set/unset only."""
        data = self.model_dump(exclude={"github_webhook_secret", "devin_api_key"})
        data["github_webhook_secret_set"] = bool(self.github_webhook_secret)
        data["devin_api_key_set"] = bool(self.devin_api_key)
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()
