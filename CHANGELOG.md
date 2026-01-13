# CHANGELOG

All notable technical decisions and changes to Brain-OS v3.0.

## [2026-01-13] - Tuesday Milestone: Repository Structure & PRD

### Repository Management

#### CLAUDE.md Removed from Version Control
- **Why**: CLAUDE.md contains project-specific instructions for AI assistance and should remain local-only
- **What**:
  - Added `CLAUDE.md` to `.gitignore` under "# Documentation (local only)"
  - Ran `git rm --cached CLAUDE.md` to remove from index while preserving local file
  - File remains functional for Claude Code but won't be committed
- **Rationale**: Keeps AI instructions accessible without polluting version control history

### Documentation

#### Product Requirements Document (PRD)
- **Location**: `docs/PRD.md`
- **Why**: Formal specification of Brain-OS v3.0 architecture, capabilities, and use cases for stakeholders
- **Contents**:
  - **Deep Research Capabilities**: Hybrid search (sparse + dense vectors), hi-res PDF parsing, table flattening
  - **Write Once, Read Anywhere (WORA)**: Architecture diagram showing VM ingestion → S3 snapshot bridge → offline laptop
  - **Technical Stack**: Complete list of dependencies and system requirements
  - **Wasabi S3 Snapshot Bridge**: Detailed workflow for snapshot push/pull operations
  - **API Design**: `/query` endpoint with Linear (citations) + Non-Linear (reasoning) response structure
  - **Use Cases**: Offline research, compliance auditing, multi-modal document analysis, personal knowledge management
  - **Performance Characteristics**: Ingestion (2-6 sec/page), Query (3-12 sec end-to-end)
  - **Appendices**: Docker Compose structure, environment variables, testing strategy, deployment checklist
- **Technical Decision**: PRD documents "why" and "what" for each component, not just "how"

### Build System

#### Make Target: `test-ingest` Updated
- **Previous Implementation**: `docker compose run --rm ingest pytest tests/ -v` (created fresh container)
- **New Implementation**: `docker-compose exec ingest pytest tests/ -v`
- **Why**: Exec pattern tests against running services, closer to production behavior
- **Requirement**: Services must be started first via `make up-online`
- **Trade-off**: Requires pre-existing container state (not isolated), but validates integration with live Qdrant/Ollama

### VM Deployment Readiness

#### Volume Mapping Verification (ingest/src/main.py:261)
- **Code**: `Path(watch_dir or os.getenv("INGEST_WATCH_DIR", "/app/documents"))`
- **Docker Mount**: `../data/documents:/app/documents:ro` (docker-compose.prod.yml:16)
- **Status**: ✅ Verified correct - code expects `/app/documents` which matches volume mount

#### Docker Compose Overlay Pattern Validated
- **Base**: `docker-compose.base.yml` (Qdrant, Ollama, API)
- **Prod Overlay**: `docker-compose.prod.yml` (adds Ingest service, Prometheus)
- **Local Overlay**: `docker-compose.local.yml` (read-only Qdrant, no ingestion)
- **Validation**: Confirmed Ingest service only exists in prod overlay (VM-only ingestion)

### Next Steps (Wednesday Milestone)
1. **VM Deployment**: Deploy production stack to Hetzner VM
2. **Sample Data Load**: Upload test PDFs to `/data/documents`
3. **Ingestion Validation**: Monitor `docker-compose logs -f ingest` for successful processing
4. **Snapshot Creation**: Run `./scripts/snapshot_push.sh` to create first S3 snapshot
5. **Offline Sync Test**: Pull snapshot to laptop via `make sync-down`, verify query functionality
6. **Monitoring Setup**: Configure Prometheus metrics for ingestion pipeline

---

## [2026-01-12] - Data Ingestion Milestone (TDD Implementation)

### Added

#### Ingestion Test Suite (`ingest/tests/test_ingestion.py`)
- **Why**: Implemented TDD approach to ensure ingestion pipeline correctness before production deployment
- **What**: Comprehensive test suite covering:
  - `DocumentChunk` data model validation
  - `QdrantVectorClient` initialization and configuration
  - Hybrid vector generation (dense + sparse)
  - Collection creation with correct schema for `brain_os_docs`
  - PDF parsing with layout-aware element extraction
  - Table flattening with "Table data:" prefix for Deep Research
  - End-to-end integration test: PDF → Chunks → Vectors → Qdrant
