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
                            "request_id": "b3c4d5e6f7a2",
                            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                            "document_id": "123e4567-e89b-12d3-a456-426614174000",
                            "workflow": "icd",
                            "model": {
                                "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                                "prompt_version": "normalization.v1",
                                "model_version": "penthus-1.2-alpha-4b",
                            },
                            "result": {
                                "system": "ICD11",
                                "normalized_terms": [
                                    {"source_text": "refractive error", "normalized_text": "Refractive error of eye"},
                                    {"source_text": "presbyopia", "normalized_text": "Presbyopia"},
                                ],
                                "candidates": [
                                    {"term": "Refractive error of eye", "code": "9D00", "system": "ICD11", "score": 0.95},
                                    {"term": "Presbyopia", "code": "9D01.2", "system": "ICD11", "score": 0.98},
                                    {"term": "Elevated intraocular pressure", "code": "9C61", "system": "ICD11", "score": 0.88},
                                ],
                            },
                            "warnings": [],
                            "latency_ms": 15300,
                            "ocr_reused": True,
                        }
                    }
                }
            }
        },
    },
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
