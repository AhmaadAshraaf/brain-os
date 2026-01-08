"""
Document ingestion pipeline for Brain-OS.

Parses PDFs using unstructured with hi-res strategy, extracts text and tables,
embeds content using sentence-transformers, and upserts to Qdrant with hybrid search.
"""

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
    models,
)
from sentence_transformers import SentenceTransformer
from unstructured.partition.pdf import partition_pdf

load_dotenv()

logger = structlog.get_logger(__name__)


@dataclass
class DocumentChunk:
    """A processed chunk ready for vectorization."""

    text: str
    source: str
    page_number: int
    element_type: str


class QdrantVectorClient:
    """
    Production Qdrant client for vector storage operations.

    Handles collection creation, embedding generation, and hybrid search upserts
    using both dense and sparse vectors.
    """

    COLLECTION_NAME = "brain_os_docs"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        embedding_model: str | None = None,
    ) -> None:
        """
        Initialize the Qdrant vector client.

        Args:
            host: Qdrant host. Defaults to QDRANT_HOST env var or 'localhost'.
            port: Qdrant port. Defaults to QDRANT_PORT env var or 6333.
            embedding_model: Sentence-transformers model name. Defaults to EMBEDDING_MODEL env var.
        """
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.embedding_model_name = embedding_model or os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )

        logger.info(
            "initializing_qdrant_client",
            host=self.host,
            port=self.port,
            embedding_model=self.embedding_model_name,
        )

        self.client = QdrantClient(host=self.host, port=self.port)
        self.embedding_model = SentenceTransformer(self.embedding_model_name)
        self.vector_size = self.embedding_model.get_sentence_embedding_dimension()

        logger.info(
            "qdrant_client_initialized",
            vector_size=self.vector_size,
            collection_name=self.COLLECTION_NAME,
        )

    def ensure_collection_exists(self) -> None:
        """
        Create the collection if it doesn't exist.

        Creates a collection with dense vectors for semantic search and
        sparse vectors for keyword/BM25-style search (hybrid search).
        """
        try:
            collection_info = self.client.get_collection(self.COLLECTION_NAME)
            logger.info(
                "collection_exists",
                collection_name=self.COLLECTION_NAME,
                points_count=collection_info.points_count,
            )
        except (UnexpectedResponse, Exception) as e:
            if "Not found" in str(e) or "404" in str(e):
                logger.info(
                    "creating_collection",
                    collection_name=self.COLLECTION_NAME,
                    vector_size=self.vector_size,
                )

                self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config={
                        "dense": VectorParams(
                            size=self.vector_size,
                            distance=Distance.COSINE,
                        ),
                    },
                    sparse_vectors_config={
                        "sparse": SparseVectorParams(
                            modifier=models.Modifier.IDF,
                        ),
                    },
                )

                logger.info(
                    "collection_created",
                    collection_name=self.COLLECTION_NAME,
                )
            else:
                logger.error(
                    "collection_check_failed",
                    collection_name=self.COLLECTION_NAME,
                    error=str(e),
                )
                raise

    def _compute_sparse_vector(self, text: str) -> SparseVector:
        """
        Compute a simple sparse vector from text using term frequency.

        This creates a basic sparse representation for hybrid search.
        For production, consider using a proper BM25 implementation.

        Args:
            text: Input text to vectorize.

        Returns:
            SparseVector with term indices and values.
        """
        words = text.lower().split()
        word_freq: dict[str, int] = {}
        for word in words:
            cleaned = "".join(c for c in word if c.isalnum())
            if cleaned and len(cleaned) > 2:
                word_freq[cleaned] = word_freq.get(cleaned, 0) + 1

        indices = []
        values = []
        for word, freq in word_freq.items():
            word_hash = hash(word) % (2**31)
            indices.append(word_hash)
            values.append(float(freq))

        return SparseVector(indices=indices, values=values)

    def upsert_chunks(self, chunks: list[DocumentChunk], batch_size: int = 10) -> int:
        """
        Embed and upsert document chunks to Qdrant.

        Args:
            chunks: List of DocumentChunk objects to upsert.
            batch_size: Number of chunks to process per batch.

        Returns:
            Number of points successfully upserted.
        """
        if not chunks:
            logger.warning("no_chunks_to_upsert")
            return 0

        self.ensure_collection_exists()

        total_upserted = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [chunk.text for chunk in batch]

            logger.info(
                "embedding_batch",
                batch_index=i // batch_size,
                batch_size=len(batch),
            )

            dense_embeddings = self.embedding_model.encode(texts, show_progress_bar=False)

            points = []
            for j, (chunk, dense_vector) in enumerate(zip(batch, dense_embeddings)):
                point_id = str(uuid.uuid4())
                sparse_vector = self._compute_sparse_vector(chunk.text)

                point = PointStruct(
                    id=point_id,
                    vector={
                        "dense": dense_vector.tolist(),
                        "sparse": sparse_vector,
                    },
                    payload={
                        "text": chunk.text,
                        "source": chunk.source,
                        "page_number": chunk.page_number,
                        "element_type": chunk.element_type,
                    },
                )
                points.append(point)

            self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points,
            )

            total_upserted += len(points)
            logger.info(
                "batch_upserted",
                batch_index=i // batch_size,
                points_in_batch=len(points),
                total_upserted=total_upserted,
            )

        logger.info(
            "upsert_completed",
            total_chunks=len(chunks),
            total_upserted=total_upserted,
        )

        return total_upserted


