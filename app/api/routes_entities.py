"""
Clinova Penthus AI Engine - Entities Route
POST /api/v1/entities - Extract clinical entities from text.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.security import AuthenticatedUser, require_entities
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="Clinical Entity Extraction",
    description="Extract and classify clinical entities (symptoms, diagnoses, medications, etc.).",
)
async def entity_extraction(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_entities),
):
    """Extract clinical entities from text or document images."""
    return await orchestrator.run(
        workflow="entities",
        request=request,
        request_id=request_id,
    )
