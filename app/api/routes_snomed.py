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
    description=(
        "Two-step workflow: (1) AI model normalizes clinical terms and abbreviations, "
        "(2) Normalized terms are sent to the SNOMED CT terminology gateway to retrieve concept candidates. "
        "The AI does NOT assign codes — codes come from the external SNOMED CT service."
    ),
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
                            "request_id": "a2b3c4d5e6f7",
                            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                            "document_id": "123e4567-e89b-12d3-a456-426614174000",
                            "workflow": "snomed",
                            "model": {
                                "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                                "prompt_version": "normalization.v1",
                                "model_version": "penthus-1.2-alpha-4b",
                            },
                            "result": {
                                "system": "SNOMED_CT",
                                "query_terms": [
                                    "Refractive error",
                                    "Presbyopia",
                                    "Elevated intraocular pressure",
                                ],
                                "normalized_terms": [
                                    {"source_text": "refractive error", "normalized_text": "Refractive error"},
                                    {"source_text": "presbyopia", "normalized_text": "Presbyopia"},
                                    {"source_text": "raised IOP", "normalized_text": "Elevated intraocular pressure"},
                                ],
                                "candidates": [
                                    {"term": "Refractive error", "code": "39021009", "system": "SNOMED_CT", "score": 0.97},
                                    {"term": "Presbyopia", "code": "41256004", "system": "SNOMED_CT", "score": 0.99},
                                    {"term": "Elevated intraocular pressure", "code": "24075007", "system": "SNOMED_CT", "score": 0.91},
                                ],
                                "ai_normalized": True,
                                "terminology_service_available": True,
                                "warning": None,
                            },
                            "warnings": [],
                            "latency_ms": 16800,
                            "ocr_reused": True,
                        }
                    }
                }
            }
        },
    },
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

    Step 1 — AI normalization: The model normalizes clinical abbreviations and
    terms into canonical forms (e.g. 'IOP' → 'Intraocular Pressure').

    Step 2 — Terminology gateway: Normalized terms are sent to the SNOMED CT
    external service which returns concept candidates with codes and confidence scores.

    Note: If the terminology gateway is unavailable, normalized terms are returned
    without codes and a warning is included in the response.
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
            result={"normalized_terms": [], "candidates": [], "system": "SNOMED_CT",
                    "query_terms": [], "ai_normalized": False,
                    "terminology_service_available": False, "warning": None},
            warnings=["SNOMED CT mapping is disabled"],
            latency_ms=0,
        )

    return await orchestrator.run(
        workflow="snomed",
        request=request,
        request_id=request_id,
    )