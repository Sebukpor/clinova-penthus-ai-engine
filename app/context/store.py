"""
Clinova Penthus AI Engine - Clinical Context Store
Durable context storage using PostgreSQL with Redis caching.
"""

import uuid
from typing import Any, Dict, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class ClinicalContextStore:
    """
    Stores and retrieves clinical context for encounters.

    Context is the shared state that accumulates across workflow calls
    for the same encounter/document pair.
    """

    def __init__(self, db_repository=None, cache_client=None):
        self.db = db_repository
        self.cache = cache_client

    async def get(
        self,
        tenant_id: str,
        encounter_id: str,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get clinical context for an encounter.

        Args:
            tenant_id: Tenant identifier
            encounter_id: Encounter identifier
            document_id: Optional document identifier

        Returns:
            Context dict (empty if not found)
        """
        # Try Redis cache first
        cache_key = self._cache_key(tenant_id, encounter_id, document_id)
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.debug("context_cache_hit", encounter_id=encounter_id)
                return cached

        # Try database
        if self.db:
            try:
                try:
                    tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
                except Exception:
                    tenant_uuid = tenant_id

                try:
                    encounter_uuid = uuid.UUID(encounter_id) if isinstance(encounter_id, str) else encounter_id
                except Exception:
                    encounter_uuid = encounter_id

                try:
                    doc_uuid = uuid.UUID(document_id) if document_id else None
                except Exception:
                    doc_uuid = document_id if document_id else None

                # Support being passed either a repo container (with .clinical_contexts)
                # or a repo object directly (tests pass the repo directly).
                if hasattr(self.db, "get_by_encounter"):
                    repo = self.db
                elif hasattr(self.db, "clinical_contexts") and hasattr(self.db.clinical_contexts, "get_by_encounter"):
                    repo = self.db.clinical_contexts
                else:
                    repo = self.db

                ctx = await repo.get_by_encounter(tenant_uuid, encounter_uuid, doc_uuid)
                if ctx:
                    result = ctx.state
                    # Cache in Redis
                    if self.cache:
                        await self.cache.set(cache_key, result, ttl=86400)
                    return result
            except Exception as e:
                logger.error("context_db_get_failed", error=str(e))

        return {}

    async def update(
        self,
        tenant_id: str,
        encounter_id: str,
        workflow: str,
        result: Dict[str, Any],
        document_id: Optional[str] = None,
    ) -> None:
        """
        Update clinical context with workflow results.

        Args:
            tenant_id: Tenant identifier
            encounter_id: Encounter identifier
            workflow: Workflow type that produced the result
            result: Workflow result data
            document_id: Optional document identifier
        """
        # Load existing context
        ctx = await self.get(tenant_id, encounter_id, document_id)

        # Merge workflow result into context
        ctx = self._merge_result(ctx, workflow, result)

        # Persist to database
        if self.db:
            try:
                try:
                    tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
                except Exception:
                    tenant_uuid = tenant_id

                try:
                    encounter_uuid = uuid.UUID(encounter_id) if isinstance(encounter_id, str) else encounter_id
                except Exception:
                    encounter_uuid = encounter_id

                try:
                    doc_uuid = uuid.UUID(document_id) if document_id else None
                except Exception:
                    doc_uuid = document_id if document_id else None

                if hasattr(self.db, "create_or_update"):
                    repo = self.db
                elif hasattr(self.db, "clinical_contexts") and hasattr(self.db.clinical_contexts, "create_or_update"):
                    repo = self.db.clinical_contexts
                else:
                    repo = self.db

                await repo.create_or_update(
                    tenant_id=tenant_uuid,
                    encounter_id=encounter_uuid,
                    state=ctx,
                    document_id=doc_uuid,
                )
            except Exception as e:
                logger.error("context_db_update_failed", error=str(e))

        # Update cache
        cache_key = self._cache_key(tenant_id, encounter_id, document_id)
        if self.cache:
            try:
                await self.cache.set(cache_key, ctx, ttl=86400)
            except Exception as e:
                logger.warning("context_cache_update_failed", error=str(e))

    def _merge_result(self, ctx: Dict[str, Any], workflow: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Merge workflow result into context."""
        ctx = dict(ctx)  # Copy

        # Update context fields based on workflow
        field_map = {
            "ocr": "ocr",
            "soap": "soap",
            "entities": "entities",
            "normalization": "normalized_terms",
            "summary": "summary",
            "gaps": "gaps",
            "translation": "translation",
            "snomed": "snomed_candidates",
            "icd": "icd_candidates",
            "fhir": "fhir_resources",
        }

        field = field_map.get(workflow)
        if field:
            ctx[field] = result

        # Track workflow state
        if "workflow_state" not in ctx:
            ctx["workflow_state"] = {}
        ctx["workflow_state"][workflow] = {
            "completed": True,
            "timestamp": "__timestamp__",  # Will be set by caller
        }

        return ctx

    def _cache_key(self, tenant_id: str, encounter_id: str, document_id: Optional[str] = None) -> str:
        """Generate cache key for context."""
        if document_id:
            return f"context:{tenant_id}:{encounter_id}:{document_id}"
        return f"context:{tenant_id}:{encounter_id}"
