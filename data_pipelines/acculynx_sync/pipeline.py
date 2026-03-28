"""
OmniDrop AI — AccuLynx Historical Data Sync Pipeline

Uses dlt's rest_api source to pull historical data from AccuLynx
and load it into Supabase (PostgreSQL).

RATE LIMIT REMINDER:
  - 30 req/sec per IP, 10 req/sec per API key
  - dlt handles pagination automatically; configure max_retries and backoff below

SECRETS:
  - API key and Bearer token are read from .dlt/secrets.toml at runtime
  - NEVER hardcode credentials in this file

Usage:
  python pipeline.py

Setup:
  pip install "dlt[rest_api]"
  cp .dlt/secrets.toml.example .dlt/secrets.toml
  # Fill in secrets.toml with real credentials
"""

import dlt
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

# TODO: Replace with actual AccuLynx API endpoints once documented
# Reference: https://api.acculynx.com/api/v2 (confirm endpoint list)
ACCULYNX_CONFIG: RESTAPIConfig = {
    "client": {
        "base_url": "https://api.acculynx.com/api/v2",
        "auth": {
            "type": "bearer",
            # Read from .dlt/secrets.toml — never hardcode here
            "token": dlt.secrets["sources.acculynx.bearer_token"],
        },
        "paginator": {
            "type": "page_number",         # TODO: confirm AccuLynx pagination type
            "page_param": "page",
            "total_path": "totalCount",
            "maximum_page": 1000,
        },
        # Respect AccuLynx rate limits: 10 req/sec per API key
        "rate_limiter": {
            "limit": 8,                     # Stay under the 10 req/sec limit
            "time_period": 1,
        },
    },
    "resources": [
        # TODO: Add AccuLynx resource endpoints once API access is confirmed
        # Example structure:
        # {
        #     "name": "jobs",
        #     "endpoint": {"path": "/jobs", "params": {"pageSize": 100}},
        # },
    ],
}


def run_acculynx_sync() -> None:
    """Run the AccuLynx historical sync pipeline."""
    pipeline = dlt.pipeline(
        pipeline_name="acculynx_sync",
        destination="postgres",             # Supabase is PostgreSQL-compatible
        dataset_name="acculynx_raw",
    )

    # TODO: Uncomment once resources are configured above
    # data = rest_api_resources(ACCULYNX_CONFIG)
    # load_info = pipeline.run(data)
    # print(load_info)

    raise NotImplementedError(
        "AccuLynx pipeline resources not yet configured. "
        "Add endpoint definitions to ACCULYNX_CONFIG above."
    )


if __name__ == "__main__":
    run_acculynx_sync()
