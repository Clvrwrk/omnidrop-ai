"""
OmniDrop AI — Structured JSON Logging
"""

import logging
import sys


def configure_logging() -> None:
    """Configure structured JSON logging for all environments."""
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
