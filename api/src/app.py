"""
Brain-OS API Service.

Provides the /query endpoint that returns:
- Linear (Sparse): Specific document citations
- Non-Linear (Dense): LLM-synthesized reasoning
"""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

from .clients import (
    VectorDBClient,
    LLMClient,
    create_vector_client,
    create_llm_client,
)
from .config import settings
from .models import QueryRequest, QueryResponse, Citation

logger = structlog.get_logger()

# Global client instances (initialized on startup)
vector_client: VectorDBClient | None = None
llm_client: LLMClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize clients on startup, cleanup on shutdown."""
    global vector_client, llm_client

    logger.info(
        "starting_api",
        mock_mode=settings.use_mock_clients,
        qdrant_host=settings.qdrant_host,
        ollama_model=settings.ollama_model,
    )

    vector_client = create_vector_client(mock=settings.use_mock_clients)
    llm_client = create_llm_client(mock=settings.use_mock_clients)

    yield

    logger.info("shutting_down_api")


app = FastAPI(
    title="Brain-OS API",
    description="Deep Document Understanding RAG System",
    version="3.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    """
    Query the document corpus.

    Returns both Linear (citations) and Non-Linear (reasoning) results:
    - Citations: Direct excerpts from source documents with page numbers
    - Reasoning: LLM-synthesized answer based on retrieved context
    """
    if vector_client is None or llm_client is None:
        raise HTTPException(status_code=503, detail="Clients not initialized")

    logger.info(
        "processing_query",
        query=request.query,
        top_k=request.top_k,
        collection=request.collection,
    )

    # Step 1: Linear Search - Retrieve relevant document chunks
    search_results = vector_client.search(
        query=request.query,
        collection=request.collection,
        top_k=request.top_k,
    )

    # Convert to Citation models
    citations = [
        Citation(
            source=result.metadata.get("source", "unknown"),
            page=result.metadata.get("page", 1),
            text=result.text,
            score=result.metadata.get("score", 0.0),
        )
        for result in search_results
    ]

    # --- START OF MANUAL EDIT ---
    # Step 2: Non-Linear Synthesis - Deep Research Prompting
    # We format the context to include Source/Page info so the LLM can cite correctly.
    formatted_context = [
        f"SOURCE: {c.source} | PAGE: {c.page}\nCONTENT: {c.text}" 
        for c in citations
    ]
    
    # We define a specialized system prompt for "Deep Research"
    system_instruction = (
        "You are a Deep Research Assistant. Answer using ONLY the provided context.\n"
        "1. Synthesize a non-linear answer based on retrieved evidence.\n"
        "2. Cite every claim as [Source_Name, Page_X].\n"
        "3. If context includes flattened tables, extract specific numerical data points."
    )

    # Note: We combine instructions with context for the LLM call
    reasoning = llm_client.synthesize(
        query=f"{system_instruction}\n\nUSER QUESTION: {request.query}", 
        context=formatted_context
    )
    # --- END OF MANUAL EDIT ---

    logger.info(
        "query_complete",
        query=request.query,
        num_citations=len(citations),
    )

    return QueryResponse(
        citations=citations,
        reasoning=reasoning,
        query=request.query,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.src.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
