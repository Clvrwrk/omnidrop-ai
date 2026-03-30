"""
OmniDrop AI — Semantic Search Endpoint
GET /api/v1/search

T2-12: pgvector cosine similarity search over document_embeddings using Voyage AI
       voyage-3 embeddings (1024-dim). Results are ranked by cosine similarity
       and scoped to the authenticated organization.
"""

import logging

import voyageai
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from backend.services.supabase_client import (
    get_or_create_organization,
    get_supabase_client,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Voyage AI client — reads VOYAGE_API_KEY from environment
_vo = voyageai.Client()


# ── Response models ───────────────────────────────────────────────────────────


class SearchResult(BaseModel):
    document_id: str
    chunk_text: str
    similarity: float
    document_metadata: dict


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.get("/search", response_model=SearchResponse, summary="Semantic document search")
async def search_documents(
    request: Request,
    q: str = Query(..., min_length=1, max_length=500, description="Natural language search query"),
    location_id: str | None = Query(default=None, description="Narrow results to a single branch"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of results to return"),
) -> SearchResponse:
    """
    Semantic search over ingested documents using pgvector cosine similarity.

    The query string is embedded with Voyage AI voyage-3 (1024-dim) and compared
    against stored chunk embeddings in the document_embeddings table. Results are
    ranked by cosine similarity and filtered to the authenticated organization.

    Auth: x-workos-org-id header → organization_id (WorkOS session header pattern).
    Optional location_id narrows results to a single branch location.
    """
    # ── Auth: resolve organization from WorkOS session header ─────────────────
    workos_org_id = request.headers.get("x-workos-org-id")
    if not workos_org_id:
        raise HTTPException(status_code=401, detail="Missing x-workos-org-id header.")

    workos_org_name = request.headers.get("x-workos-org-name", "")
    org = await get_or_create_organization(workos_org_id, workos_org_name)
    organization_id = org.get("organization_id")
    if not organization_id:
        raise HTTPException(status_code=404, detail="Organization not found.")

    # ── Step 1: Embed the query with Voyage AI voyage-3 ──────────────────────
    try:
        voyage_result = _vo.embed([q], model="voyage-3", input_type="query")
        embedding: list[float] = voyage_result.embeddings[0]
    except Exception:
        logger.exception("Voyage AI embedding failed for query: %s", q)
        raise HTTPException(status_code=502, detail="Failed to generate query embedding.")

    # ── Step 2: Query document_embeddings via pgvector RPC ───────────────────
    try:
        client = await get_supabase_client()
        response = await client.rpc(
            "match_document_embeddings",
            {
                "query_embedding": embedding,
                "match_threshold": 0.7,
                "match_count": limit,
                "p_organization_id": organization_id,
                "p_location_id": location_id,  # null if not provided
            },
        ).execute()
        rows = response.data or []
    except Exception:
        logger.exception(
            "pgvector search RPC failed for org %s query: %s", organization_id, q
        )
        raise HTTPException(status_code=500, detail="Failed to execute semantic search.")

    # ── Step 3: Build ranked response ────────────────────────────────────────
    results = [
        SearchResult(
            document_id=row.get("document_id", ""),
            chunk_text=row.get("chunk_text", ""),
            similarity=float(row.get("similarity", 0.0)),
            document_metadata=row.get("document_metadata") or {},
        )
        for row in rows
    ]

    logger.info(
        "search_documents",
        extra={
            "organization_id": organization_id,
            "location_id": location_id,
            "limit": limit,
            "result_count": len(results),
        },
    )

    return SearchResponse(query=q, results=results)
