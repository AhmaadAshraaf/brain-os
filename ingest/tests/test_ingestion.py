"""
Test suite for document ingestion pipeline.

Tests PDF parsing, chunking, vector generation, and Qdrant integration
using mocked external dependencies for isolated unit testing.
"""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from qdrant_client.models import Distance, SparseVector, VectorParams

from ingest.src.main import DocumentChunk, DocumentProcessor, QdrantVectorClient


class TestDocumentChunk:
    """Test DocumentChunk data model."""

    def test_document_chunk_creation(self):
        """Test that DocumentChunk can be created with required fields."""
        chunk = DocumentChunk(
            text="Sample text content",
            source="test.pdf",
            page_number=1,
            element_type="NarrativeText",
        )

        assert chunk.text == "Sample text content"
        assert chunk.source == "test.pdf"
        assert chunk.page_number == 1
        assert chunk.element_type == "NarrativeText"


class TestQdrantVectorClient:
    """Test QdrantVectorClient with mocked Qdrant connection."""

    @patch("ingest.src.main.QdrantClient")
    @patch("ingest.src.main.SentenceTransformer")
    def test_client_initialization(self, mock_st, mock_qc):
        """Test that client initializes with correct parameters."""
        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_st.return_value = mock_model

        client = QdrantVectorClient(
            host="localhost",
            port=6333,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )

        assert client.host == "localhost"
        assert client.port == 6333
        assert client.COLLECTION_NAME == "brain_os_docs"
        assert client.vector_size == 384
        mock_qc.assert_called_once_with(host="localhost", port=6333)

    @patch("ingest.src.main.QdrantClient")
    @patch("ingest.src.main.SentenceTransformer")
    def test_collection_name_is_brain_os_docs(self, mock_st, mock_qc):
        """Verify that the collection name is exactly 'brain_os_docs'."""
        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_st.return_value = mock_model

        client = QdrantVectorClient()

        assert client.COLLECTION_NAME == "brain_os_docs"

    @patch("ingest.src.main.QdrantClient")
    @patch("ingest.src.main.SentenceTransformer")
    def test_ensure_collection_exists_creates_with_hybrid_vectors(self, mock_st, mock_qc):
        """Test collection creation with both dense and sparse vector configs."""
        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_st.return_value = mock_model

        mock_client_instance = Mock()
        mock_client_instance.get_collection.side_effect = Exception("Not found: 404")
        mock_qc.return_value = mock_client_instance

        client = QdrantVectorClient()
        client.ensure_collection_exists()

        mock_client_instance.create_collection.assert_called_once()
        call_args = mock_client_instance.create_collection.call_args

        assert call_args.kwargs["collection_name"] == "brain_os_docs"
        assert "dense" in call_args.kwargs["vectors_config"]
        assert "sparse" in call_args.kwargs["sparse_vectors_config"]

        dense_config = call_args.kwargs["vectors_config"]["dense"]
        assert dense_config.size == 384
        assert dense_config.distance == Distance.COSINE

    @patch("ingest.src.main.QdrantClient")
    @patch("ingest.src.main.SentenceTransformer")
    def test_compute_sparse_vector(self, mock_st, mock_qc):
        """Test sparse vector generation from text."""
        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_st.return_value = mock_model

        client = QdrantVectorClient()
        text = "The quick brown fox jumps over the lazy dog"
        sparse_vector = client._compute_sparse_vector(text)

        assert isinstance(sparse_vector, SparseVector)
        assert len(sparse_vector.indices) > 0
        assert len(sparse_vector.values) > 0
        assert len(sparse_vector.indices) == len(sparse_vector.values)

    @patch("ingest.src.main.QdrantClient")
    @patch("ingest.src.main.SentenceTransformer")
    def test_upsert_chunks_generates_dense_and_sparse_vectors(self, mock_st, mock_qc):
        """Test that upsert generates both dense and sparse vectors for hybrid search."""
        import numpy as np

        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_model.encode.return_value = np.random.rand(2, 384)
        mock_st.return_value = mock_model

        mock_client_instance = Mock()
        mock_client_instance.get_collection.return_value = Mock(points_count=0)
        mock_qc.return_value = mock_client_instance

        client = QdrantVectorClient()

        chunks = [
            DocumentChunk(
                text="First chunk about AI and machine learning",
                source="test.pdf",
                page_number=1,
                element_type="NarrativeText",
            ),
            DocumentChunk(
                text="Second chunk with technical content",
                source="test.pdf",
                page_number=2,
                element_type="NarrativeText",
            ),
        ]

        upserted_count = client.upsert_chunks(chunks, batch_size=10)

        assert upserted_count == 2
        mock_client_instance.upsert.assert_called_once()

        upsert_call = mock_client_instance.upsert.call_args
        assert upsert_call.kwargs["collection_name"] == "brain_os_docs"

        points = upsert_call.kwargs["points"]
        assert len(points) == 2

        for point in points:
            assert "dense" in point.vector
            assert "sparse" in point.vector
            assert isinstance(point.vector["dense"], list)
            assert len(point.vector["dense"]) == 384
            assert isinstance(point.vector["sparse"], SparseVector)
            assert len(point.vector["sparse"].indices) > 0
            assert len(point.vector["sparse"].values) > 0

    @patch("ingest.src.main.QdrantClient")
    @patch("ingest.src.main.SentenceTransformer")
    def test_upsert_chunks_includes_metadata(self, mock_st, mock_qc):
        """Test that chunks include all required metadata fields."""
        import numpy as np

        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_model.encode.return_value = np.random.rand(1, 384)
        mock_st.return_value = mock_model

        mock_client_instance = Mock()
        mock_client_instance.get_collection.return_value = Mock(points_count=0)
        mock_qc.return_value = mock_client_instance

        client = QdrantVectorClient()

        chunk = DocumentChunk(
            text="Table data: Revenue Q1 2024: $1.2M",
            source="financials.pdf",
            page_number=5,
            element_type="Table",
        )

        client.upsert_chunks([chunk])

        points = mock_client_instance.upsert.call_args.kwargs["points"]
        payload = points[0].payload

        assert payload["text"] == "Table data: Revenue Q1 2024: $1.2M"
        assert payload["source"] == "financials.pdf"
        assert payload["page_number"] == 5
        assert payload["element_type"] == "Table"


