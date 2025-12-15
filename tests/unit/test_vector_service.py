"""Unit tests for VectorService.

Tests cover:
- Embedding and storage operations
- Semantic search with filtering
- Deduplication logic
- Text hashing
- Error handling
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone

from src.services.vector_service import (
    VectorService,
    EmbeddingResult,
    SearchResult,
    LOG_EMBEDDINGS_COLLECTION,
    CONVERSATION_HISTORY_COLLECTION,
)


@pytest.fixture
def mock_qdrant_client():
    """Create a mock Qdrant client."""
    client = Mock()
    client.get_collections.return_value = Mock(collections=[])
    client.create_collection.return_value = None
    client.create_payload_index.return_value = None
    client.upsert.return_value = None
    client.scroll.return_value = ([], None)
    client.search.return_value = []
    client.delete.return_value = None
    return client


@pytest.fixture
def mock_embedding():
    """Create a mock embedding vector."""
    return [0.1] * 768  # 768-dim embedding


@pytest.fixture
def vector_service(mock_qdrant_client, mock_embedding):
    """Create a VectorService with mocked dependencies."""
    with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
        mock_qdrant.client = mock_qdrant_client
        with patch("src.services.vector_service.embedding_service") as mock_embed:
            mock_embed.get_embedding.return_value = mock_embedding
            with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                # Reset singleton
                VectorService._instance = None
                VectorService._log_collection_initialized = False
                service = VectorService()
                yield service


class TestVectorServiceInit:
    """Tests for VectorService initialization."""

    def test_singleton_pattern(self, mock_qdrant_client):
        """Test that VectorService is a singleton."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            VectorService._instance = None
            service1 = VectorService()
            service2 = VectorService()
            assert service1 is service2

    def test_enabled_property_when_enabled(self, mock_qdrant_client):
        """Test enabled property when vector search is enabled."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                VectorService._instance = None
                service = VectorService()
                assert service.enabled is True

    def test_enabled_property_when_disabled(self, mock_qdrant_client):
        """Test enabled property when vector search is disabled."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", False):
                VectorService._instance = None
                service = VectorService()
                assert service.enabled is False

    def test_enabled_property_when_no_client(self):
        """Test enabled property when Qdrant client is None."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = None
            with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                VectorService._instance = None
                service = VectorService()
                assert service.enabled is False


class TestTextHashing:
    """Tests for text hashing functionality."""

    def test_compute_text_hash_returns_hex(self, vector_service):
        """Test that compute_text_hash returns a hex string."""
        hash_value = vector_service.compute_text_hash("test text")
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA-256 hex length

    def test_compute_text_hash_deterministic(self, vector_service):
        """Test that same text produces same hash."""
        text = "Hello, World!"
        hash1 = vector_service.compute_text_hash(text)
        hash2 = vector_service.compute_text_hash(text)
        assert hash1 == hash2

    def test_compute_text_hash_different_texts(self, vector_service):
        """Test that different texts produce different hashes."""
        hash1 = vector_service.compute_text_hash("text1")
        hash2 = vector_service.compute_text_hash("text2")
        assert hash1 != hash2


class TestEnsureLogEmbeddingsCollection:
    """Tests for collection initialization."""

    def test_creates_collection_when_not_exists(self, mock_qdrant_client, mock_embedding):
        """Test collection creation when it doesn't exist."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_client.get_collections.return_value = Mock(collections=[])

            with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                VectorService._instance = None
                VectorService._log_collection_initialized = False
                service = VectorService()

                result = service.ensure_log_embeddings_collection()

                assert result is True
                mock_qdrant_client.create_collection.assert_called_once()

    def test_skips_creation_when_exists(self, mock_qdrant_client, mock_embedding):
        """Test collection is not recreated when it exists."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            existing_collection = Mock()
            existing_collection.name = LOG_EMBEDDINGS_COLLECTION
            mock_qdrant_client.get_collections.return_value = Mock(collections=[existing_collection])

            with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                VectorService._instance = None
                VectorService._log_collection_initialized = False
                service = VectorService()

                result = service.ensure_log_embeddings_collection()

                assert result is True
                mock_qdrant_client.create_collection.assert_not_called()

    def test_caches_initialization_result(self, vector_service, mock_qdrant_client):
        """Test that initialization is cached."""
        vector_service._log_collection_initialized = True

        result = vector_service.ensure_log_embeddings_collection()

        assert result is True
        mock_qdrant_client.get_collections.assert_not_called()


class TestEmbedAndStore:
    """Tests for embed_and_store functionality."""

    def test_returns_none_when_disabled(self, mock_qdrant_client):
        """Test returns None when vector search is disabled."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", False):
                VectorService._instance = None
                service = VectorService()

                result = service.embed_and_store(
                    text="test",
                    project_id="test-project",
                )

                assert result is None

    def test_returns_none_for_empty_text(self, vector_service):
        """Test returns None for empty text."""
        result = vector_service.embed_and_store(
            text="",
            project_id="test-project",
        )
        assert result is None

    def test_returns_none_for_whitespace_text(self, vector_service):
        """Test returns None for whitespace-only text."""
        result = vector_service.embed_and_store(
            text="   ",
            project_id="test-project",
        )
        assert result is None

    def test_successful_embedding(self, mock_qdrant_client, mock_embedding):
        """Test successful embedding and storage."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            with patch("src.services.vector_service.embedding_service") as mock_embed:
                mock_embed.get_embedding.return_value = mock_embedding
                with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                    VectorService._instance = None
                    VectorService._log_collection_initialized = True
                    service = VectorService()

                    result = service.embed_and_store(
                        text="Test log message",
                        project_id="test-project",
                        source_type="log",
                        metadata={"severity": "ERROR"},
                    )

                    assert result is not None
                    assert isinstance(result, EmbeddingResult)
                    assert result.embedding_dim == 768
                    assert result.collection == LOG_EMBEDDINGS_COLLECTION
                    mock_qdrant_client.upsert.assert_called_once()

    def test_deduplication_finds_existing(self, mock_qdrant_client, mock_embedding):
        """Test deduplication returns existing embedding."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client

            # Mock existing point
            existing_point = Mock()
            existing_point.id = "existing-id"
            existing_point.payload = {
                "text_hash": "abc123",
                "timestamp": {"iso": "2025-01-01T00:00:00Z"},
            }
            mock_qdrant_client.scroll.return_value = ([existing_point], None)

            with patch("src.services.vector_service.embedding_service") as mock_embed:
                mock_embed.get_embedding.return_value = mock_embedding
                with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                    VectorService._instance = None
                    VectorService._log_collection_initialized = True
                    service = VectorService()

                    result = service.embed_and_store(
                        text="Test log message",
                        project_id="test-project",
                        deduplicate=True,
                    )

                    assert result is not None
                    assert result.vector_id == "existing-id"
                    # Should not call upsert since duplicate found
                    mock_qdrant_client.upsert.assert_not_called()