class DocumentProcessor:
    """
    Processes documents through the ingestion pipeline.

    Extracts text and tables from PDFs using layout analysis,
    flattens tables into searchable text, and uploads to vector storage.
    """

    def __init__(
        self,
        watch_dir: str | None = None,
        vector_client: QdrantVectorClient | None = None,
    ) -> None:
        """
        Initialize the document processor.

        Args:
            watch_dir: Directory to watch for documents. Defaults to INGEST_WATCH_DIR env var.
            vector_client: QdrantVectorClient instance. Created if not provided.
        """
        self.watch_dir = Path(watch_dir or os.getenv("INGEST_WATCH_DIR", "/app/documents"))
        self.batch_size = int(os.getenv("INGEST_BATCH_SIZE", "10"))
        self.vector_client = vector_client or QdrantVectorClient()

        logger.info(
            "document_processor_initialized",
            watch_dir=str(self.watch_dir),
            batch_size=self.batch_size,
        )

    def parse_pdf(self, file_path: Path) -> list[DocumentChunk]:
        """
        Parse a PDF file using hi-res strategy with table structure inference.

        Args:
            file_path: Path to the PDF file.

        Returns:
            List of DocumentChunk objects with extracted content and metadata.
        """
        logger.info("parsing_pdf_started", file_path=str(file_path))

        elements = partition_pdf(
            filename=str(file_path),
            strategy="hi_res",
            infer_table_structure=True,
        )

        chunks: list[DocumentChunk] = []
        source = file_path.name

        for element in elements:
            element_type = element.category if hasattr(element, "category") else type(element).__name__
            page_number = getattr(element.metadata, "page_number", 1) or 1

            if element_type == "Table":
                table_content = getattr(element.metadata, "text_as_html", None) or element.text
                text = f"Table data: {table_content}"
            else:
                text = element.text

            if not text or not text.strip():
                continue

            chunk = DocumentChunk(
                text=text.strip(),
                source=source,
                page_number=page_number,
                element_type=element_type,
            )
            chunks.append(chunk)

        element_types = {}
        for c in chunks:
            element_types[c.element_type] = element_types.get(c.element_type, 0) + 1

        logger.info(
            "parsing_pdf_completed",
            file_path=str(file_path),
            total_chunks=len(chunks),
            element_types=element_types,
        )

        return chunks

    def process_and_upload(self, file_path: Path) -> int:
        """
        Process a document and upload chunks to Qdrant.

        Args:
            file_path: Path to the document to process.

        Returns:
            Number of chunks successfully uploaded.
        """
        logger.info("processing_file_started", file_path=str(file_path))

        try:
            chunks = self.parse_pdf(file_path)

            if not chunks:
                logger.warning("no_chunks_extracted", file_path=str(file_path))
                return 0

            upserted = self.vector_client.upsert_chunks(chunks, batch_size=self.batch_size)

            logger.info(
                "processing_file_completed",
                file_path=str(file_path),
                chunks_extracted=len(chunks),
                chunks_upserted=upserted,
            )

            return upserted

        except Exception as e:
            logger.error(
                "processing_file_failed",
                file_path=str(file_path),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def process_directory(self) -> dict[str, int]:
        """
        Process all PDF files in the watch directory.

        Returns:
            Dictionary mapping filenames to number of chunks uploaded.
        """
        if not self.watch_dir.exists():
            logger.error("watch_dir_not_found", watch_dir=str(self.watch_dir))
            return {}

        pdf_files = list(self.watch_dir.glob("*.pdf"))
        logger.info(
            "processing_directory_started",
            watch_dir=str(self.watch_dir),
            pdf_count=len(pdf_files),
        )

        results: dict[str, int] = {}
        successful = 0
        failed = 0

        for pdf_file in pdf_files:
            try:
                chunks_uploaded = self.process_and_upload(pdf_file)
                results[pdf_file.name] = chunks_uploaded
                successful += 1
            except Exception as e:
                logger.error(
                    "document_processing_failed",
                    file_path=str(pdf_file),
                    error=str(e),
                )
                results[pdf_file.name] = 0
                failed += 1

        logger.info(
            "processing_directory_completed",
            total_files=len(pdf_files),
            successful=successful,
            failed=failed,
            total_chunks=sum(results.values()),
        )

        return results


def main() -> None:
    """Entry point for the ingest service."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )

    logger.info("ingest_service_starting")

    try:
        processor = DocumentProcessor()
        results = processor.process_directory()

        logger.info(
            "ingest_service_completed",
            files_processed=len(results),
            total_chunks=sum(results.values()),
        )

    except Exception as e:
        logger.error(
            "ingest_service_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


if __name__ == "__main__":
    main()
