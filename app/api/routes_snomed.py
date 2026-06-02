"""
Clinova Penthus AI Engine - SNOMED CT Route
POST /api/v1/snomed - Map clinical terms to SNOMED CT concepts.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.config import get_settings
from app.core.security import AuthenticatedUser, require_snomed
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="SNOMED CT Mapping",
    description="Normalize clinical terms and return SNOMED CT candidates via terminology gateway.",
)
async def snomed_mapping(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_snomed),
):
    """
    SNOMED CT mapping endpoint.

    1. Resolves OCR if image provided
    2. Extracts entities if needed
    3. Normalizes terms via AI model
    4. Calls terminology gateway for SNOMED CT candidates
    5. Returns normalized terms + candidates

    The AI model normalizes terms but does NOT assign final SNOMED CT codes.
    """
    settings = get_settings()
    if not settings.features.snomed_endpoint:
        return ClinicalResponse(
            request_id=request_id,
            tenant_id=request.tenant_id,
            encounter_id=request.encounter_id,
            document_id=request.document_id,
            workflow="snomed",
            model={"repo_id": "", "prompt_version": "", "model_version": ""},
            result={"normalized_terms": [], "candidates": [], "system": "SNOMED_CT"},
            warnings=["SNOMED CT mapping is disabled"],
            latency_ms=0,
        )

    return await orchestrator.run(
        workflow="snomed",
        request=request,
        request_id=request_id,
    )