class TestSemanticSearch:
    """Tests for semantic search functionality."""

    def test_returns_empty_when_disabled(self, mock_qdrant_client):
        """Test returns empty list when disabled."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", False):
                VectorService._instance = None
                service = VectorService()

                results = service.semantic_search(
                    query="test query",
                    project_id="test-project",
                )

                assert results == []

    def test_returns_empty_for_empty_query(self, vector_service):
        """Test returns empty for empty query."""
        results = vector_service.semantic_search(
            query="",
            project_id="test-project",
        )
        assert results == []

    def test_successful_search(self, mock_qdrant_client, mock_embedding):
        """Test successful semantic search."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client

            # Mock search results
            search_result = Mock()
            search_result.id = "result-1"
            search_result.score = 0.85
            search_result.payload = {
                "content_preview": "Test log content",
                "timestamp": {"iso": "2025-01-01T00:00:00Z"},
                "severity": "ERROR",
            }
            mock_qdrant_client.search.return_value = [search_result]

            with patch("src.services.vector_service.embedding_service") as mock_embed:
                mock_embed.get_embedding.return_value = mock_embedding
                with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                    VectorService._instance = None
                    service = VectorService()

                    results = service.semantic_search(
                        query="error logs",
                        project_id="test-project",
                        top_k=10,
                    )

                    assert len(results) == 1
                    assert results[0].id == "result-1"
                    assert results[0].score == 0.85
                    assert results[0].content == "Test log content"

    def test_search_with_filters(self, mock_qdrant_client, mock_embedding):
        """Test search with severity and service filters."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_client.search.return_value = []

            with patch("src.services.vector_service.embedding_service") as mock_embed:
                mock_embed.get_embedding.return_value = mock_embedding
                with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                    VectorService._instance = None
                    service = VectorService()

                    service.semantic_search(
                        query="test",
                        project_id="test-project",
                        filters={
                            "severity": "ERROR",
                            "service": "my-service",
                            "year": 2025,
                            "month": 1,
                        },
                    )

                    # Verify search was called with filters
                    mock_qdrant_client.search.assert_called_once()
                    call_args = mock_qdrant_client.search.call_args
                    assert call_args.kwargs["query_filter"] is not None


class TestSemanticSearchLogs:
    """Tests for semantic_search_logs convenience method."""

    def test_calls_semantic_search(self, mock_qdrant_client, mock_embedding):
        """Test that semantic_search_logs calls semantic_search."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            mock_qdrant_client.search.return_value = []

            with patch("src.services.vector_service.embedding_service") as mock_embed:
                mock_embed.get_embedding.return_value = mock_embedding
                with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                    VectorService._instance = None
                    service = VectorService()

                    results = service.semantic_search_logs(
                        query="error",
                        project_id="test-project",
                        severity="ERROR",
                        service="api-service",
                    )

                    assert results == []
                    mock_qdrant_client.search.assert_called_once()


