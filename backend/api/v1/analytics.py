"""
OmniDrop AI — Analytics Endpoints
GET  /api/v1/analytics/kpis
GET  /api/v1/analytics/vendor-spend
GET  /api/v1/analytics/leakage
POST /api/v1/analytics/query  — Text-to-SQL agent
"""

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request
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


# ── Revenue Leakage Summary ──────────────────────────────────────────────────


def _period_cutoff(period: str) -> str:
    """Return an ISO 8601 UTC timestamp for the start of the requested period."""
    now = datetime.now(timezone.utc)
    if period == "7d":
        cutoff = now - timedelta(days=7)
    elif period == "30d":
        cutoff = now - timedelta(days=30)
    elif period == "90d":
        cutoff = now - timedelta(days=90)
    elif period == "ytd":
        cutoff = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    else:
        cutoff = now - timedelta(days=30)
    return cutoff.isoformat()


@router.get("/analytics/leakage", summary="Revenue leakage summary for C-Suite dashboard")
async def get_leakage_summary(
    request: Request,
    period: str = Query(default="30d", pattern="^(7d|30d|90d|ytd)$"),
) -> dict:
    """
    Returns revenue leakage summary for the authenticated org.
    Used by /dashboard/c-suite Revenue Recovery Dashboard.

    Scoped to organization via x-workos-org-id header → organization_id lookup.
    """
    from backend.services.supabase_client import get_or_create_organization, get_supabase_client

    workos_org_id = request.headers.get("x-workos-org-id")
    if not workos_org_id:
        raise HTTPException(status_code=401, detail="Missing x-workos-org-id header.")

    workos_org_name = request.headers.get("x-workos-org-name", "")
    org = await get_or_create_organization(workos_org_id, workos_org_name)
    organization_id = org.get("organization_id")
    if not organization_id:
        raise HTTPException(status_code=404, detail="Organization not found.")

    cutoff = _period_cutoff(period)

    try:
        client = await get_supabase_client()

        # Query revenue_findings joined with locations for location_name
        findings_resp = await (
            client.table("revenue_findings")
            .select(
                "leakage_amount, vendor_name, location_id, "
                "locations(location_name)"
            )
            .eq("organization_id", organization_id)
            .gte("created_at", cutoff)
            .execute()
        )

        rows = findings_resp.data or []

        total_leakage = sum(r.get("leakage_amount", 0.0) or 0.0 for r in rows)
        finding_count = len(rows)

        # Aggregate by location
        location_agg: dict[str, dict] = {}
        for r in rows:
            loc = r.get("locations") or {}
            loc_name = loc.get("location_name") or r.get("location_id") or "Unknown"
            if loc_name not in location_agg:
                location_agg[loc_name] = {"location_name": loc_name, "total_leakage": 0.0, "finding_count": 0}
            location_agg[loc_name]["total_leakage"] += r.get("leakage_amount", 0.0) or 0.0
            location_agg[loc_name]["finding_count"] += 1

        # Aggregate by vendor
        vendor_agg: dict[str, dict] = {}
        for r in rows:
            vendor = r.get("vendor_name") or "Unknown"
            if vendor not in vendor_agg:
                vendor_agg[vendor] = {"vendor_name": vendor, "total_leakage": 0.0, "finding_count": 0}
            vendor_agg[vendor]["total_leakage"] += r.get("leakage_amount", 0.0) or 0.0
            vendor_agg[vendor]["finding_count"] += 1

        by_location = sorted(location_agg.values(), key=lambda x: x["total_leakage"], reverse=True)[:10]
        by_vendor = sorted(vendor_agg.values(), key=lambda x: x["total_leakage"], reverse=True)[:10]

    except Exception:
        logger.exception("get_leakage_summary failed for org %s", organization_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve leakage summary.")

    return {
        "total_leakage": total_leakage,
        "finding_count": finding_count,
        "by_location": by_location,
        "by_vendor": by_vendor,
        "period": period,
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
