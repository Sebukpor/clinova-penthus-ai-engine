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
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                        "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                        "document_id": "123e4567-e89b-12d3-a456-426614174000",
                        "image": "data:image/jpeg;base64,/9j/4AAQ...(base64 encoded image)",
                        "language": "en",
                        "target_language": "fr",
                    }
                }
            }
        },
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "example": {
                            "request_id": "e5f6a1b2c3d4",
                            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                            "document_id": "123e4567-e89b-12d3-a456-426614174000",
                            "workflow": "translation",
                            "model": {
                                "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                                "prompt_version": "translation.v1",
                                "model_version": "penthus-1.2-alpha-4b",
                            },
                            "result": {
                                "translated_text": "Le patient s'est présenté pour un examen ophtalmologique de routine. Acuité visuelle : OD 6/12P, OG 6/12P. Pression intraoculaire : OD 21,0 mmHg, OG 23,0 mmHg. Presbytie confirmée (+2,50 add). Prescription : gouttes E19 combination BCS 00, 6 fois par jour, 1 mois.",
                                "source_language": "en",
                                "target_language": "fr",
                                "confidence": 0.93,
                            },
                            "warnings": [],
                            "latency_ms": 18900,
                            "ocr_reused": True,
                        }
                    }
                }
            }
        },
    },
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
