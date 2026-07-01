"""
Clinova Penthus AI Engine - FHIR Route
POST /api/v1/fhir - Generate FHIR resources from clinical data.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.config import get_settings
from app.core.security import AuthenticatedUser, require_fhir
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="FHIR Resource Generation",
    description="Generate FHIR R4 resources from clinical encounter data.",
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
                            "request_id": "f6a1b2c3d4e5",
                            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                            "document_id": "123e4567-e89b-12d3-a456-426614174000",
                            "workflow": "fhir",
                            "model": {
                                "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                                "prompt_version": "fhir.v1",
                                "model_version": "penthus-1.2-alpha-4b",
                            },
                            "result": {
                                "resources": [
                                    {
                                        "resourceType": "Encounter",
                                        "status": "finished",
                                        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB", "display": "ambulatory"},
                                        "serviceType": {"text": "Ophthalmology"},
                                        "period": {"start": "2026-06-26"},
                                    },
                                    {
                                        "resourceType": "Condition",
                                        "clinicalStatus": {"coding": [{"code": "active"}]},
                                        "code": {"text": "Refractive error"},
                                        "subject": {"reference": "Patient/unknown"},
                                    },
                                    {
                                        "resourceType": "MedicationRequest",
                                        "status": "active",
                                        "medicationCodeableConcept": {"text": "E19 combination BCS 00"},
                                        "dosageInstruction": [{"text": "6 times daily via eye drops for 1 month"}],
                                    },
                                    {
                                        "resourceType": "Observation",
                                        "status": "final",
                                        "code": {"text": "Intraocular Pressure"},
                                        "valueString": "RE 21.0 mmHg, LE 23.0 mmHg",
                                    },
                                ]
                            },
                            "warnings": [],
                            "latency_ms": 22100,
                            "ocr_reused": True,
                        }
                    }
                }
            }
        },
    },
)
async def fhir_generation(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_fhir),
):
    """
    Generate FHIR R4 resources.

    Produces FHIR resources including Patient, Encounter, Condition,
    Observation, MedicationRequest, and Composition from clinical data.
    """
    settings = get_settings()
    if not settings.features.fhir_endpoint:
        return ClinicalResponse(
            request_id=request_id,
            tenant_id=request.tenant_id,
            encounter_id=request.encounter_id,
            document_id=request.document_id,
            workflow="fhir",
            model={"repo_id": "", "prompt_version": "", "model_version": ""},
            result={"resources": []},
            warnings=["FHIR generation is disabled"],
            latency_ms=0,
        )

    return await orchestrator.run(
        workflow="fhir",
        request=request,
        request_id=request_id,
    )
