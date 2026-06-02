"""
Clinova Penthus AI Engine - Document Service
Document management with object storage integration.
"""

import hashlib
import uuid
from typing import Any, Dict, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class DocumentService:
    """Service for document management and storage."""

    def __init__(self, db_repository=None, object_storage=None):
        self.db = db_repository
        self.storage = object_storage

    async def create_document(
        self,
        tenant_id: str,
        encounter_id: str,
        content: bytes,
        mime_type: str = "application/octet-stream",
        language: str = "en",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a document record and store content.

        Args:
            tenant_id: Tenant identifier
            encounter_id: Encounter identifier
            content: Document bytes
            mime_type: MIME type
            language: Document language
            metadata: Additional metadata

        Returns:
            Document record dict
        """
        content_hash = hashlib.sha256(content).hexdigest()
        tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        encounter_uuid = uuid.UUID(encounter_id) if isinstance(encounter_id, str) else encounter_id

        # Check for existing document by hash
        if self.db:
            existing = await self.db.documents.get_by_content_hash(tenant_uuid, content_hash)
            if existing:
                logger.info("document_deduplicated", content_hash=content_hash[:16])
                return {
                    "id": str(existing.id),
                    "tenant_id": tenant_id,
                    "encounter_id": encounter_id,
                    "content_hash": content_hash,
                    "mime_type": existing.mime_type,
                    "language": existing.language,
                    "deduplicated": True,
                }

        # Store in object storage
        object_uri = None
        if self.storage:
            try:
                object_uri = await self.storage.upload(
                    key=f"{tenant_id}/{encounter_id}/{content_hash}",
                    data=content,
                    content_type=mime_type,
                )
            except Exception as e:
                logger.warning("object_storage_upload_failed", error=str(e))

        # Create database record
        doc_id = uuid.uuid4()
        if self.db:
            try:
                doc = await self.db.documents.create(
                    tenant_id=tenant_uuid,
                    encounter_id=encounter_uuid,
                    content_hash=content_hash,
                    object_uri=object_uri,
                    mime_type=mime_type,
                    language=language,
                    file_size_bytes=len(content),
                    metadata=metadata or {},
                )
                doc_id = doc.id
            except Exception as e:
                logger.error("document_db_create_failed", error=str(e))

        return {
            "id": str(doc_id),
            "tenant_id": tenant_id,
            "encounter_id": encounter_id,
            "content_hash": content_hash,
            "mime_type": mime_type,
            "language": language,
            "object_uri": object_uri,
            "deduplicated": False,
        }

    async def get_document(self, tenant_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        if not self.db:
            return None
        tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id
        doc = await self.db.documents.get_by_id(tenant_uuid, doc_uuid)
        if doc:
            return {
                "id": str(doc.id),
                "tenant_id": str(doc.tenant_id),
                "encounter_id": str(doc.encounter_id),
                "content_hash": doc.content_hash,
                "object_uri": doc.object_uri,
                "mime_type": doc.mime_type,
                "language": doc.language,
            }
        return None
