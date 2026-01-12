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

The ingest service (`ingest/src/main.py`) has two main classes:
- **`DocumentProcessor`** - Orchestrates the pipeline: watches directory, parses PDFs, sends to vector client
- **`QdrantVectorClient`** - Handles embedding generation (sentence-transformers) and Qdrant upserts

Processing flow:
1. **PDF Parsing** - Uses `unstructured.partition.pdf` with `strategy="hi_res"` and `infer_table_structure=True`
2. **Table Flattening** - Tables are converted to searchable text: `"Table data: {content}"` (enables Deep Research extraction)
3. **Metadata Enrichment** - Each `DocumentChunk` stores `source`, `page_number`, `element_type`
4. **Hybrid Vectorization** - Dense vectors via sentence-transformers + sparse vectors via term frequency, upserted to Qdrant

**System Dependencies (required on VM):**
```bash
apt-get install -y poppler-utils tesseract-ocr
```

### Deep Research Prompting (API)

The `/query` endpoint formats citations for LLM synthesis with source attribution:
```python
f"SOURCE: {source} | PAGE: {page}\nCONTENT: {text}"
```
The LLM is instructed to cite claims as `[Source_Name, Page_X]` and extract numerical data from flattened tables.

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

**Import Pattern:** Tests import from `api.src.app` (not `src.app`) - run pytest from the `api/` directory or project root.

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
- `OLLAMA_HOST`, `OLLAMA_MODEL` (currently: `llama3.1:8b`)
- `WASABI_ACCESS_KEY`, `WASABI_SECRET_KEY`, `WASABI_BUCKET`
- `EMBEDDING_MODEL` (sentence-transformers model name, default: `sentence-transformers/all-MiniLM-L6-v2`)
- `INGEST_WATCH_DIR`, `INGEST_BATCH_SIZE` (VM ingest service)

---

## Current System State (2026-01-12)

### Completed Milestones

#### ✅ Data Ingestion Pipeline with TDD (Jan 12, 2026)
- **Status:** Production-ready, fully tested
- **Test Coverage:** 13 test cases in `ingest/tests/test_ingestion.py`
- **Key Components:**
  - `DocumentProcessor` - PDF parsing with hi-res layout analysis
  - `QdrantVectorClient` - Hybrid vector generation and Qdrant upserts
  - Collection name enforced: `brain_os_docs`
  - Input directory: `/app/documents` (configurable via `INGEST_WATCH_DIR`)
- **Hybrid Search Validated:**
  - Dense vectors: 384-dimensional (sentence-transformers/all-MiniLM-L6-v2)
  - Sparse vectors: Term frequency with IDF modifier
  - Both vector types tested and working
- **LLM Configuration:** Updated to `llama3.1:8b` across all configs

### Next Steps

1. **Run Tests in Docker Environment**
   - Add `make test-ingest` to Makefile
   - Validate tests pass with real dependencies in container
   - Command: `docker-compose exec ingest pytest tests/ -v`

2. **VM Deployment**
   - Deploy ingestion service to Hetzner VM
   - Load sample PDFs into `/data/documents`
   - Monitor ingestion logs via `docker-compose logs -f ingest`
   - Verify Qdrant collection population: `curl http://localhost:6333/collections/brain_os_docs`

3. **Snapshot Creation & Sync**
   - Run `./scripts/snapshot_push.sh` after initial ingestion
   - Validate snapshot appears in Wasabi S3 bucket
   - Test `./scripts/snapshot_pull.sh` on laptop
   - Verify offline query functionality with downloaded snapshot

4. **API Integration Testing**
   - Switch API to real clients: `use_mock_clients=False` in config
   - Test `/query` endpoint with ingested documents
   - Validate citation accuracy (source, page_number)
   - Test Deep Research with table data extraction

5. **Monitoring & Observability**
   - Configure Prometheus metrics for ingestion pipeline
   - Add alerting for failed document processing
   - Dashboard: ingestion rate, error rate, collection size

6. **Documentation**
   - Update README with deployment instructions
   - Add troubleshooting guide for common ingestion errors
   - Document snapshot restore procedures

### Known Constraints
- Collection name must remain `brain_os_docs` (hardcoded in both ingest and API)
- LLM model: `llama3.1:8b` (per user specification)
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (not changed)
- Test suite requires mocked dependencies (no real Qdrant/PDF files for unit tests)

### Files Changed (Latest Commit: 8074fdf)
- `ingest/tests/test_ingestion.py` (NEW) - 13 test cases covering full pipeline
- `CHANGELOG.md` (NEW) - Technical decision log
- `api/src/config.py` - Updated `ollama_model` to `llama3.1:8b`
- `.env.example` - Updated `OLLAMA_MODEL` to `llama3.1:8b`
- `scripts/setup.sh` - Updated model pull to `llama3.1:8b`
- `ingest/requirements.txt` - Added pytest dependencies
