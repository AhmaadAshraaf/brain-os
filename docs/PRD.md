# Product Requirements Document: Brain-OS v3.0

**Document Version:** 1.0
**Last Updated:** 2026-01-13
**Status:** Active Development

---

## Executive Summary

Brain-OS v3.0 is a **Deep Document Understanding RAG (Retrieval-Augmented Generation) system** designed for offline-first document research. It implements a "Write Once, Read Anywhere" architecture where heavy document processing happens on a cloud VM, while offline laptops access synchronized snapshots for instant, zero-latency queries.

**Key Differentiator:** Unlike traditional RAG systems that require constant internet connectivity and re-processing, Brain-OS enables deep research on complex documents (with tables, images, multi-column layouts) in completely offline environments.

---

## Problem Statement

### Current Limitations of RAG Systems

1. **Online Dependency:** Most RAG systems require constant API access to embedding services and LLMs
2. **Shallow Parsing:** Standard text extraction misses complex document structures (tables, figures, layouts)
3. **Ingestion Overhead:** Every user must process documents individually, wasting compute resources
4. **Keyword vs Semantic Trade-off:** Systems optimize for either BM25 (keyword) or dense vectors (semantic), rarely both

### Our Solution

Brain-OS solves these problems through:
- **Hybrid Search:** Combines sparse (BM25-style) and dense (semantic) vectors for precision + recall
- **Centralized Ingestion:** Heavy processing (OCR, layout analysis, embedding) happens once on a VM
- **Snapshot Distribution:** Vectorized knowledge is distributed via S3, enabling offline querying
- **Deep Layout Understanding:** Uses Unstructured.io with `hi_res` strategy to extract tables, figures, and multi-column text

---

## Architecture Overview

### Write Once, Read Anywhere (WORA)

```
┌─────────────────────────────────────────────────────────────┐
│                     ONLINE VM (Hetzner)                      │
│  ┌────────────┐   ┌──────────────┐   ┌─────────────────┐   │
│  │  Documents │──▶│    Ingest    │──▶│    Qdrant DB    │   │
│  │  (PDFs)    │   │   Pipeline   │   │ (Hybrid Vectors)│   │
│  └────────────┘   └──────────────┘   └─────────────────┘   │
│                           │                     │            │
│                           │                     ▼            │
│                           │            ┌──────────────────┐ │
│                           │            │ Snapshot Creator │ │
│                           │            └────────┬─────────┘ │
│                           │                     │            │
└───────────────────────────┼─────────────────────┼───────────┘
                            │                     │
                            ▼                     ▼
                    ┌──────────────────────────────────┐
                    │       Wasabi S3 Bucket          │
                    │  (Snapshot Bridge & Archive)     │
                    └──────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────┐
│                   OFFLINE LAPTOP (Read-Only)                 │
│  ┌────────────────┐   ┌────────────┐   ┌────────────────┐  │
│  │ Snapshot Pull  │──▶│  Qdrant DB │◀──│  Query API     │  │
│  │    Script      │   │ (Read-Only)│   │  + Ollama LLM  │  │
│  └────────────────┘   └────────────┘   └────────────────┘  │
│                                                 │            │
│                                                 ▼            │
│                                          ┌────────────────┐ │
│                                          │  User Research │ │
│                                          │   (Offline)    │ │
│                                          └────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Environment | Role | Dependencies |
|-----------|------------|------|--------------|
| **Ingest Service** | VM Only | Parse PDFs, extract layout, embed text, upsert vectors | Poppler, Tesseract, Unstructured, sentence-transformers |
| **Qdrant DB** | Both | Vector storage with hybrid search (sparse + dense) | None (embedded) |
| **Ollama LLM** | Both | Local inference for answer synthesis | GPU (optional, CPU fallback) |
| **Query API** | Both | `/query` endpoint: retrieves citations, synthesizes answers | Qdrant, Ollama |
| **Snapshot Scripts** | Both | Push (VM) / Pull (Laptop) vector snapshots to/from S3 | Wasabi S3 credentials |

---

## Technical Stack

### Core Technologies

- **Orchestration:** Docker Compose (base + prod/local overlays)
- **Backend:** FastAPI (Python 3.11, fully typed with Pydantic)
- **Vector Database:** Qdrant (Hybrid Search: Sparse + Dense vectors)
- **Document Parsing:** Unstructured.io with Layout-Parser (multi-modal: Text, Tables, Images)
- **LLM:** Ollama (`llama3.1:8b` for local inference)
- **Embedding Model:** sentence-transformers (`all-MiniLM-L6-v2`, 384-dim dense vectors)
- **Object Storage:** Wasabi S3 (snapshot bridge between environments)
- **Monitoring:** Prometheus (VM only)

### System Dependencies (VM Only)

The ingestion pipeline requires native libraries for OCR and PDF processing:

```bash
apt-get install -y poppler-utils tesseract-ocr
```

These are **NOT** required on offline laptops (no ingestion).

---

## Deep Research Capabilities

### 1. Hybrid Search Architecture

Brain-OS implements **true hybrid search** by combining two complementary retrieval strategies:

#### Sparse Vectors (BM25-style Keyword Search)
- **Purpose:** Precision retrieval for exact terms, acronyms, product codes
- **Implementation:** Term frequency with IDF modifier (Qdrant's `Modifier.IDF`)
- **Vector Generation:** Hash-based sparse representation of document tokens
- **Use Case:** "Find all mentions of 'ISO-27001' or 'GDPR Article 32'"

#### Dense Vectors (Semantic Similarity Search)
- **Purpose:** Recall retrieval for conceptual queries, paraphrased questions
- **Implementation:** sentence-transformers (`all-MiniLM-L6-v2`, 384 dimensions)
- **Vector Generation:** Neural embedding of text chunks
- **Use Case:** "What are the security compliance requirements?" (matches even if document uses different wording)

#### Query Flow

```python
# Example: User query "What are the data retention policies?"

