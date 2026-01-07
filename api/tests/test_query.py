"""Tests for the /query endpoint."""

import pytest
from fastapi.testclient import TestClient

from api.src.app import app


@pytest.fixture
def client():
    """Create test client."""
    with TestClient(app) as c:
        yield c


def test_health_check(client):
    """Test health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_query_returns_citations_and_reasoning(client):
    """Test that /query returns both linear and non-linear results."""
    response = client.post(
        "/query",
        json={"query": "How does backpropagation work?", "top_k": 3},
    )

    assert response.status_code == 200
    data = response.json()

    # Check structure matches QueryResponse model
    assert "citations" in data
    assert "reasoning" in data
    assert "query" in data

    # Check citations structure
    assert len(data["citations"]) == 3
    for citation in data["citations"]:
        assert "source" in citation
        assert "page" in citation
        assert "text" in citation
        assert "score" in citation

    # Check reasoning is non-empty
    assert len(data["reasoning"]) > 0

    # Check query is echoed back
    assert data["query"] == "How does backpropagation work?"


def test_query_respects_top_k(client):
    """Test that top_k parameter limits citations."""
    response = client.post(
        "/query",
        json={"query": "test query", "top_k": 2},
    )

    assert response.status_code == 200
    assert len(response.json()["citations"]) == 2


def test_query_validates_empty_query(client):
    """Test that empty query is rejected."""
    response = client.post(
        "/query",
        json={"query": "", "top_k": 5},
    )

    assert response.status_code == 422  # Validation error


def test_query_validates_top_k_bounds(client):
    """Test that top_k must be between 1 and 20."""
    # Too low
    response = client.post(
        "/query",
        json={"query": "test", "top_k": 0},
    )
    assert response.status_code == 422

    # Too high
    response = client.post(
        "/query",
        json={"query": "test", "top_k": 25},
    )
    assert response.status_code == 422
