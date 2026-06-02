"""
Clinova Penthus AI Engine - Response Schemas
Standardized response envelope and model info for all clinical AI workflows.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    """Model information for traceability."""
    repo_id: str = Field(..., description="Hugging Face model repository ID")
    prompt_version: str = Field(..., description="Prompt version used for inference")
    model_version: str = Field(default="unknown", description="Model checkpoint version")


class ClinicalResponse(BaseModel):
    """Standard response envelope for all clinical AI endpoints."""
    request_id: str = Field(..., description="Unique request identifier")
    tenant_id: str = Field(..., description="Tenant ID")
    encounter_id: str = Field(..., description="Encounter ID")
    document_id: Optional[str] = Field(default=None, description="Document ID")
    workflow: str = Field(..., description="Workflow that was executed")
    model: ModelInfo = Field(..., description="Model and prompt information")
    result: Dict[str, Any] = Field(..., description="Workflow-specific result")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings")
    latency_ms: int = Field(..., description="Total processing time in milliseconds")
    ocr_reused: bool = Field(default=False, description="Whether OCR result was reused from cache")

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "req_001",
                "tenant_id": "tenant_001",
                "encounter_id": "enc_001",
                "document_id": "doc_001",
                "workflow": "soap",
                "model": {
                    "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
                    "prompt_version": "soap.v1",
                    "model_version": "2026-05-07",
                },
                "result": {
                    "subjective": "Patient reports fever for 3 days and cough.",
                    "objective": "Temperature 38.5C, respiratory rate 22.",
                    "assessment": "Suspected upper respiratory infection.",
                    "plan": "Prescribe antibiotics and follow up in 3 days.",
                },
                "warnings": [],
                "latency_ms": 1200,
                "ocr_reused": True,
            }
        }
    }


class ErrorResponse(BaseModel):
    """Standardized error response."""
    error: Dict[str, Any] = Field(..., description="Error details")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="healthy")
    version: str = Field(default="1.2.0")
    environment: str = Field(default="development")
    checks: Dict[str, bool] = Field(default_factory=dict)
    timestamp: str = Field(default="")


class ReadinessResponse(BaseModel):
    """Readiness check response."""
    ready: bool = Field(...)
    checks: Dict[str, bool] = Field(default_factory=dict)
    timestamp: str = Field(default="")


class ContextResponse(BaseModel):
    """Clinical context retrieval response."""
    tenant_id: str = Field(...)
    encounter_id: str = Field(...)
    document_id: Optional[str] = Field(default=None)
    raw_text: Optional[str] = Field(default=None)
    ocr: Optional[Dict[str, Any]] = Field(default=None)
    soap: Optional[Dict[str, Any]] = Field(default=None)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    normalized_terms: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Optional[Dict[str, Any]] = Field(default=None)
    gaps: Optional[Dict[str, Any]] = Field(default=None)
    translation: Optional[Dict[str, Any]] = Field(default=None)
    snomed_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    icd_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    fhir_resources: List[Dict[str, Any]] = Field(default_factory=list)
    workflow_state: Dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1)
    updated_at: Optional[str] = Field(default=None)
