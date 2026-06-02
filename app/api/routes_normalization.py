"""
Clinova Penthus AI Engine - Normalization Route
POST /api/v1/normalization - Normalize clinical terms.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.security import AuthenticatedUser, require_normalization
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="Clinical Term Normalization",
    description="Normalize clinical terms to canonical forms. Does NOT assign standardized codes.",
)
async def term_normalization(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_normalization),
):
    """
    Normalize clinical terms.

    Normalizes abbreviations and clinical terms but does NOT assign
    SNOMED CT, ICD-11, RxNorm, or LOINC codes.
    """
    return await orchestrator.run(
        workflow="normalization",
        request=request,
        request_id=request_id,
    )
