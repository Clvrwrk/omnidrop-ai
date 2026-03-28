"""
OmniDrop AI — Jobs Endpoints
GET /api/v1/jobs
GET /api/v1/jobs/{job_id}
"""

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/jobs", summary="List jobs for authenticated user's locations")
async def list_jobs(
    location_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Returns paginated job list. Placeholder until Supabase queries are wired."""
    # TODO: Query Supabase jobs table filtered by user's locations
    return {
        "jobs": [],
        "total": 0,
        "offset": offset,
        "limit": limit,
    }


@router.get("/jobs/{job_id}", summary="Get single job detail")
async def get_job(job_id: str) -> dict:
    """Returns full job detail. Placeholder until Supabase queries are wired."""
    # TODO: Query Supabase jobs table by job_id, verify location access
    return {
        "job_id": job_id,
        "location_id": None,
        "location_name": None,
        "status": "queued",
        "document_type": None,
        "file_name": None,
        "raw_path": None,
        "created_at": None,
        "completed_at": None,
        "error_message": None,
        "document_id": None,
    }
