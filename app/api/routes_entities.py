"""
Clinova Penthus AI Engine - Entities Route
POST /api/v1/entities - Extract clinical entities.
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
                            "request_id": "a1b2c3d4e5f6",
                            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                            "document_id": "123e4567-e89b-12d3-a456-426614174000",
                            "workflow": "entities",
                            "model": {
                                "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                                "prompt_version": "entities.v1",
                                "model_version": "penthus-1.2-alpha-4b",
                            },
                            "result": {
                                "entities": [
                                    {"type": "CONDITION", "text": "refractive error", "start": 0, "end": 16},
                                    {"type": "CONDITION", "text": "presbyopia", "start": 18, "end": 28},
                                    {"type": "MEDICATION", "text": "E19 combination BCS 00", "start": 30, "end": 52},
                                    {"type": "MEASUREMENT", "text": "IOP 21.0 mmHg", "start": 54, "end": 67},
                                    {"type": "DOCTOR", "text": "DR. SANA ZAFAR", "start": 70, "end": 84},
                                ]
                            },
                            "warnings": [],
                            "latency_ms": 12400,
                            "ocr_reused": True,
                        }
                    }
                }
            }
        },
    },
)
async def entity_extraction(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_entities),
):
    """
    Clinical entity extraction endpoint.

    Extract and classify clinical entities such as symptoms, diagnoses,
    medications, measurements, and provider names from clinical text or images.
    """
    return await orchestrator.run(
        workflow="entities",
        request=request,
        request_id=request_id,
    )
