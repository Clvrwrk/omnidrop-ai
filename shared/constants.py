"""
OmniDrop AI — Shared Constants
Used by both the FastAPI backend and Temporal workers.
"""

# =============================================================================
# AccuLynx API Rate Limits
# Source: AccuLynx API documentation
# =============================================================================
ACCULYNX_RATE_LIMIT_PER_IP: int = 30       # requests per second per IP
ACCULYNX_RATE_LIMIT_PER_KEY: int = 10      # requests per second per API key
ACCULYNX_WEBHOOK_TIMEOUT_SECONDS: int = 10  # AccuLynx retries if no response in 10s
ACCULYNX_API_BASE_URL: str = "https://api.acculynx.com/api/v2"

# =============================================================================
# Temporal Task Queues
# Keep queue names in sync with TEMPORAL_TASK_QUEUE env var
# =============================================================================
TEMPORAL_TASK_QUEUE: str = "omni-intake-queue"

# =============================================================================
# Webhook Headers
# =============================================================================
ACCULYNX_SIGNATURE_HEADER: str = "X-AccuLynx-Signature"
