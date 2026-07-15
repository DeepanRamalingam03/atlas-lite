from __future__ import annotations

import logging
import sys


def setup_logger(
    name: str = "atlas-lite",
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Create and return one reusable console logger.

    Duplicate handlers are avoided when this function is called repeatedly.
    """

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
