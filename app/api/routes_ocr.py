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
