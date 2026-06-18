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
                    }
                }
            }
        },
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "example": {
                            "request_id": "b2c3d4e5f6a1",
                            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                            "document_id": "123e4567-e89b-12d3-a456-426614174000",
                            "workflow": "normalization",
                            "model": {
                                "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                                "prompt_version": "normalization.v1",
                                "model_version": "penthus-1.2-alpha-4b",
                            },
                            "result": {
                                "normalized_terms": [
                                    {"source_text": "IOP", "normalized_text": "Intraocular Pressure", "category": "measurement"},
                                    {"source_text": "VA", "normalized_text": "Visual Acuity", "category": "measurement"},
                                    {"source_text": "AR", "normalized_text": "Auto-Refraction", "category": "procedure"},
                                    {"source_text": "6TID", "normalized_text": "6 times daily", "category": "frequency"},
                                    {"source_text": "TEAR", "normalized_text": "Topical eye administration", "category": "route"},
                                ]
                            },
                            "warnings": [],
                            "latency_ms": 9800,
                            "ocr_reused": True,
                        }
                    }
                }
            }
        },
    },
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
