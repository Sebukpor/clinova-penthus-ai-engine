"""
Clinova Penthus AI Engine - Summary Route
POST /api/v1/summary - Generate clinical summaries.
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_orchestrator, get_request_id
from app.core.security import AuthenticatedUser, require_summary
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse

router = APIRouter()


@router.post(
    "",
    response_model=ClinicalResponse,
    status_code=status.HTTP_200_OK,
    summary="Clinical Summary Generation",
    description="Generate concise clinical summaries with key findings and follow-up recommendations.",
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
                            "request_id": "c3d4e5f6a1b2",
                            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
                            "document_id": "123e4567-e89b-12d3-a456-426614174000",
                            "workflow": "summary",
                            "model": {
                                "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                                "prompt_version": "summary.v1",
                                "model_version": "penthus-1.2-alpha-4b",
                            },
                            "result": {
                                "summary": "Patient attended routine ophthalmology OPD. Examination revealed mild bilateral refractive error (RE: +0.75/-1.50 x 180, LE: +0.00/-0.50 x 7) with visual acuity 6/12P bilaterally. IOP borderline at 21/23 mmHg. Presbyopia confirmed with +2.50 add. Prescribed E19 combination eye drops 6 times daily for 1 month. Follow-up in 1 month. Reviewed by Dr. Sana Zafar, Dept of Ophthalmology.",
                                "key_findings": [
                                    "Bilateral refractive error",
                                    "Visual acuity 6/12P both eyes",
                                    "IOP borderline high (21/23 mmHg)",
                                    "Presbyopia (+2.50 add)",
                                ],
                                "follow_up": "1 month",
                            },
                            "warnings": [],
                            "latency_ms": 14600,
                            "ocr_reused": True,
                        }
                    }
                }
            }
        },
    },
)
async def summary_generation(
    request: ClinicalRequest,
    http_request: Request,
    orchestrator: ClinicalAIOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
    user: AuthenticatedUser = Depends(require_summary),
):
    """Generate clinical summary from encounter data."""
    return await orchestrator.run(
        workflow="summary",
        request=request,
        request_id=request_id,
    )
