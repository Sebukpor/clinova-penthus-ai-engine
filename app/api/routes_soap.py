"""
Clinova Penthus AI Engine - SOAP Route
POST /api/v1/soap - Generate SOAP notes from clinical text.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.security import AuthenticatedUser, require_soap
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="SOAP Note Generation",
    description="Generate structured SOAP notes from clinical encounter text or images.",
)
async def soap_generation(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_soap),
):
    """
    SOAP note generation endpoint.

    Resolves OCR if image is provided, then generates a structured SOAP note
    with subjective, objective, assessment, and plan sections.
    """
    return await orchestrator.run(
        workflow="soap",
        request=request,
        request_id=request_id,
    )
