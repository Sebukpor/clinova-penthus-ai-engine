"""
Clinova Penthus AI Engine - Context Route
GET /api/v1/encounters/{encounter_id}/context - Retrieve clinical context.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_cache_client, get_db_session
from app.context.store import ClinicalContextStore
from app.core.logging import get_logger
from app.core.security import AuthenticatedUser, require_context_read, require_tenant_access
from app.db.session import AsyncSession

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/encounters/{encounter_id}/context",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get Clinical Context",
    description="Retrieve the accumulated clinical context for an encounter.",
)
async def get_context(
    encounter_id: str,
    tenant_id: str,
    document_id: str = "",
    http_request: Request = None,
    cache = Depends(get_cache_client),
    session: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_context_read),
):
    """
    Retrieve clinical context for an encounter.

    Returns the accumulated state including OCR results, SOAP notes,
    entities, normalized terms, and other workflow outputs.
    """
    # Tenant isolation check
    if not user.can_access_tenant(tenant_id):
        raise HTTPException(status_code=403, detail="Tenant access denied")

    from app.db.repositories import ClinicalContextRepository
    repos = {"clinical_contexts": ClinicalContextRepository(session)}
    store = ClinicalContextStore(db_repository=repos["clinical_contexts"], cache_client=cache)

    ctx = await store.get(
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        document_id=document_id or None,
    )

    return {
        "tenant_id": tenant_id,
        "encounter_id": encounter_id,
        "document_id": document_id or None,
        "context": ctx,
    }


@router.get(
    "/documents/{document_id}/ocr",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get Document OCR Result",
    description="Retrieve the OCR result for a specific document.",
)
async def get_document_ocr(
    document_id: str,
    tenant_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_context_read),
):
    """Get OCR result for a document."""
    if not user.can_access_tenant(tenant_id):
        raise HTTPException(status_code=403, detail="Tenant access denied")

    import uuid
    from app.db.repositories import OCRResultRepository

    repo = OCRResultRepository(session)
    tenant_uuid = uuid.UUID(tenant_id)
    doc_uuid = uuid.UUID(document_id)

    result = await repo.get_by_document(tenant_uuid, doc_uuid)
    if not result:
        raise HTTPException(status_code=404, detail="OCR result not found")

    return {
        "document_id": document_id,
        "tenant_id": tenant_id,
        "raw_text": result.raw_text,
        "entities": result.entities,
        "language": result.language,
        "confidence": float(result.confidence) if result.confidence else None,
        "model_version": result.model_version,
        "prompt_version": result.prompt_version,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }
