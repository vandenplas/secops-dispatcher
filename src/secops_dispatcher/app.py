import logging

from fastapi import FastAPI

from .config import Settings, get_settings
from .dispatch import Dispatcher, DispatchLedger, LoggingDispatcher
from .logging_config import configure_logging
from .webhook import build_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, dispatcher: Dispatcher | None = None) -> FastAPI:
    settings = settings or get_settings()
    dispatcher = dispatcher or LoggingDispatcher()
    configure_logging(settings.log_level)

    app = FastAPI(title="secops-dispatcher", version="0.1.0")
    app.state.settings = settings
    app.state.dispatcher = dispatcher
    app.state.ledger = DispatchLedger()
    logger.info("starting secops-dispatcher with config: %s", settings.redacted())

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/config")
    def config() -> dict[str, object]:
        """Non-secret view of the effective configuration, for local troubleshooting."""
        return settings.redacted()

    app.include_router(build_router(settings, dispatcher, app.state.ledger))
    return app


app = create_app()