class TestGetSimilarLogs:
    """Tests for get_similar_logs functionality."""

    def test_excludes_self_by_default(self, mock_qdrant_client, mock_embedding):
        """Test that similar logs excludes the source log."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client

            # Mock search results including the source text
            source_text = "Error in service"
            source_hash = VectorService().compute_text_hash(source_text)

            result1 = Mock()
            result1.id = "self"
            result1.score = 1.0
            result1.payload = {
                "content_preview": source_text,
                "text_hash": source_hash,
                "timestamp": {},
            }

            result2 = Mock()
            result2.id = "similar"
            result2.score = 0.9
            result2.payload = {
                "content_preview": "Similar error",
                "text_hash": "different-hash",
                "timestamp": {},
            }

            mock_qdrant_client.search.return_value = [result1, result2]

            with patch("src.services.vector_service.embedding_service") as mock_embed:
                mock_embed.get_embedding.return_value = mock_embedding
                with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                    VectorService._instance = None
                    service = VectorService()

                    results = service.get_similar_logs(
                        log_text=source_text,
                        project_id="test-project",
                        top_k=5,
                        exclude_self=True,
                    )

                    # Should exclude the source text
                    assert len(results) == 1
                    assert results[0].id == "similar"


class TestDeleteByProject:
    """Tests for delete_by_project functionality."""

    def test_deletes_project_embeddings(self, mock_qdrant_client, mock_embedding):
        """Test deletion of all project embeddings."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = mock_qdrant_client
            with patch("src.services.vector_service.ENABLE_VECTOR_SEARCH", True):
                VectorService._instance = None
                service = VectorService()

                result = service.delete_by_project(
                    project_id="test-project",
                    collection=LOG_EMBEDDINGS_COLLECTION,
                )

                mock_qdrant_client.delete.assert_called_once()
                assert result == -1  # Qdrant doesn't return count

    def test_returns_zero_when_no_client(self):
        """Test returns 0 when Qdrant client is None."""
        with patch("src.services.vector_service.qdrant_service") as mock_qdrant:
            mock_qdrant.client = None
            VectorService._instance = None
            service = VectorService()

            result = service.delete_by_project(project_id="test-project")

            assert result == 0


class TestEmbeddingResult:
    """Tests for EmbeddingResult dataclass."""

    def test_embedding_result_creation(self):
        """Test EmbeddingResult can be created with required fields."""
        result = EmbeddingResult(
            vector_id="test-id",
            text_hash="abc123",
            embedding_dim=768,
            created_at="2025-01-01T00:00:00Z",
            collection="test_collection",
        )

        assert result.vector_id == "test-id"
        assert result.text_hash == "abc123"
        assert result.embedding_dim == 768
        assert result.metadata == {}


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_search_result_creation(self):
        """Test SearchResult can be created with required fields."""
        result = SearchResult(
            id="result-1",
            score=0.95,
            content="Test content",
            metadata={"key": "value"},
        )

        assert result.id == "result-1"
        assert result.score == 0.95
        assert result.content == "Test content"
        assert result.timestamp is None
