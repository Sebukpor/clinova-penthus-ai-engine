"""
Clinova Penthus AI Engine - Translation Route
POST /api/v1/translation - Translate clinical text.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.config import get_settings
from app.core.security import AuthenticatedUser, require_translation
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="Clinical Text Translation",
    description="Translate clinical text between languages while preserving medical accuracy.",
)
async def translation(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_translation),
):
    """Translate clinical text to target language."""
    settings = get_settings()
    if not settings.features.translation:
        return ClinicalResponse(
            request_id=request_id,
            tenant_id=request.tenant_id,
            encounter_id=request.encounter_id,
            document_id=request.document_id,
            workflow="translation",
            model={"repo_id": "", "prompt_version": "", "model_version": ""},
            result={"translated_text": "", "source_language": request.language, "target_language": request.target_language or "en", "confidence": 0.0},
            warnings=["Translation feature is disabled"],
            latency_ms=0,
        )

    return await orchestrator.run(
        workflow="translation",
        request=request,
        request_id=request_id,
    )
