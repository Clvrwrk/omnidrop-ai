"""
OmniDrop AI — Analytics Endpoints
GET  /api/v1/analytics/kpis
GET  /api/v1/analytics/vendor-spend
GET  /api/v1/analytics/leakage
POST /api/v1/analytics/query  — Text-to-SQL agent

T2-10: get_kpis
  Five KPIs, all org-scoped (organization_id from WorkOS session header):
    volume_processed        — jobs completed in period vs prior period
    accuracy_rate           — confirmed / (confirmed + rejected) documents
    avg_processing_time_sec — AVG(completed_at - created_at) for complete jobs
    total_invoice_value     — SUM(invoices.total) for org in period
    pending_triage_count    — documents with triage_status='needs_clarity' (no period)

  Delta computation: (current - prior) / prior * 100.0, clamped to 0.0 when prior=0.

  Optional location_id filter narrows all metrics to a single branch.
  When location_id is supplied, jobs/documents are filtered directly;
  invoices are filtered via their location_id column.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.services.claude_service import ClaudeService
from backend.services.supabase_client import (
    get_or_create_organization,
    get_supabase_client,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Period helpers ────────────────────────────────────────────────────────────

def _period_bounds(period: str) -> tuple[str, str, str, str]:
    """
    Return (current_start, current_end, prior_start, prior_end) as UTC ISO strings.

    The prior period is the window immediately before the current period of equal
    length, so delta_pct is always an apples-to-apples comparison.

    ytd: current  = Jan 1 of this year → now
         prior    = Jan 1 of last year → Jan 1 of this year (same span length)
    """
    now = datetime.now(timezone.utc)

    if period == "7d":
        span = timedelta(days=7)
    elif period == "30d":
        span = timedelta(days=30)
    elif period == "90d":
        span = timedelta(days=90)
    elif period == "ytd":
        current_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
        span = now - current_start
        prior_start = current_start - span
        return (
            current_start.isoformat(),
            now.isoformat(),
            prior_start.isoformat(),
            current_start.isoformat(),
        )
    else:
        span = timedelta(days=30)

    current_start = now - span
    prior_start = current_start - span
    return (
        current_start.isoformat(),
        now.isoformat(),
        prior_start.isoformat(),
        current_start.isoformat(),
    )


def _delta_pct(current: float, prior: float) -> float:
    """Percentage change from prior to current. Returns 0.0 when prior is zero."""
    if not prior:
        return 0.0
    return round((current - prior) / prior * 100.0, 2)


# ── KPI queries ───────────────────────────────────────────────────────────────

async def _count_completed_jobs(
    client,
    organization_id: str,
    start: str,
    end: str,
    location_id: str | None,
) -> int:
    """COUNT jobs WHERE status='complete' in [start, end)."""
    q = (
        client.table("jobs")
        .select("job_id", count="exact")
        .eq("organization_id", organization_id)
        .eq("status", "complete")
        .gte("completed_at", start)
        .lt("completed_at", end)
    )
    if location_id:
        q = q.eq("location_id", location_id)
    r = await q.execute()
    return r.count or 0


async def _accuracy_rate(
    client,
    organization_id: str,
    start: str,
    end: str,
    location_id: str | None,
) -> float:
    """
    confirmed / (confirmed + rejected) for documents created in [start, end).
    Returns 0.0 if no decided documents exist in the window.
    """
    q = (
        client.table("documents")
        .select("triage_status")
        .eq("organization_id", organization_id)
        .in_("triage_status", ["confirmed", "rejected"])
        .gte("created_at", start)
        .lt("created_at", end)
    )
    if location_id:
        q = q.eq("location_id", location_id)
    r = await q.execute()
    rows = r.data or []
    if not rows:
        return 0.0
    confirmed = sum(1 for row in rows if row.get("triage_status") == "confirmed")
    return round(confirmed / len(rows), 4)


async def _avg_processing_seconds(
    client,
    organization_id: str,
    start: str,
    end: str,
    location_id: str | None,
) -> float:
    """
    Average (completed_at - created_at) in seconds for complete jobs in [start, end).
    Returns 0.0 if no complete jobs in window.

    Supabase PostgREST doesn't support AVG() directly, so we fetch the timestamps
    and compute in Python. Volume here is bounded by the period window, so this
    is safe for typical production loads (thousands, not millions of rows).
    """
    q = (
        client.table("jobs")
        .select("created_at, completed_at")
        .eq("organization_id", organization_id)
        .eq("status", "complete")
        .gte("completed_at", start)
        .lt("completed_at", end)
        .not_.is_("completed_at", "null")
    )
    if location_id:
        q = q.eq("location_id", location_id)
    r = await q.execute()
    rows = r.data or []
    if not rows:
        return 0.0

    deltas: list[float] = []
    for row in rows:
        try:
            created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            completed = datetime.fromisoformat(row["completed_at"].replace("Z", "+00:00"))
            deltas.append((completed - created).total_seconds())
        except (KeyError, ValueError):
            continue

    return round(sum(deltas) / len(deltas), 2) if deltas else 0.0


async def _total_invoice_value(
    client,
    organization_id: str,
    start: str,
    end: str,
    location_id: str | None,
) -> float:
    """
    SUM(invoices.total) for org in [start, end).
    Invoices are scoped by organization_id and created_at.
    """
    q = (
        client.table("invoices")
        .select("total")
        .eq("organization_id", organization_id)
        .gte("created_at", start)
        .lt("created_at", end)
        .not_.is_("total", "null")
    )
    if location_id:
        q = q.eq("location_id", location_id)
    r = await q.execute()
    rows = r.data or []
    return round(sum(float(row.get("total") or 0.0) for row in rows), 2)


async def _pending_triage_count(
    client,
    organization_id: str,
    location_id: str | None,
) -> int:
    """
    COUNT documents WHERE triage_status='needs_clarity'.
    No period filter — this is always the live queue depth.
    """
    q = (
        client.table("documents")
        .select("document_id", count="exact")
        .eq("organization_id", organization_id)
        .eq("triage_status", "needs_clarity")
    )
    if location_id:
        q = q.eq("location_id", location_id)
    r = await q.execute()
    return r.count or 0


# ── KPI endpoint ──────────────────────────────────────────────────────────────

@router.get("/analytics/kpis", summary="C-Suite KPI metrics")
async def get_kpis(
    request: Request,
    period: str = Query(default="30d", pattern="^(7d|30d|90d|ytd)$"),
    location_id: str | None = Query(default=None),
) -> dict:
    """
    C-Suite KPI dashboard metrics for the requested period.

    All metrics are scoped to the authenticated organization via the
    x-workos-org-id session header. Optional location_id narrows to a
    single branch.

    Each time-series KPI returns:
      value     — current period value
      delta_pct — percentage change vs the equally-sized prior period
                  (positive = improvement, negative = decline)

    pending_triage_count has no period — it is always the live queue depth.
    """
    workos_org_id = request.headers.get("x-workos-org-id")
    if not workos_org_id:
        raise HTTPException(status_code=401, detail="Missing x-workos-org-id header.")

    workos_org_name = request.headers.get("x-workos-org-name", "")
    org = await get_or_create_organization(workos_org_id, workos_org_name)
    organization_id = org.get("organization_id")
    if not organization_id:
        raise HTTPException(status_code=404, detail="Organization not found.")

    curr_start, curr_end, prior_start, prior_end = _period_bounds(period)

    try:
        client = await get_supabase_client()

        # Fire all 9 queries concurrently: 4 metrics × 2 periods + 1 triage count
        (
            vol_curr,
            vol_prior,
            acc_curr,
            acc_prior,
            proc_curr,
            proc_prior,
            inv_curr,
            inv_prior,
            triage_count,
        ) = await asyncio.gather(
            _count_completed_jobs(client, organization_id, curr_start, curr_end, location_id),
            _count_completed_jobs(client, organization_id, prior_start, prior_end, location_id),
            _accuracy_rate(client, organization_id, curr_start, curr_end, location_id),
            _accuracy_rate(client, organization_id, prior_start, prior_end, location_id),
            _avg_processing_seconds(client, organization_id, curr_start, curr_end, location_id),
            _avg_processing_seconds(client, organization_id, prior_start, prior_end, location_id),
            _total_invoice_value(client, organization_id, curr_start, curr_end, location_id),
            _total_invoice_value(client, organization_id, prior_start, prior_end, location_id),
            _pending_triage_count(client, organization_id, location_id),
        )

    except Exception:
        logger.exception("get_kpis failed for org %s", organization_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve KPI metrics.")

    logger.info(
        "get_kpis",
        extra={
            "organization_id": organization_id,
            "period": period,
            "location_id": location_id,
        },
    )

    return {
        "period": period,
        "volume_processed": {
            "value": vol_curr,
            "delta_pct": _delta_pct(vol_curr, vol_prior),
        },
        "accuracy_rate": {
            "value": acc_curr,
            "delta_pct": _delta_pct(acc_curr, acc_prior),
        },
        "avg_processing_time_seconds": {
            "value": proc_curr,
            "delta_pct": _delta_pct(proc_curr, proc_prior),
        },
        "total_invoice_value": {
            "value": inv_curr,
            "delta_pct": _delta_pct(inv_curr, inv_prior),
        },
        "pending_triage_count": triage_count,
    }


@router.get("/analytics/vendor-spend", summary="Vendor spend breakdown")
async def get_vendor_spend(
    request: Request,
    period: str = Query(default="30d", pattern="^(7d|30d|90d|ytd)$"),
    location_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> dict:
    """
    Vendor spend breakdown for the authenticated org.

    Aggregates invoices by vendor_name, returning total_spend, invoice_count,
    and avg_invoice_amount. All amounts are summed from invoices.total.

    Scoped to organization via x-workos-org-id header. Optional location_id
    narrows to a single branch. date_from / date_to override the period window
    when both are supplied (ISO 8601).
    """
    workos_org_id = request.headers.get("x-workos-org-id")
    if not workos_org_id:
        raise HTTPException(status_code=401, detail="Missing x-workos-org-id header.")

    workos_org_name = request.headers.get("x-workos-org-name", "")
    org = await get_or_create_organization(workos_org_id, workos_org_name)
    organization_id = org.get("organization_id")
    if not organization_id:
        raise HTTPException(status_code=404, detail="Organization not found.")

    # Resolve date window
    if date_from and date_to:
        start, end = date_from, date_to
    else:
        start, end, _, _ = _period_bounds(period)

    try:
        client = await get_supabase_client()
        q = (
            client.table("invoices")
            .select("vendor_name, total")
            .eq("organization_id", organization_id)
            .gte("created_at", start)
            .lt("created_at", end)
            .not_.is_("vendor_name", "null")
            .not_.is_("total", "null")
        )
        if location_id:
            q = q.eq("location_id", location_id)
        r = await q.execute()
        rows = r.data or []
    except Exception:
        logger.exception("get_vendor_spend failed for org %s", organization_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve vendor spend.")

    # Aggregate per vendor in Python (PostgREST lacks GROUP BY)
    agg: dict[str, dict] = {}
    for row in rows:
        vendor = row.get("vendor_name") or "Unknown"
        amount = float(row.get("total") or 0.0)
        if vendor not in agg:
            agg[vendor] = {"vendor_name": vendor, "total_spend": 0.0, "invoice_count": 0}
        agg[vendor]["total_spend"] += amount
        agg[vendor]["invoice_count"] += 1

    items = []
    for v in sorted(agg.values(), key=lambda x: x["total_spend"], reverse=True):
        count = v["invoice_count"]
        items.append({
            "vendor_name": v["vendor_name"],
            "total_spend": round(v["total_spend"], 2),
            "invoice_count": count,
            "avg_invoice_amount": round(v["total_spend"] / count, 2) if count else 0.0,
        })

    logger.info(
        "get_vendor_spend",
        extra={"organization_id": organization_id, "period": period, "location_id": location_id},
    )

    return {"period": period, "location_id": location_id, "items": items}


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
    location_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> dict:
    """
    Returns per-vendor revenue leakage summary for the authenticated org.
    Used by /dashboard/c-suite Revenue Recovery Dashboard.

    Each item in `items` contains:
      vendor_name, total_leakage_amount, finding_count,
      avg_leakage_per_invoice, location_id (null when org-scoped)

    Scoped to organization via x-workos-org-id header. Optional location_id
    narrows to a single branch. date_from / date_to override the period window.
    """
    workos_org_id = request.headers.get("x-workos-org-id")
    if not workos_org_id:
        raise HTTPException(status_code=401, detail="Missing x-workos-org-id header.")

    workos_org_name = request.headers.get("x-workos-org-name", "")
    org = await get_or_create_organization(workos_org_id, workos_org_name)
    organization_id = org.get("organization_id")
    if not organization_id:
        raise HTTPException(status_code=404, detail="Organization not found.")

    # Resolve date window
    if date_from and date_to:
        start, end = date_from, date_to
    else:
        start, end, _, _ = _period_bounds(period)

    try:
        client = await get_supabase_client()
        q = (
            client.table("revenue_findings")
            .select("leakage_amount, vendor_name, location_id")
            .eq("organization_id", organization_id)
            .gte("created_at", start)
            .lt("created_at", end)
        )
        if location_id:
            q = q.eq("location_id", location_id)
        findings_resp = await q.execute()
        rows = findings_resp.data or []
    except Exception:
        logger.exception("get_leakage_summary failed for org %s", organization_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve leakage summary.")

    # Aggregate per (vendor_name, location_id)
    Key = tuple[str, str | None]
    agg: dict[Key, dict] = {}
    for r in rows:
        vendor = r.get("vendor_name") or "Unknown"
        loc = r.get("location_id")  # None when no location filter
        key: Key = (vendor, loc)
        amount = float(r.get("leakage_amount") or 0.0)
        if key not in agg:
            agg[key] = {
                "vendor_name": vendor,
                "location_id": loc,
                "total_leakage_amount": 0.0,
                "finding_count": 0,
            }
        agg[key]["total_leakage_amount"] += amount
        agg[key]["finding_count"] += 1

    items = []
    for entry in sorted(agg.values(), key=lambda x: x["total_leakage_amount"], reverse=True):
        count = entry["finding_count"]
        items.append({
            "vendor_name": entry["vendor_name"],
            "location_id": entry["location_id"],
            "total_leakage_amount": round(entry["total_leakage_amount"], 2),
            "finding_count": count,
            "avg_leakage_per_invoice": round(entry["total_leakage_amount"] / count, 2) if count else 0.0,
        })

    logger.info(
        "get_leakage_summary",
        extra={"organization_id": organization_id, "period": period, "location_id": location_id},
    )

    return {
        "period": period,
        "location_id": location_id,
        "total_leakage_amount": round(sum(i["total_leakage_amount"] for i in items), 2),
        "finding_count": sum(i["finding_count"] for i in items),
        "items": items,
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