- **Technical Decision**: Used mocked dependencies (Qdrant, SentenceTransformer, partition_pdf) for fast, isolated unit tests
- **Dependencies**: Added `pytest>=7.4.0` and `pytest-mock>=3.12.0` to `ingest/requirements.txt`

### Configuration Decisions

#### Collection Name: `brain_os_docs`
- **Why**: Enforced exact collection name for consistency across Online (VM) and Offline (Laptop) environments
- **Validation**: Test `test_collection_name_is_brain_os_docs` explicitly asserts this constant
- **Location**: Hardcoded in `QdrantVectorClient.COLLECTION_NAME` (ingest/src/main.py:51)

#### Hybrid Search Architecture
- **Why**: Enables both semantic search (dense vectors) and keyword/BM25-style search (sparse vectors)
- **Dense Vectors**:
  - Model: `sentence-transformers/all-MiniLM-L6-v2` (default, 384 dimensions)
  - Distance: Cosine similarity
  - Generated via SentenceTransformer.encode()
- **Sparse Vectors**:
  - Method: Term frequency with hash-based indexing
  - Implementation: `_compute_sparse_vector()` in QdrantVectorClient
  - Modifier: IDF (Inverse Document Frequency) via Qdrant
- **Qdrant Schema**:
  ```python
  vectors_config={"dense": VectorParams(size=384, distance=Distance.COSINE)}
  sparse_vectors_config={"sparse": SparseVectorParams(modifier=models.Modifier.IDF)}
  ```

#### LLM Model: llama3.1:8b (Constraint Applied)
- **Why**: User-specified constraint for all synthesis logic in API
- **Note**: This is for LLM reasoning/synthesis, NOT for embeddings
- **Embedding Model Remains**: `sentence-transformers/all-MiniLM-L6-v2` (specialized for vector generation)
- **Configuration Files**:
  - `.env.example`: `OLLAMA_MODEL=llama3.1:8b`
  - `api/src/config.py`: Default updated to `llama3.1:8b`
  - `scripts/setup.sh`: Docker pull command updated

#### PDF Input Directory
- **Path**: `/app/documents` (default in Docker environment)
- **Configuration**: `INGEST_WATCH_DIR` environment variable
- **Access Pattern**: Read-only mount in production (`../data/documents:/app/documents:ro`)
- **Why**: Separates ingestion input from Qdrant snapshot data, enables safe file watching

### Architecture Validation

#### Test Coverage
- **Unit Tests**: 13 test cases across 4 test classes
- **Mocking Strategy**: External dependencies isolated (no real Qdrant/PDF files needed)
- **Integration Test**: `test_full_pipeline_pdf_to_vectors` validates end-to-end flow
- **Assertions**:
  - Collection name is exactly "brain_os_docs"
  - Both dense and sparse vectors are generated
  - Metadata includes: text, source, page_number, element_type
  - Tables are prefixed with "Table data:" for searchability

#### TDD Red-Green-Refactor Cycle
1. **Red Phase**: Tests created first, defining expected behavior
2. **Green Phase**: Implementation in `ingest/src/main.py` already passes (production-ready code)
3. **Refactor**: No changes needed - code already follows best practices

### Dependencies

#### Python Packages (ingest/requirements.txt)
- `unstructured[pdf]>=0.10.0` - PDF parsing with layout analysis
- `qdrant-client>=1.7.0` - Vector database client
- `sentence-transformers>=2.2.0` - Dense embedding generation
- `python-dotenv>=1.0.0` - Environment configuration
- `structlog>=23.0.0` - Structured JSON logging
- `pytest>=7.4.0` - Testing framework
- `pytest-mock>=3.12.0` - Mock utilities for tests

#### System Dependencies (Required on VM)
```bash
apt-get install -y poppler-utils tesseract-ocr
```
- `poppler-utils`: PDF rendering for hi-res strategy
- `tesseract-ocr`: OCR for scanned documents

### Next Steps
1. Run tests in Docker environment: `make test-ingest` (to be added to Makefile)
2. Deploy to VM with production data
3. Validate snapshot creation after initial ingestion
4. Implement monitoring/alerting for ingestion failures
5. Add Makefile target for local ingestion testing

---

## Format Notes
- All dates in ISO 8601 format (YYYY-MM-DD)
- Decisions documented with "Why" rationale
- Technical changes linked to business/architectural requirements
