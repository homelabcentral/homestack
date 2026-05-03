"""Centralized logging setup for homestack commands."""

from __future__ import annotations

import logging
from pathlib import Path

from settings.settings import settings

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(log_file: Path | None = None) -> None:
    """Configure console and file handlers once for the process."""
    log_path = log_file or settings.log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("homestack")
    if root_logger.handlers:
        return

    level_name = (settings.log_level or "INFO").strip().upper()
    level = logging.getLevelNamesMapping().get(level_name, logging.INFO)

    root_logger.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def get_command_logger(command_name: str) -> logging.Logger:
    """Return a command-scoped logger under the homestack namespace."""
    setup_logging()
    return logging.getLogger(f"homestack.command.{command_name}")
