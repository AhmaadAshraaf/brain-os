"""Pydantic models for the Brain-OS API."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request model for the /query endpoint."""

    query: str = Field(..., min_length=1, description="The search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of citations to return")
    collection: str = Field(default="brain_os", description="Qdrant collection name")


class Citation(BaseModel):
    """A single citation from the document corpus."""

    source: str = Field(..., description="Document filename or path")
    page: int = Field(..., ge=1, description="Page number in the source document")
    text: str = Field(..., description="Relevant text excerpt")
    score: float = Field(..., ge=0, le=1, description="Relevance score")


class QueryResponse(BaseModel):
    """
    Response model for the /query endpoint.

    Combines Linear (citations) and Non-Linear (reasoning) results
    as per the Brain-OS architecture spec.
    """

    citations: list[Citation] = Field(
        ..., description="Linear/Sparse: Specific document citations"
    )
    reasoning: str = Field(
        ..., description="Non-Linear/Dense: LLM-synthesized answer"
    )
    query: str = Field(..., description="Original query for reference")
