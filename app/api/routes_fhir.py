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
