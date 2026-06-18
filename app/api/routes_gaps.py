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
                            "request_id": "d4e5f6a1b2c3",
                            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                            "document_id": "123e4567-e89b-12d3-a456-426614174000",
                            "workflow": "gaps",
                            "model": {
                                "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                                "prompt_version": "gaps.v1",
                                "model_version": "penthus-1.2-alpha-4b",
                            },
                            "result": {
                                "gaps": [
                                    {"category": "demographics", "description": "Patient name not documented", "priority": "high"},
                                    {"category": "demographics", "description": "Patient age/sex not recorded", "priority": "high"},
                                    {"category": "history", "description": "Chief complaint / presenting complaint missing", "priority": "medium"},
                                    {"category": "history", "description": "Allergy status not documented", "priority": "medium"},
                                    {"category": "vitals", "description": "Blood pressure not recorded", "priority": "low"},
                                ],
                                "completeness_score": 0.62,
                                "recommendations": [
                                    "Add patient demographics before filing",
                                    "Document chief complaint",
                                    "Record allergy status",
                                ],
                            },
                            "warnings": [],
                            "latency_ms": 11200,
                            "ocr_reused": True,
                        }
                    }
                }
            }
        },
    },
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
