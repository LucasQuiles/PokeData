"""Central logging configuration for PokeData."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "pokedata.log"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the shared logger once and return it.

    The logs are written to ``logs/pokedata.log`` with basic rotation to prevent the
    file from growing without bound.
    """

    logger = logging.getLogger("pokedata")
    if logger.handlers:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_format = (
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    formatter = logging.Formatter(log_format)

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.WARNING)

    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    logging.getLogger("pdf2image").setLevel(logging.WARNING)
    logging.getLogger("pytesseract").setLevel(logging.INFO)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a child logger under the pokedata namespace."""

    parent = setup_logging()
    if name:
        return parent.getChild(name)
    return parent

