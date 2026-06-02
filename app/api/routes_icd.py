"""
Clinova Penthus AI Engine - ICD-11 Route
POST /api/v1/icd - Map clinical terms to ICD-11 codes.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.config import get_settings
from app.core.security import AuthenticatedUser, require_icd
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="ICD-11 Coding",
    description="Normalize clinical terms and return ICD-11 candidates via terminology gateway.",
)
async def icd_coding(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_icd),
):
    """
    ICD-11 coding endpoint.

    1. Resolves OCR if image provided
    2. Extracts entities if needed
    3. Normalizes terms via AI model
    4. Calls terminology gateway for ICD-11 candidates
    5. Returns normalized terms + ICD-11 candidates

    The AI model normalizes terms but does NOT assign final ICD-11 codes.
    """
    settings = get_settings()
    if not settings.features.icd_endpoint:
        return ClinicalResponse(
            request_id=request_id,
            tenant_id=request.tenant_id,
            encounter_id=request.encounter_id,
            document_id=request.document_id,
            workflow="icd",
            model={"repo_id": "", "prompt_version": "", "model_version": ""},
            result={"normalized_terms": [], "candidates": [], "system": "ICD11"},
            warnings=["ICD-11 coding is disabled"],
            latency_ms=0,
        )

    return await orchestrator.run(
        workflow="icd",
        request=request,
        request_id=request_id,
    )
