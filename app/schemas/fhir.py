"""
Clinova Penthus AI Engine - FHIR Schemas
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FHIRResource(BaseModel):
    """Generated FHIR resource wrapper."""
    resourceType: str = Field(..., description="FHIR resource type")
    resource: Dict[str, Any] = Field(..., description="FHIR R4 resource JSON")


class FHIRResult(BaseModel):
    """FHIR resource generation output schema."""
    resources: List[FHIRResource] = Field(default_factory=list, description="Generated FHIR resources")

    model_config = {
        "json_schema_extra": {
            "example": {
                "resources": [
                    {
                        "resourceType": "Condition",
                        "resource": {
                            "resourceType": "Condition",
                            "id": "cond-001",
                            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
                            "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
                            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category", "code": "encounter-diagnosis"}]}],
                            "code": {"text": "Upper respiratory tract infection"},
                            "subject": {"reference": "Patient/pat-001"},
                            "encounter": {"reference": "Encounter/enc-001"},
                        },
                    }
                ]
            }
        }
    }


class TerminologyCandidate(BaseModel):
    """Terminology coding candidate from external terminology service."""
    code: str = Field(..., description="Terminology code")
    display: str = Field(..., description="Code display name")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Match score")
    source: str = Field(default="unknown", description="Source terminology service")


class TerminologyResult(BaseModel):
    """Terminology mapping result (SNOMED CT or ICD-11)."""
    query: str = Field(..., description="Original query term")
    system: str = Field(..., description="Terminology system (SNOMED_CT, ICD11)")
    candidates: List[TerminologyCandidate] = Field(default_factory=list)
    ai_normalized: bool = Field(default=True, description="Whether AI normalization was used")
    terminology_service_available: bool = Field(default=True)
    warning: Optional[str] = Field(default=None)
