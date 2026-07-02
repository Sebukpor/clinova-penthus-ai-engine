"""
Tests for OCR Dependency Resolver
Verifies OCR deduplication, caching, and single-execution guarantee.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.orchestrator.ocr_dependency import OCRDependencyResolver


@pytest.fixture
def mock_vllm():
    client = AsyncMock()
    client.chat_completion.return_value.content = '''{
        "document_id": "doc_001",
        "raw_text": "Patient has fever for 3 days.",
        "entities": [{"text": "fever", "type": "symptom"}],
        "layout": {"pages": 1, "blocks": []},
        "language": "en"
    }'''
    client.chat_completion.return_value.model = "penthus-1.2-alpha-4b"
    return client


@pytest.fixture
def mock_prompts():
    pm = MagicMock()
    pm.render_prompt.return_value = {
        "system": "You are an OCR model",
        "user": "Extract text from this document",
        "temperature": 0.1,
        "max_tokens": 4000,
        "schema_ref": "OCRResult",
        "prompt_version": "ocr.v1",
    }
    return pm


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.ocr_results.get_by_document = AsyncMock(return_value=None)
    db.ocr_results.create = AsyncMock()
    return db


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get.return_value = None
    return cache


@pytest.fixture
def resolver(mock_vllm, mock_prompts, mock_db, mock_cache):
    return OCRDependencyResolver(
        vllm_client=mock_vllm,
        prompt_manager=mock_prompts,
        db_repository=mock_db,
        cache_client=mock_cache,
    )


class TestOCRDependency:
    """Test OCR dependency resolution."""

    @pytest.mark.asyncio
    async def test_ocr_executed_when_missing(self, resolver, mock_db, mock_cache, mock_vllm):
        """OCR is executed when no cached or stored result exists."""
        mock_db.ocr_results.get_by_document.return_value = None
        mock_cache.get.return_value = None

        result, reused = await resolver.resolve(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            document_id="doc_001",
            content_hash="abc123",
            text="Patient has fever for 3 days.",
        )

        assert not reused
        assert result["raw_text"] == "Patient has fever for 3 days."
        mock_vllm.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_ocr_reused_from_db(self, resolver, mock_db, mock_vllm):
        """OCR result is reused from PostgreSQL when available."""
        db_result = MagicMock()
        db_result.document_id = uuid.UUID("12345678-1234-1234-1234-123456789abc")
        db_result.raw_text = "Cached OCR text"
        db_result.entities = []
        db_result.layout = {}
        db_result.language = "en"

        mock_db.ocr_results.get_by_document.return_value = db_result

        result, reused = await resolver.resolve(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            document_id="doc_001",
            content_hash="abc123",
            text="Some text",
        )

        assert reused
        assert result["raw_text"] == "Cached OCR text"
        mock_vllm.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_ocr_reused_from_cache(self, resolver, mock_db, mock_cache, mock_vllm):
        """OCR result is reused from Redis cache when DB miss but cache hit."""
        mock_db.ocr_results.get_by_document.return_value = None
        mock_cache.get.return_value = {
            "document_id": "doc_001",
            "raw_text": "Redis cached text",
            "entities": [],
            "layout": {},
            "language": "en",
        }

        result, reused = await resolver.resolve(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            document_id="doc_001",
            content_hash="abc123",
            text="Some text",
        )

        assert reused
        assert result["raw_text"] == "Redis cached text"
        mock_vllm.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_ocr_force_rerun(self, resolver, mock_db, mock_vllm):
        """OCR is re-executed when force_rerun is True even if cached."""
        db_result = MagicMock()
        db_result.document_id = uuid.UUID("12345678-1234-1234-1234-123456789abc")
        db_result.raw_text = "Cached text"
        db_result.entities = []

        mock_db.ocr_results.get_by_document.return_value = db_result

        result, reused = await resolver.resolve(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            document_id="doc_001",
            content_hash="abc123",
            text="Some text",
            force_rerun=True,
        )

        assert not reused
        mock_vllm.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_ocr_not_executed_twice_same_hash(self, resolver, mock_vllm):
        """OCR is not executed twice for the same content hash."""
        # First call - no cache
        _, reused1 = await resolver.resolve(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            document_id="doc_001",
            content_hash="same_hash",
            text="Same text",
        )

        assert not reused1
        assert mock_vllm.chat_completion.call_count == 1

        # Second call - should use cache
        _, reused2 = await resolver.resolve(
            tenant_id="tenant_001",
            encounter_id="enc_002",
            document_id="doc_002",
            content_hash="same_hash",
            text="Same text",
        )

        assert reused2
        # vLLM should still be called once from first invocation
        assert mock_vllm.chat_completion.call_count == 1

    def test_cache_key_format(self, resolver):
        """Cache key follows correct format."""
        key = resolver._cache_key("tenant_001", "abc123")
        assert key == "ocr:tenant_001:abc123"

    def test_content_hash_computation(self, resolver):
        """Content hash is computed correctly."""
        data = b"test content"
        hash1 = resolver.compute_content_hash(data)
        hash2 = resolver.compute_content_hash(data)
        assert len(hash1) == 64  # SHA-256 hex
        assert hash1 == hash2  # Deterministic

    @pytest.mark.asyncio
    async def test_ocr_no_image_or_text_raises(self, resolver):
        """OCR raises error when neither image nor text is provided."""
        with pytest.raises(Exception):
            await resolver.resolve(
                tenant_id="tenant_001",
                encounter_id="enc_001",
                document_id="doc_001",
                content_hash="abc123",
            )
