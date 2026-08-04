import logging

from fastapi import FastAPI

from .config import Settings, get_settings
from .logging_config import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="secops-dispatcher", version="0.1.0")
    app.state.settings = settings
    logger.info("starting secops-dispatcher with config: %s", settings.redacted())

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/config")
    def config() -> dict[str, object]:
        """Non-secret view of the effective configuration, for local troubleshooting."""
        return settings.redacted()

    return app


app = create_app()
