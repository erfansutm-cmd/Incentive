"""Centralized logging for the backend.

Provides :func:`get_logger`, which returns a namespaced logger and makes sure
the root logger is configured (stream -> stdout with a consistent format and
level from ``LOG_LEVEL``). Logging is configured lazily on first use, so any
module can log without relying on the app entry point running first.

Level is read from environment variable LOG_LEVEL directly.
"""

import logging
import os
import sys
from app.core.config import LOG_LEVEL


_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_CONFIGURED = False


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a configured logger for ``name`` (defaults to calling module)."""
    _configure_root()
    return logging.getLogger(name or __name__)


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(_resolve_level())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    # Attach before the handler uvicorn may have already added (e.g. uvicorn's
    # own configuration) so our formatter takes precedence on the root logger.
    root.addHandler(handler)

    _CONFIGURED = True


def _resolve_level() -> int:
    level_name = LOG_LEVEL.strip().upper()
    return getattr(logging, level_name, logging.INFO)