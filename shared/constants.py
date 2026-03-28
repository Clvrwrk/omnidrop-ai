"""
OmniDrop AI — Shared Constants
Used by both the FastAPI backend and Celery workers.
"""

# =============================================================================
# AccuLynx API Rate Limits
# =============================================================================
ACCULYNX_RATE_LIMIT_PER_IP: int = 30       # requests per second per IP
ACCULYNX_RATE_LIMIT_PER_KEY: int = 10      # requests per second per API key
ACCULYNX_RATE_LIMIT: str = "10/s"          # Celery rate_limit format for fetch tasks
ACCULYNX_WEBHOOK_TIMEOUT_SECONDS: int = 10  # AccuLynx retries if no response in 10s
ACCULYNX_API_BASE_URL: str = "https://api.acculynx.com/api/v2"

# =============================================================================
# Celery Queue Names
# =============================================================================
CELERY_TASK_QUEUE: str = "omni-intake"

# =============================================================================
# Hookdeck Webhook Headers
# =============================================================================
HOOKDECK_SIGNATURE_HEADER: str = "x-hookdeck-signature"

# =============================================================================
# Confidence Thresholds
# =============================================================================
AUTO_CONFIRM_THRESHOLD: float = 0.95  # All fields must be >= this to auto-confirm
