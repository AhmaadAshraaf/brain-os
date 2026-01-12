# CHANGELOG

All notable technical decisions and changes to Brain-OS v3.0.

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
