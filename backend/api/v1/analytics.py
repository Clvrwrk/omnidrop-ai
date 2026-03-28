"""
OmniDrop AI — Analytics Endpoints
GET  /api/v1/analytics/kpis
GET  /api/v1/analytics/vendor-spend
POST /api/v1/analytics/query  — Text-to-SQL agent
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.claude_service import ClaudeService
from backend.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/analytics/kpis", summary="C-Suite KPI metrics")
async def get_kpis(
    period: str = Query(default="30d", pattern="^(7d|30d|90d|ytd)$"),
    location_id: str | None = Query(default=None),
) -> dict:
    """Returns KPI metrics for the given period. Placeholder."""
    # TODO: Aggregate from Supabase jobs/invoices tables
    return {
        "period": period,
        "volume_processed": {"value": 0, "delta_pct": 0.0},
        "accuracy_rate": {"value": 0.0, "delta_pct": 0.0},
        "avg_processing_time_seconds": {"value": 0.0, "delta_pct": 0.0},
        "total_invoice_value": {"value": 0.0, "delta_pct": 0.0},
        "pending_triage_count": 0,
    }


@router.get("/analytics/vendor-spend", summary="Vendor spend breakdown")
async def get_vendor_spend(
    period: str = Query(default="30d", pattern="^(7d|30d|90d|ytd)$"),
    location_id: str | None = Query(default=None),
    group_by: str = Query(default="vendor", pattern="^(vendor|job|month)$"),
) -> dict:
    """Returns vendor spend breakdown. Placeholder."""
    # TODO: Aggregate from Supabase invoices/line_items tables
    return {
        "period": period,
        "group_by": group_by,
        "items": [],
        "trend": [],
    }


# ── Text-to-SQL Analytics Agent ──────────────────────────────────────────────


class AnalyticsQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Natural language question")
    location_id: str = Field(..., description="Location ID for data isolation")


class AnalyticsQueryResponse(BaseModel):
    query: str
    sql: str
    explanation: str
    columns: list[str]
    rows: list[dict]


@router.post("/analytics/query", summary="Text-to-SQL analytics agent")
async def analytics_query(body: AnalyticsQueryRequest) -> AnalyticsQueryResponse:
    """
    Accepts a natural language question, generates a parameterized SELECT via Claude,
    executes it against Supabase, and returns the results.
    location_id is always injected as a WHERE filter for data isolation.
    """
    try:
        result = ClaudeService.analytics_agent(body.query, body.location_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("analytics_agent failed for query: %s", body.query)
        raise HTTPException(status_code=500, detail="Failed to generate SQL query")

    # Execute the parameterized query via Supabase RPC
    try:
        client = await get_supabase_client()
        response = await client.rpc(
            "run_analytics_query",
            {"query_text": result["sql"], "query_params": result["params"]},
        ).execute()

        rows = response.data if response.data else []
        columns = list(rows[0].keys()) if rows else []
    except Exception:
        logger.exception("Analytics query execution failed: %s", result["sql"])
        raise HTTPException(status_code=500, detail="Failed to execute analytics query")

    return AnalyticsQueryResponse(
        query=body.query,
        sql=result["sql"],
        explanation=result["explanation"],
        columns=columns,
        rows=rows,
    )
