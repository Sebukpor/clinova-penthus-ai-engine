"""
Clinova Penthus AI Engine - SOAP Route
POST /api/v1/soap - Generate SOAP notes from clinical text.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.security import AuthenticatedUser, require_soap
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="SOAP Note Generation",
    description="Generate structured SOAP notes from clinical encounter text or images.",
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
                            "request_id": "987780eb6db2d4c41586ca1cd49bb9d4",
                            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                            "document_id": "123e4567-e89b-12d3-a456-426614174000",
                            "workflow": "soap",
                            "model": {
                                "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                                "prompt_version": "soap.v1",
                                "model_version": "penthus-1.2-alpha-4b",
                            },
                            "result": {
                                "data": {
                                    "subjective": "Patient presented for routine ophthalmological examination. History of present illness: None reported. Allergies: None known.",
                                    "objective": "Visual Acuity: RE 6/12P, LE 6/12P. Refraction: RE AR +0.75/-1.50 x 180, LE +0.00/-0.50 x 7. Intraocular Pressure: RE 21.0 mmHg, LE 23.0 mmHg. Add: +2.50 sph.",
                                    "assessment": "Mild refractive error with reduced visual acuity (6/12P). IOP within normal limits (upper range). Presbyopia (+2.50 add). No evidence of glaucoma or retinopathy.",
                                    "plan": "Medication: E19 combination BCS 00, Route: TEAR, Frequency: 6TID, Duration: 1 month. Follow-up: 1 month.",
                                }
                            },
                            "warnings": [],
                            "latency_ms": 55321,
                            "ocr_reused": True,
                        }
                    }
                }
            }
        },
    },
)
async def soap_generation(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_soap),
):
    """
    SOAP note generation endpoint.

    Resolves OCR if image is provided, then generates a structured SOAP note
    with subjective, objective, assessment, and plan sections.
    """
    return await orchestrator.run(
        workflow="soap",
        request=request,
        request_id=request_id,
    )
