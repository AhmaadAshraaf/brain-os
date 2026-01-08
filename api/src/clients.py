"""Real and Mock clients for external services (Qdrant & Ollama)."""

import httpx
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from typing import Protocol, List, Dict, Any
from dataclasses import dataclass

@dataclass
class SearchResult:
    text: str
    metadata: Dict[str, Any]

class VectorDBClient(Protocol):
    def search(self, query: str, collection: str, top_k: int) -> List[SearchResult]: ...

class LLMClient(Protocol):
    def synthesize(self, query: str, context: List[str]) -> str: ...

# --- REAL CLIENTS ---

class RealVectorDBClient(VectorDBClient):
    """Actual Qdrant client using Sentence Transformers for embeddings."""

    def __init__(self, host: str, port: int):
        # We initialize the Synchronous client to match your app logic
        self.client = QdrantClient(host=host, port=port)
        # Logic: Must match the model used in ingest.src.main
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    def search(self, query: str, collection: str, top_k: int) -> List[SearchResult]:
        """Perform vector search against Qdrant."""
        # 1. Encode query
        vector = self.model.encode(query).tolist()
        
        # 2. Search using the most compatible method for v1.12+
        # Logic: We use 'search' but wrap it in error handling for version mismatches
        try:
            points = self.client.search(
                collection_name=collection,
                query_vector=vector,
                limit=top_k,
                with_payload=True
            )
        except Exception as e:
            # Fallback to a lower-level API if 'search' attribute is missing
            print(f"Standard search failed, trying low-level API: {e}")
            from qdrant_client.http import models
            res = self.client.query_points(
                collection_name=collection,
                query=vector,
                limit=top_k
            )
            points = res.points
        
        # 3. Format results for the API
        return [
            SearchResult(
                text=p.payload.get("text", ""),
                metadata={
                    "source": p.payload.get("source"),
                    "page": p.payload.get("page_number"),
                    "type": p.payload.get("element_type")
                }
            ) for p in points
        ]

class RealLLMClient(LLMClient):
    """Actual Ollama client connecting to local service."""

    def __init__(self, host: str, port: int, model: str):
        self.url = f"http://{host}:{port}/api/generate"
        self.model = model

    def synthesize(self, query: str, context: List[str]) -> str:
        """Send context and query to Ollama for RAG response."""
        context_str = "\n---\n".join(context)
        prompt = (
            f"Context information is below:\n{context_str}\n\n"
            f"Using ONLY the context provided, answer this query: {query}\n"
            f"If the answer is not in the context, say you do not know."
        )

        try:
            response = httpx.post(
                self.url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=90.0
            )
            response.raise_for_status()
            return response.json().get("response", "Error: Empty response.")
        except Exception as e:
            return f"LLM synthesis failed: {str(e)}"

# --- MOCK CLIENTS ---

class MockVectorDBClient(VectorDBClient):
    def search(self, query: str, collection: str, top_k: int) -> List[SearchResult]:
        return [SearchResult(text="Mock context", metadata={"source": "mock.pdf"})]

class MockLLMClient(LLMClient):
    def synthesize(self, query: str, context: List[str]) -> str:
        return f"Mock response for query: {query}"

# --- FACTORY FUNCTIONS ---

def create_vector_client(mock: bool = False) -> VectorDBClient:
    if mock:
        return MockVectorDBClient()
    from .config import settings
    return RealVectorDBClient(host=settings.qdrant_host, port=settings.qdrant_port)

def create_llm_client(mock: bool = False) -> LLMClient:
    if mock:
        return MockLLMClient()
    from .config import settings
    return RealLLMClient(
        host=settings.ollama_host, 
        port=settings.ollama_port, 
        model=settings.ollama_model
    )