# 1. Generate both vector types from query
dense_query_vector = embed_model.encode(query)  # 384-dim
sparse_query_vector = compute_tf_idf(query)      # Hash-based sparse

# 2. Qdrant hybrid search (internal fusion)
results = qdrant.search(
    collection="brain_os_docs",
    query_vector={"dense": dense_query_vector, "sparse": sparse_query_vector},
    limit=5
)

# 3. Returns ranked results combining both signals
# - "retention" (exact keyword match via sparse)
# - "How long we keep customer information" (semantic match via dense)
```

### 2. Advanced Layout Understanding

#### Hi-Res PDF Parsing Strategy

Brain-OS uses Unstructured.io's `strategy="hi_res"` with `infer_table_structure=True`:

```python
elements = partition_pdf(
    filename=pdf_path,
    strategy="hi_res",           # OCR + layout analysis (vs "fast" text-only)
    infer_table_structure=True,  # Detect and parse tabular data
)
```

**What This Enables:**
- **Multi-column layouts:** Correctly orders text from academic papers, magazines
- **Table extraction:** Converts tables to searchable text (`"Table data: ..."` prefix)
- **Image captions:** Links figures to surrounding context
- **Hierarchical structure:** Preserves headings, lists, footnotes

#### Table Flattening for Deep Research

Tables are critical for research but hard to search. Brain-OS flattens them:

```python
# Input: PDF table with quarterly revenue
# ┌─────────┬──────────┬──────────┐
# │ Quarter │ Revenue  │ Growth % │
# ├─────────┼──────────┼──────────┤
# │ Q1 2025 │ $2.4M    │ 12%      │
# │ Q2 2025 │ $2.9M    │ 21%      │
# └─────────┴──────────┴──────────┘

# Output: Searchable text chunk
chunk.text = "Table data: <table><tr><th>Quarter</th><th>Revenue</th>..."
chunk.element_type = "Table"
chunk.page_number = 7
chunk.source = "Q2_financial_report.pdf"
```

**Research Benefit:** LLM can now extract numerical data from tables in retrieved context and cite the source page.

### 3. Deep Research Prompting

The `/query` endpoint formats retrieved citations with source attribution for LLM synthesis:

```python
# Format for LLM context
context = ""
for citation in search_results:
    context += f"SOURCE: {citation.source} | PAGE: {citation.page_number}\n"
    context += f"CONTENT: {citation.text}\n\n"

# LLM prompt (simplified)
prompt = f"""
You are a research assistant. Answer the question using ONLY the provided sources.
Cite every claim as [Source_Name, Page_X].

SOURCES:
{context}

QUESTION: {user_query}

ANSWER:
"""
```

**Example Output:**
> According to the financial reports, Q2 revenue grew 21% to $2.9M [Q2_financial_report.pdf, Page 7]. This exceeded the forecasted growth of 15% [Annual_Plan_2025.pdf, Page 23].

### 4. Metadata-Rich Chunking

Every document chunk stores structured metadata for provenance:

```python
@dataclass
class DocumentChunk:
    text: str              # The actual content (or flattened table)
    source: str            # Filename (e.g., "research_paper.pdf")
    page_number: int       # Page where this chunk appears
    element_type: str      # "Text", "Title", "Table", "ListItem", etc.
