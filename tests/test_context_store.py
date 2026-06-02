"""
Tests for Clinical Context Store
Verifies context persistence, merging, and retrieval.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.context.store import ClinicalContextStore


class TestClinicalContextStore:
    """Test clinical context store operations."""

    @pytest.fixture
    def store(self):
        db = MagicMock()
        db.clinical_contexts = AsyncMock()
        db.clinical_contexts.get_by_encounter = AsyncMock(return_value=None)
        db.clinical_contexts.create_or_update = AsyncMock()

        cache = AsyncMock()
        cache.get.return_value = None

        return ClinicalContextStore(db_repository=db.clinical_contexts, cache_client=cache), db, cache

    @pytest.mark.asyncio
    async def test_get_returns_empty_when_no_context(self, store):
        """Get returns empty dict when no context exists."""
        context_store, db, cache = store
        db.clinical_contexts.get_by_encounter.return_value = None

        ctx = await context_store.get("tenant_001", "enc_001")
        assert ctx == {}

    @pytest.mark.asyncio
    async def test_get_returns_context_from_db(self, store):
        """Get returns context from database when found."""
        context_store, db, cache = store

        mock_ctx = MagicMock()
        mock_ctx.state = {
            "raw_text": "Patient has fever.",
            "ocr": {"document_id": "doc_001"},
            "soap": {"subjective": "Fever for 3 days"},
        }

        db.clinical_contexts.get_by_encounter.return_value = mock_ctx

        ctx = await context_store.get("tenant_001", "enc_001")
        assert ctx["raw_text"] == "Patient has fever."
        assert ctx["soap"]["subjective"] == "Fever for 3 days"

    @pytest.mark.asyncio
    async def test_update_merges_workflow_result(self, store):
        """Update merges workflow result into existing context."""
        context_store, db, cache = store

        existing_state = {"raw_text": "Patient has fever.", "version": 1}
        db.clinical_contexts.get_by_encounter.return_value = MagicMock(state=existing_state)

        await context_store.update(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            workflow="soap",
            result={"subjective": "Fever", "objective": "Temp 38.5C"},
        )

        # Should call create_or_update with merged state
        db.clinical_contexts.create_or_update.assert_called_once()
        call_args = db.clinical_contexts.create_or_update.call_args
        state = call_args.kwargs.get("state") or call_args[1].get("state")
        assert state is not None

    @pytest.mark.asyncio
    async def test_update_creates_new_context(self, store):
        """Update creates new context when none exists."""
        context_store, db, cache = store
        db.clinical_contexts.get_by_encounter.return_value = None

        await context_store.update(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            workflow="ocr",
            result={"raw_text": "Test text", "confidence": 0.95},
        )

        db.clinical_contexts.create_or_update.assert_called_once()

    def test_merge_result_adds_workflow_data(self):
        """_merge_result correctly adds workflow-specific data."""
        store = ClinicalContextStore()

        ctx = {}
        result = {"subjective": "Patient reports fever"}
        merged = store._merge_result(ctx, "soap", result)

        assert merged["soap"] == result
        assert "workflow_state" in merged
        assert merged["workflow_state"]["soap"]["completed"] is True

    def test_merge_result_preserves_existing_data(self):
        """_merge_result preserves existing context data."""
        store = ClinicalContextStore()

        ctx = {"raw_text": "Existing text", "ocr": {"document_id": "doc_001"}}
        result = {"subjective": "New SOAP"}
        merged = store._merge_result(ctx, "soap", result)

        assert merged["raw_text"] == "Existing text"
        assert merged["ocr"]["document_id"] == "doc_001"
        assert merged["soap"] == result

    def test_cache_key_with_document(self):
        """Cache key includes document ID when provided."""
        store = ClinicalContextStore()
        key = store._cache_key("tenant_001", "enc_001", "doc_001")
        assert key == "context:tenant_001:enc_001:doc_001"

    def test_cache_key_without_document(self):
        """Cache key excludes document ID when not provided."""
        store = ClinicalContextStore()
        key = store._cache_key("tenant_001", "enc_001")
        assert key == "context:tenant_001:enc_001"

    @pytest.mark.asyncio
    async def test_cache_is_used(self, store):
        """Cache is checked before database."""
        context_store, db, cache = store
        cache.get.return_value = {"raw_text": "Cached context", "soap": {}}

        ctx = await context_store.get("tenant_001", "enc_001")

        assert ctx["raw_text"] == "Cached context"
        # Should not hit database when cache has data
        db.clinical_contexts.get_by_encounter.assert_not_called()