class TestDocumentProcessor:
    """Test DocumentProcessor with mocked PDF parsing."""

    @patch("ingest.src.main.QdrantVectorClient")
    def test_processor_initialization(self, mock_vector_client):
        """Test processor initializes with correct watch directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor = DocumentProcessor(watch_dir=tmpdir)

            assert processor.watch_dir == Path(tmpdir)
            assert processor.batch_size == 10

    @patch("ingest.src.main.partition_pdf")
    @patch("ingest.src.main.QdrantVectorClient")
    def test_parse_pdf_extracts_chunks(self, mock_vector_client, mock_partition):
        """Test PDF parsing extracts chunks with proper metadata."""
        mock_element1 = Mock()
        mock_element1.text = "First paragraph of text"
        mock_element1.category = "NarrativeText"
        mock_element1.metadata.page_number = 1

        mock_element2 = Mock()
        mock_element2.text = "<table>Revenue: $100k</table>"
        mock_element2.category = "Table"
        mock_element2.metadata.page_number = 2
        mock_element2.metadata.text_as_html = "<table>Revenue: $100k</table>"

        mock_partition.return_value = [mock_element1, mock_element2]

        processor = DocumentProcessor(watch_dir="/tmp/test")
        chunks = processor.parse_pdf(Path("/tmp/test/document.pdf"))

        assert len(chunks) == 2

        assert chunks[0].text == "First paragraph of text"
        assert chunks[0].source == "document.pdf"
        assert chunks[0].page_number == 1
        assert chunks[0].element_type == "NarrativeText"

        assert chunks[1].text.startswith("Table data:")
        assert chunks[1].source == "document.pdf"
        assert chunks[1].page_number == 2
        assert chunks[1].element_type == "Table"

    @patch("ingest.src.main.partition_pdf")
    @patch("ingest.src.main.QdrantVectorClient")
    def test_parse_pdf_handles_tables_specially(self, mock_vector_client, mock_partition):
        """Test that table elements are prefixed with 'Table data:'."""
        mock_table = Mock()
        mock_table.text = "Q1 Revenue: $1M"
        mock_table.category = "Table"
        mock_table.metadata.page_number = 3
        mock_table.metadata.text_as_html = "<table><tr><td>Q1 Revenue: $1M</td></tr></table>"

        mock_partition.return_value = [mock_table]

        processor = DocumentProcessor(watch_dir="/tmp/test")
        chunks = processor.parse_pdf(Path("/tmp/test.pdf"))

        assert len(chunks) == 1
        assert chunks[0].text.startswith("Table data:")
        assert "<table>" in chunks[0].text

    @patch("ingest.src.main.partition_pdf")
    @patch("ingest.src.main.QdrantVectorClient")
    def test_process_and_upload_calls_vector_client(self, mock_vector_client_class, mock_partition):
        """Test that processing uploads chunks to vector client."""
        mock_element = Mock()
        mock_element.text = "Sample content"
        mock_element.category = "NarrativeText"
        mock_element.metadata.page_number = 1
        mock_partition.return_value = [mock_element]

        mock_vector_instance = Mock()
        mock_vector_instance.upsert_chunks.return_value = 1
        mock_vector_client_class.return_value = mock_vector_instance

        processor = DocumentProcessor(watch_dir="/tmp/test")
        result = processor.process_and_upload(Path("/tmp/test/doc.pdf"))

        assert result == 1
        mock_vector_instance.upsert_chunks.assert_called_once()
        chunks_arg = mock_vector_instance.upsert_chunks.call_args[0][0]
        assert len(chunks_arg) == 1
        assert chunks_arg[0].text == "Sample content"


class TestIntegrationScenario:
    """End-to-end test scenarios with mocked dependencies."""

    @patch("ingest.src.main.partition_pdf")
    @patch("ingest.src.main.QdrantClient")
    @patch("ingest.src.main.SentenceTransformer")
    def test_full_pipeline_pdf_to_vectors(self, mock_st, mock_qc, mock_partition):
        """
        Test complete pipeline: PDF -> Chunks -> Dense+Sparse Vectors -> Qdrant.

        This validates that a sample PDF is correctly:
        1. Parsed into chunks with metadata
        2. Transformed into dense embeddings (via sentence-transformers)
        3. Transformed into sparse vectors (via term frequency)
        4. Upserted to the brain_os_docs collection
        """
        import numpy as np

        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_model.encode.return_value = np.array([[0.1] * 384, [0.2] * 384])
        mock_st.return_value = mock_model

        mock_client_instance = Mock()
        mock_client_instance.get_collection.return_value = Mock(points_count=0)
        mock_qc.return_value = mock_client_instance

        mock_text_element = Mock()
        mock_text_element.text = "This is a research paper about neural networks"
        mock_text_element.category = "NarrativeText"
        mock_text_element.metadata.page_number = 1

        mock_table_element = Mock()
        mock_table_element.text = "Accuracy: 95%"
        mock_table_element.category = "Table"
        mock_table_element.metadata.page_number = 3
        mock_table_element.metadata.text_as_html = "<table>Accuracy: 95%</table>"

        mock_partition.return_value = [mock_text_element, mock_table_element]

        processor = DocumentProcessor(watch_dir="/tmp/test")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            pdf_path = Path(tmp_file.name)

        try:
            chunks_uploaded = processor.process_and_upload(pdf_path)

            assert chunks_uploaded == 2

            mock_partition.assert_called_once_with(
                filename=str(pdf_path),
                strategy="hi_res",
                infer_table_structure=True,
            )

            mock_client_instance.upsert.assert_called_once()
            upsert_call = mock_client_instance.upsert.call_args
            assert upsert_call.kwargs["collection_name"] == "brain_os_docs"

            points = upsert_call.kwargs["points"]
            assert len(points) == 2

            point1 = points[0]
            assert point1.payload["text"] == "This is a research paper about neural networks"
            assert point1.payload["element_type"] == "NarrativeText"
            assert point1.payload["page_number"] == 1
            assert "dense" in point1.vector
            assert "sparse" in point1.vector
            assert len(point1.vector["dense"]) == 384

            point2 = points[1]
            assert "Table data:" in point2.payload["text"]
            assert point2.payload["element_type"] == "Table"
            assert point2.payload["page_number"] == 3
            assert "dense" in point2.vector
            assert "sparse" in point2.vector

            for point in points:
                assert isinstance(point.vector["sparse"], SparseVector)
                assert len(point.vector["sparse"].indices) > 0
                assert len(point.vector["sparse"].values) > 0

        finally:
            pdf_path.unlink(missing_ok=True)
