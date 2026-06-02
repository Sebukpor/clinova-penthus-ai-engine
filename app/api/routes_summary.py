"""
Clinova Penthus AI Engine - Summary Route
POST /api/v1/summary - Generate clinical summaries.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.security import AuthenticatedUser, require_summary
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="Clinical Summary Generation",
    description="Generate concise clinical summaries with key findings and follow-up recommendations.",
)
async def summary_generation(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_summary),
):
    """Generate clinical summary from encounter data."""
    return await orchestrator.run(
        workflow="summary",
        request=request,
        request_id=request_id,
    )
