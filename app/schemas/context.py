"""
Clinova Penthus AI Engine - Clinical Context Schema
Shared context object for encounter/document workflows.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ClinicalContext(BaseModel):
    """Shared clinical context maintained per encounter/document."""
    tenant_id: str = Field(..., description="Tenant identifier")
    encounter_id: str = Field(..., description="Encounter identifier")
    document_id: Optional[str] = Field(default=None, description="Document identifier")
    raw_text: Optional[str] = Field(default=None, description="OCR-extracted or provided text")
    ocr: Optional[Dict[str, Any]] = Field(default=None, description="OCR result snapshot")
    soap: Optional[Dict[str, Any]] = Field(default=None, description="SOAP result snapshot")
    entities: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted entities")
    normalized_terms: List[Dict[str, Any]] = Field(default_factory=list, description="Normalized terms")
    summary: Optional[Dict[str, Any]] = Field(default=None, description="Summary result snapshot")
    gaps: Optional[Dict[str, Any]] = Field(default=None, description="Gap detection result snapshot")
    translation: Optional[Dict[str, Any]] = Field(default=None, description="Translation result snapshot")
    snomed_candidates: List[Dict[str, Any]] = Field(default_factory=list, description="SNOMED CT candidates")
    icd_candidates: List[Dict[str, Any]] = Field(default_factory=list, description="ICD-11 candidates")
    fhir_resources: List[Dict[str, Any]] = Field(default_factory=list, description="Generated FHIR resources")
    workflow_state: Dict[str, Any] = Field(default_factory=dict, description="Workflow execution state")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp (ISO 8601)")

    @classmethod
    def from_db_state(cls, state: Dict[str, Any]) -> "ClinicalContext":
        """Create context from database state JSON."""
        return cls(**state)

    def to_db_state(self) -> Dict[str, Any]:
        """Convert to database state JSON."""
        data = self.model_dump()
        data["updated_at"] = datetime.utcnow().isoformat()
        return data
