"""
OmniDrop AI — Semantic Search Endpoint
POST /api/v1/search
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    location_id: str | None = None
    limit: int = Field(default=10, le=50)


@router.post("/search", summary="Semantic RAG search over document embeddings")
async def search_documents(body: SearchRequest) -> dict:
    """Runs pgvector cosine similarity search. Placeholder."""
    # TODO: Generate embedding for query, search document_embeddings table
    return {
        "query": body.query,
        "results": [],
    }
