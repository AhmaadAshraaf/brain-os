# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Brain-OS v3.0 is a Deep Document Understanding RAG system with a "Write Once, Read Anywhere" architecture:
- **Online VM (Hetzner):** The "Writer" - runs heavy ingestion pipeline (OCR, Layout Parsing, Embedding)
- **Offline Laptop:** The "Reader" - does ZERO ingestion, downloads Qdrant snapshots from Wasabi S3

The offline experience must be identical to online in UI and logic, differing only in data freshness.

## Tech Stack

- **Orchestration:** Docker Compose (unified stack for Online/Offline)
- **Backend:** FastAPI (Python 3.11)
- **Database:** Qdrant (Hybrid Search: Sparse + Dense vectors)
- **Ingestion:** Unstructured / Layout-Parser (multi-modal: Text, Tables, Images)
- **LLM:** Ollama (local inference for reasoning)
- **Storage:** Wasabi S3 (snapshot bridge between environments)

## Architecture

```
/ingest     Python service (VM Only). PDFs/Docs -> Layout Analysis -> Vectorize -> Upsert to Qdrant
/api        FastAPI service. Handles /query endpoint
/infra      Docker Compose files (base + prod/local overlays)
/scripts    Snapshot management scripts (push/pull to Wasabi S3)
/data       Runtime data (documents, qdrant_snapshot) - gitignored
```

### Docker Compose Structure

Uses overlay pattern with a shared base:
- `docker-compose.base.yml` - Shared services (Qdrant, Ollama, API)
- `docker-compose.prod.yml` - VM overlay: adds Ingest service + Prometheus
- `docker-compose.local.yml` - Laptop overlay: read-only Qdrant mount, no GPU reservation

### Client Abstraction Pattern

The API uses abstract base classes for dependency injection (`api/src/clients.py`):
- `VectorDBClient` (ABC) → `MockVectorDBClient` / (future: real Qdrant)
- `LLMClient` (ABC) → `MockLLMClient` / (future: real Ollama)

Factory functions `create_vector_client(mock=True)` and `create_llm_client(mock=True)` switch implementations. The `use_mock_clients` setting in config controls this globally.

### API Response Structure

The `/query` endpoint returns Linear (Sparse) + Non-Linear (Dense) results:
```json
{
  "citations": [...],   // Specific document citations (Linear/Sparse)
  "reasoning": "..."    // LLM-synthesized answer (Non-Linear/Dense)
}
```

### Ingest Pipeline Architecture (VM Only)

The ingest service (`ingest/src/main.py`) processes documents through:
1. **PDF Parsing** - Uses `unstructured.partition.pdf` with `strategy="hi_res"` and `infer_table_structure=True`
2. **Table Flattening** - Tables are converted to searchable text: `"Table data: {content}"`
3. **Metadata Enrichment** - Each chunk stores `source`, `page_number`, `element_type`
4. **Vectorization** - Embeds text using sentence-transformers, upserts to Qdrant with hybrid search (sparse+dense)

**System Dependencies (required on VM):**
```bash
apt-get install -y poppler-utils tesseract-ocr
```

### Snapshot Workflow

- `scripts/snapshot_push.sh` (VM): Create Qdrant snapshot -> Upload to Wasabi S3
- `scripts/snapshot_pull.sh` (Laptop): Download latest snapshot -> Extract to data/qdrant_snapshot

## Common Commands

```bash
make up-online     # Start production stack (VM with ingest)
make up-offline    # Start offline stack (laptop, read-only Qdrant)
make up-local      # Alias for up-offline
make sync-down     # Pull latest Qdrant snapshot from Wasabi S3
make test-api      # Run pytest on API service
make ingest-dev    # Run ingest service locally (development)
make clean         # Stop all containers and remove volumes
```

### Running API Locally (without Docker)

```bash
cd api && python -m src.app      # Starts uvicorn on port 8000 with mock clients
```

### Testing

```bash
make test-api                           # Run all API tests
cd api && pytest tests/test_query.py    # Run specific test file
cd api && pytest -k "test_health"       # Run tests matching pattern
cd api && pytest -v --tb=long           # Verbose output with full tracebacks
```

Tests use `use_mock_clients=True` by default, so no external services needed.

### Scripts

```bash
./scripts/setup.sh              # Initial setup (creates .env, pulls images)
./scripts/snapshot_push.sh      # Push snapshot to S3 (VM only)
./scripts/snapshot_pull.sh      # Pull latest snapshot from S3
./scripts/restore.sh <name>     # Restore specific snapshot by name
```

## Development Guidelines

- **Style:** PEP 8 compliant, fully typed Python
- **Models:** Use Pydantic models for all data structures
- **Error Handling:** Fail fast, log structured JSON (use structlog)
- **Secrets:** Never commit `.env` - use `.env.example` as template

## Key Environment Variables

See `.env.example` for full list. Critical ones:
- `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION`
- `OLLAMA_HOST`, `OLLAMA_MODEL`
- `WASABI_ACCESS_KEY`, `WASABI_SECRET_KEY`, `WASABI_BUCKET`
- `EMBEDDING_MODEL` (sentence-transformers model name)
- `INGEST_WATCH_DIR`, `INGEST_BATCH_SIZE` (VM ingest service)
