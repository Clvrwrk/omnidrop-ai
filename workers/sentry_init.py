"""
OmniDrop AI — Sentry Initialization (Temporal Workers)

Call configure_sentry() at the top of workers/worker.py before starting the worker.
Captures activity failures, 429s from AccuLynx, and Azure DI / Merge.dev errors.
"""

import os

import sentry_sdk


def configure_sentry() -> None:
    """Initialize Sentry for Temporal workers."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return  # Disabled if DSN not set

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("APP_ENV", "local"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "1.0")),
        send_default_pii=False,
    )