```

**Use Cases:**
- **Citation accuracy:** LLM references specific pages, not just "the document"
- **Filtering:** Query only tables (`element_type="Table"`) for data extraction
- **Debugging:** Trace incorrect answers back to source chunks

---

## Wasabi S3 Snapshot Bridge

### Why Snapshots?

**Problem:** Qdrant's vector database can be gigabytes in size. Syncing individual vectors over the network is slow and error-prone.

**Solution:** Qdrant's native snapshot feature creates compressed archives of the entire collection. Brain-OS uses Wasabi S3 as a bridge to distribute these snapshots.

### Snapshot Workflow

#### On VM (Writer Environment)

```bash
# scripts/snapshot_push.sh
# 1. Create Qdrant snapshot via API
SNAPSHOT_NAME=$(curl -X POST http://localhost:6333/collections/brain_os_docs/snapshots | jq -r '.result.name')

# 2. Download snapshot file from Qdrant container
docker cp qdrant:/qdrant/snapshots/brain_os_docs/$SNAPSHOT_NAME ./snapshot.tar

# 3. Upload to Wasabi S3 with timestamp
aws s3 cp ./snapshot.tar s3://brain-os-snapshots/$(date +%Y%m%d_%H%M%S)_snapshot.tar \
    --endpoint-url=https://s3.wasabisys.com
```

#### On Laptop (Reader Environment)

```bash
# scripts/snapshot_pull.sh
# 1. List available snapshots from S3 (sorted by date)
LATEST=$(aws s3 ls s3://brain-os-snapshots/ --endpoint-url=https://s3.wasabisys.com | sort | tail -n1 | awk '{print $4}')

# 2. Download latest snapshot
aws s3 cp s3://brain-os-snapshots/$LATEST ./snapshot.tar --endpoint-url=https://s3.wasabisys.com

# 3. Extract to Qdrant storage directory
mkdir -p data/qdrant_snapshot/collections/brain_os_docs
tar -xf ./snapshot.tar -C data/qdrant_snapshot/collections/brain_os_docs

# 4. Restart Qdrant to load the new snapshot
docker compose -f infra/docker-compose.base.yml -f infra/docker-compose.local.yml restart qdrant
```

### Snapshot Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Compression** | ~70% size reduction | Qdrant snapshots are tar.gz compressed |
| **Transfer time** | ~2-5 min for 1GB | Depends on internet speed, Wasabi has no egress fees |
| **Frequency** | On-demand or nightly | Triggered manually or via cron on VM |
| **Versioning** | Timestamp-based | Filename format: `YYYYMMDD_HHMMSS_snapshot.tar` |
| **Storage cost** | $0.0059/GB/month | Wasabi hot storage pricing (as of 2025) |

---

## API Design

### `/query` Endpoint

**Purpose:** Retrieve relevant citations and synthesize a research answer.

**Request:**
```json
POST /query
{
  "question": "What are the key findings on customer churn?",
  "top_k": 5
}
```

**Response:**
```json
{
  "citations": [
    {
      "source": "Q4_Analysis.pdf",
      "page_number": 12,
      "text": "Customer churn increased by 8% in Q4 2025, primarily in the SMB segment.",
      "element_type": "Text",
      "score": 0.87
    },
    {
      "source": "Churn_Report.pdf",
      "page_number": 3,
      "text": "Table data: <table><tr><th>Segment</th><th>Churn %</th>...</table>",
      "element_type": "Table",
      "score": 0.82
    }
  ],
  "reasoning": "Based on the financial analysis [Q4_Analysis.pdf, Page 12], customer churn increased 8% in Q4 2025. The SMB segment was most affected, with churn rates reaching 15% [Churn_Report.pdf, Page 3, Table 1]."
}
```

**Response Structure:**
- `citations` (List[Citation]): Specific document chunks from **sparse + dense vector search** (Linear Retrieval)
- `reasoning` (str): LLM-synthesized answer with inline citations (Non-Linear Synthesis)

### Health & Debugging Endpoints

- `GET /health`: Returns service status, Qdrant connection, Ollama availability
- `GET /collections/{name}`: Returns collection info (point count, vector config)
- `POST /embed`: Direct access to embedding model (for debugging)

---

## Use Cases

### 1. Offline Research Environments

**Scenario:** Field researchers studying documents in remote areas without internet.

**Workflow:**
1. HQ ingests all research papers, manuals, reports on the VM
2. Weekly snapshot pushed to Wasabi S3
3. Researchers download snapshot to laptop before field trip
4. Query documents offline using local Ollama LLM
5. Full citation trail maintained for later verification

**Benefit:** No internet required after initial snapshot sync.

### 2. Compliance & Audit Trails

**Scenario:** Legal teams researching case law, regulations, internal policies.

**Workflow:**
1. Ingest all compliance documents (GDPR, HIPAA, internal policies)
2. Hybrid search ensures both exact regulatory codes (sparse) and conceptual queries (dense) work
3. Every answer cites specific document + page number
4. Audit trail: "This decision was based on [GDPR_Guide.pdf, Page 47]"

**Benefit:** Precise provenance for regulatory compliance.

### 3. Multi-Modal Document Analysis

**Scenario:** Analyzing scientific papers with complex tables and figures.

**Workflow:**
1. Hi-res parsing extracts tables from PDFs
2. Table flattening makes numerical data searchable
3. Query: "What were the trial results for Group B?"
4. LLM extracts data from table chunks, cites page

**Benefit:** Deep extraction from structured data, not just prose.

### 4. Personal Knowledge Management

**Scenario:** Individual researchers building a "second brain" of notes, articles, books.

**Workflow:**
1. Drop PDFs into `/data/documents` on VM (or local dev setup)
2. Ingest pipeline processes automatically
3. Query across entire knowledge base: "What did I read about habit formation?"
4. Retrieve specific quotes with source attribution

**Benefit:** Unified search across heterogeneous document types.

---

## Performance Characteristics

### Ingestion Pipeline (VM)

| Stage | Time (per page) | Notes |
|-------|----------------|-------|
| **PDF Parsing (hi_res)** | ~2-5 seconds | Depends on layout complexity, OCR needs |
| **Embedding Generation** | ~50ms | sentence-transformers on CPU, ~10ms on GPU |
| **Qdrant Upsert** | ~10ms | Batched (default: 10 chunks/batch) |
| **Total** | ~2-6 sec/page | For 100-page document: 3-10 minutes |

### Query Performance (Offline Laptop)

| Operation | Latency | Notes |
|-----------|---------|-------|
| **Hybrid Vector Search** | ~50-200ms | Depends on collection size, typically <100ms for <1M vectors |
| **LLM Synthesis (Ollama)** | ~2-10 seconds | Depends on prompt length, model size (`llama3.1:8b`) |
| **Total Query Time** | ~3-12 seconds | End-to-end from question to synthesized answer |

**Key Insight:** After snapshot sync, **all queries are 100% offline** with sub-second vector search and fast local LLM inference.

---

## Constraints & Trade-offs

### Current Limitations

1. **Snapshot Staleness:** Offline laptop sees data as of last snapshot sync (not real-time)
2. **No Image Search:** Currently extracts text from images via OCR, but no CLIP-style image embeddings
3. **Language Support:** Optimized for English (embedding model + LLM), other languages require model swap
4. **Collection Name Hardcoded:** `brain_os_docs` is fixed in both ingest and API (not multi-tenant yet)

### Design Trade-offs

| Decision | Trade-off | Rationale |
|----------|-----------|-----------|
| **Centralized Ingestion (VM)** | Single point of failure | Enables WORA, avoids duplicate processing |
| **Snapshot Distribution (vs Real-time Sync)** | Data staleness | Dramatically reduces bandwidth, enables offline mode |
| **Local LLM (Ollama)** | Lower quality than GPT-4 | Enables offline inference, zero API costs |
| **Hybrid Search** | Increased storage (~2x vectors) | Massive improvement in retrieval quality |
| **Hi-res PDF Parsing** | Slower ingestion | Critical for accurate table/layout extraction |

---

## Future Enhancements

### Planned Features (Q1 2026)

1. **Multi-Modal Embeddings (CLIP):**
   - Embed images directly for visual search
   - Query: "Show me all charts about revenue growth"

2. **Incremental Snapshots:**
   - Only sync delta changes (new documents) instead of full collection
   - Reduces sync time from minutes to seconds

3. **Real-time Ingestion Mode:**
   - Optional WebSocket-based live sync for VM<->Laptop
   - Balances offline-first with fresh data needs

4. **Multi-Tenancy:**
   - Support multiple collections (e.g., `customer_A_docs`, `customer_B_docs`)
   - Namespace isolation for shared infrastructure

5. **Query Analytics:**
   - Track which documents are queried most
   - Surface "orphaned" documents (ingested but never retrieved)

### Research Directions

- **Agentic RAG:** LLM decides which collections to search, reformulates queries
- **Cross-Document Reasoning:** "Compare findings in Report A vs Report B"
- **Causal Inference:** "What factors correlate with churn increase?"

---

## Success Metrics

### Ingestion Quality

- **Parse Success Rate:** >95% of PDFs processed without errors
- **Table Extraction Accuracy:** >90% of tables correctly identified and flattened
- **Embedding Coverage:** 100% of extracted chunks have valid vectors

### Query Quality

- **Retrieval Precision@5:** >80% of top-5 results are relevant
- **Citation Accuracy:** >95% of LLM citations match actual source pages
- **Answer Correctness:** Manual evaluation, target >85% factually accurate

### System Performance

- **Ingestion Throughput:** >1000 pages/hour on VM
- **Query Latency (p95):** <15 seconds end-to-end
- **Snapshot Sync Time:** <10 minutes for 5GB collection

### User Adoption

- **Offline Usage Rate:** >50% of queries happen without internet connectivity
- **Query Frequency:** >10 queries/user/week (indicates utility)
- **Document Retention:** <5% of ingested documents deleted (indicates value)

---

## Appendix A: Docker Compose Structure

Brain-OS uses an **overlay pattern** with a shared base:

```
infra/
├── docker-compose.base.yml      # Shared: Qdrant, Ollama, API
├── docker-compose.prod.yml      # VM overlay: +Ingest, +Prometheus
└── docker-compose.local.yml     # Laptop overlay: read-only Qdrant
```

**Commands:**
- `make up-online`: Starts base + prod (VM with ingestion)
- `make up-offline`: Starts base + local (Laptop, read-only)

**Key Difference:**
- **Prod:** Qdrant uses writable volume, Ingest service writes vectors
- **Local:** Qdrant mounts snapshot directory read-only, no writes

---

## Appendix B: Environment Variables

See `.env.example` for full list. Critical variables:

```bash
# Qdrant Configuration
QDRANT_HOST=localhost           # "qdrant" in Docker
QDRANT_PORT=6333
QDRANT_COLLECTION=brain_os_docs

# LLM Configuration
OLLAMA_HOST=localhost           # "ollama" in Docker
OLLAMA_PORT=11434
OLLAMA_MODEL=llama3.1:8b

# Embedding Configuration
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Ingestion Configuration (VM only)
INGEST_WATCH_DIR=/app/documents
INGEST_BATCH_SIZE=10

# Wasabi S3 Configuration
WASABI_ACCESS_KEY=<your_key>
WASABI_SECRET_KEY=<your_secret>
WASABI_BUCKET=brain-os-snapshots
WASABI_REGION=us-east-1
```

---

## Appendix C: Testing Strategy

### Unit Tests

- **API Tests:** `cd api && pytest tests/` (uses mock clients)
- **Ingest Tests:** `make test-ingest` (runs in Docker with real dependencies)

### Integration Tests (Planned)

- End-to-end: Ingest sample PDF → Query → Validate citation accuracy
- Snapshot roundtrip: Push to S3 → Pull on separate env → Verify data integrity

### Performance Tests (Planned)

- Load testing: 1000 concurrent queries to API
- Ingestion benchmark: 10,000-page document corpus

---

## Appendix D: Deployment Checklist

### VM Deployment (First Time)

- [ ] Provision Hetzner VM (Ubuntu 22.04, 8GB RAM, 100GB SSD)
- [ ] Install Docker, Docker Compose
- [ ] Clone repo: `git clone https://github.com/yourorg/brain-os.git`
- [ ] Copy `.env.example` to `.env`, fill in Wasabi credentials
- [ ] Run `./scripts/setup.sh` (pulls Docker images, Ollama model)
- [ ] Start services: `make up-online`
- [ ] Upload sample PDFs to `data/documents/`
- [ ] Monitor ingestion: `docker compose logs -f ingest`
- [ ] Verify collection: `curl http://localhost:6333/collections/brain_os_docs`
- [ ] Push first snapshot: `./scripts/snapshot_push.sh`

### Laptop Setup (First Time)

- [ ] Install Docker, Docker Compose
- [ ] Clone repo: `git clone https://github.com/yourorg/brain-os.git`
- [ ] Copy `.env.example` to `.env` (use same Wasabi creds as VM)
- [ ] Run `./scripts/setup.sh`
- [ ] Pull snapshot: `make sync-down` (downloads from S3)
- [ ] Start services: `make up-offline`
- [ ] Test query: `curl -X POST http://localhost:8000/query -d '{"question": "test"}'`

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-13 | Claude Sonnet 4.5 | Initial PRD creation for Tuesday Milestone |

---

**END OF DOCUMENT**
