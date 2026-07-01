"""
Clinova Penthus AI Engine - Entity Extraction Schemas
"""

from typing import Optional

from pydantic import BaseModel, Field


class ClinicalEntity(BaseModel):
    """Extracted clinical entity."""
    text: str = Field(..., description="Original text span")
    type: str = Field(..., description="Entity type classification")
    normalized_text: Optional[str] = Field(default=None, description="Normalized/canonical form")
    source_span: Optional[str] = Field(default=None, description="Source context span")

    model_config = {
        "json_schema_extra": {
            "example": {
                "text": "fever",
                "type": "symptom",
                "normalized_text": "fever",
                "source_span": "Patient has fever for 3 days",
            }
        }
    }


class EntityTypeInfo:
    """Valid entity types for extraction."""
    SYMPTOM = "symptom"
    DIAGNOSIS = "diagnosis"
    FINDING = "finding"
    MEDICATION = "medication"
    PROCEDURE = "procedure"
    ALLERGY = "allergy"
    VITAL_SIGN = "vital_sign"
    LAB_RESULT = "lab_result"

    ALL = [
        SYMPTOM, DIAGNOSIS, FINDING, MEDICATION,
        PROCEDURE, ALLERGY, VITAL_SIGN, LAB_RESULT,
    ]


class EntityResult(BaseModel):
    """Entity extraction output schema."""
    entities: list[ClinicalEntity] = Field(default_factory=list, description="Extracted entities")
