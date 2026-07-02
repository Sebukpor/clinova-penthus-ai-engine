"""
Clinova Penthus AI Engine - Normalization Schemas
"""

from typing import Optional

from pydantic import BaseModel, Field


class NormalizedTerm(BaseModel):
    """Normalized clinical term."""
    source_text: str = Field(..., description="Original text")
    normalized_text: str = Field(..., description="Normalized clinical term")
    category: str = Field(..., description="Clinical category (symptom, diagnosis, medication, etc.)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_text": "HTN",
                "normalized_text": "hypertension",
                "category": "diagnosis",
            }
        }
    }


class NormalizationResult(BaseModel):
    """Normalization output schema."""
    normalized_terms: list[NormalizedTerm] = Field(default_factory=list)
