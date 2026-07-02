"""
Clinova Penthus AI Engine - OCR Route
POST /api/v1/ocr - Extract text and entities from clinical documents.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.security import AuthenticatedUser, require_ocr
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="OCR Document Extraction",
    description="Extract text, entities, and layout from clinical document images.",
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
                            "request_id": "d4c1a71b2b265a88f93ab26720101d5f",
                            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                            "document_id": "123e4567-e89b-12d3-a456-426614174000",
                            "workflow": "ocr",
                            "model": {
                                "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                                "prompt_version": "ocr.v1",
                                "model_version": "penthus-1.2-alpha-4b",
                            },
                            "result": {
                                "raw_text": "\n--- PATIENT DEMOGRAPHICS ---\nAppointment Date: 26/06/2026\nDept: Ophthalmology\n\n--- CLINICAL NOTES ---\nExamination Findings: AR +0.75/-1.50 x 180, +0.00/-0.50 x 7. VA 6/12P, 6/12P. IOP 21.0 mmHg, 23.0.\n\n--- PRESCRIPTION ---\n - drug_dose: E19 combination BCS 00 | route: TEAR | frequency: 6TID | duration: 1 month\n\n--- DOCTOR DETAILS ---\nSignature Present: True\nName Stamp: DR. SANA ZAFAR, ASSISTANT PROFESSOR, DEPT OF OPHTHALMOLOGY",
                                "entities": [
                                    {
                                        "type": "DOCTOR_NAME",
                                        "text": "DR. SANA ZAFAR, ASSISTANT PROFESSOR, DEPT OF OPHTHALMOLOGY",
                                    }
                                ],
                                "layout": {"pages": 1, "blocks": []},
                                "language": "en",
                            },
                            "warnings": [],
                            "latency_ms": 34200,
                            "ocr_reused": False,
                        }
                    }
                }
            }
        },
    },
)
async def ocr_extraction(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_ocr),
):
    """
    OCR extraction endpoint.

    Extracts all text and clinical entities from a document image.
    Results are cached and reused for subsequent workflow calls.
    """
    return await orchestrator.run(
        workflow="ocr",
        request=request,
        request_id=request_id,
    )
