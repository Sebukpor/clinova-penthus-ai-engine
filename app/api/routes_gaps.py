"""
Clinova Penthus AI Engine - Gaps Route
POST /api/v1/gaps - Detect documentation gaps.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.config import get_settings
from app.core.security import AuthenticatedUser, require_gaps
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="Documentation Gap Detection",
    description="Identify missing information and quality issues in clinical documentation.",
)
async def gap_detection(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_gaps),
):
    """Detect documentation gaps and quality issues."""
    settings = get_settings()
    if not settings.features.gap_detection:
        return ClinicalResponse(
            request_id=request_id,
            tenant_id=request.tenant_id,
            encounter_id=request.encounter_id,
            document_id=request.document_id,
            workflow="gaps",
            model={"repo_id": "", "prompt_version": "", "model_version": ""},
            result={"missing_information": [], "quality_warnings": [], "suggestions": ["Gap detection is disabled."]},
            warnings=["Feature disabled"],
            latency_ms=0,
        )

    return await orchestrator.run(
        workflow="gaps",
        request=request,
        request_id=request_id,
    )
