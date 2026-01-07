"""
Client abstractions for Qdrant and Ollama.

Uses Protocol classes for interface definitions, allowing easy swapping
between mock and real implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .models import Citation


@dataclass
class SearchResult:
    """Raw search result from vector database."""

    source: str
    page: int
    text: str
    score: float


class VectorDBClient(ABC):
    """Abstract interface for vector database operations."""

    @abstractmethod
    def search(
        self, query: str, collection: str, top_k: int
    ) -> list[SearchResult]:
        """
        Perform hybrid search (sparse + dense) on the collection.

        Args:
            query: The search query text
            collection: Name of the collection to search
            top_k: Maximum number of results to return

        Returns:
            List of SearchResult objects sorted by relevance
        """
        pass


class LLMClient(ABC):
    """Abstract interface for LLM operations."""

    @abstractmethod
    def synthesize(self, query: str, context: list[str]) -> str:
        """
        Generate a synthesized answer from query and context.

        Args:
            query: The original user query
            context: List of relevant text excerpts from citations

        Returns:
            LLM-generated reasoning/answer
        """
        pass


class MockVectorDBClient(VectorDBClient):
    """Mock Qdrant client for testing without a running database."""

    def __init__(self) -> None:
        # Mock document corpus
        self._mock_data = [
            SearchResult(
                source="neural_networks_fundamentals.pdf",
                page=42,
                text="Backpropagation computes gradients by applying the chain rule recursively through the network layers.",
                score=0.95,
            ),
            SearchResult(
                source="deep_learning_architectures.pdf",
                page=15,
                text="Transformer models use self-attention mechanisms to capture long-range dependencies in sequences.",
                score=0.89,
            ),
            SearchResult(
                source="ml_optimization.pdf",
                page=78,
                text="Adam optimizer combines momentum and RMSprop, adapting learning rates for each parameter.",
                score=0.82,
            ),
            SearchResult(
                source="neural_networks_fundamentals.pdf",
                page=56,
                text="Dropout regularization randomly deactivates neurons during training to prevent overfitting.",
                score=0.75,
            ),
            SearchResult(
                source="practical_ml_guide.pdf",
                page=23,
                text="Cross-validation provides robust model evaluation by training on multiple data splits.",
                score=0.68,
            ),
        ]

    def search(
        self, query: str, collection: str, top_k: int
    ) -> list[SearchResult]:
        """Return mock search results."""
        # In a real implementation, this would:
        # 1. Encode query with embedding model
        # 2. Perform hybrid search (sparse BM25 + dense vector)
        # 3. Rerank results
        return self._mock_data[:top_k]


class MockLLMClient(LLMClient):
    """Mock Ollama client for testing without a running LLM."""

    def synthesize(self, query: str, context: list[str]) -> str:
        """Return a mock synthesized response."""
        # In a real implementation, this would:
        # 1. Format prompt with query and context
        # 2. Call Ollama API
        # 3. Return generated text
        context_summary = f"Based on {len(context)} sources"
        return (
            f"{context_summary}, the answer to '{query}' involves the concepts "
            f"mentioned in the retrieved documents. This is a mock response - "
            f"connect to Ollama for real LLM synthesis."
        )


def create_vector_client(mock: bool = False) -> VectorDBClient:
    """Factory function to create appropriate vector DB client."""
    if mock:
        return MockVectorDBClient()
    # TODO: Return real QdrantClient when implemented
    raise NotImplementedError("Real Qdrant client not yet implemented")


def create_llm_client(mock: bool = False) -> LLMClient:
    """Factory function to create appropriate LLM client."""
    if mock:
        return MockLLMClient()
    # TODO: Return real OllamaClient when implemented
    raise NotImplementedError("Real Ollama client not yet implemented")
