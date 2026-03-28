"""
OmniDrop AI — Analytics Endpoints
GET /api/v1/analytics/kpis
GET /api/v1/analytics/vendor-spend
"""

from fastapi import APIRouter, Query

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
