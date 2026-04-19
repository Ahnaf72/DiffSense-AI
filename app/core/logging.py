import logging
import sys
import uuid

from app.core.config import settings


def setup_logging() -> None:
    """Configure root logger for the application."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# ── Request ID context ──────────────────────────────────────────────

_request_id_var: str = ""


def get_request_id() -> str:
    return _request_id_var


def set_request_id(rid: str) -> None:
    global _request_id_var
    _request_id_var = rid


class RequestIdFilter(logging.Filter):
    """Inject the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


# Register the filter on the root logger so all child loggers inherit it
logging.getLogger().addFilter(RequestIdFilter())
