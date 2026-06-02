"""
Clinova Penthus AI Engine - Documentation Gap Detection Schemas
"""

from typing import List

from pydantic import BaseModel, Field


class GapResult(BaseModel):
    """Documentation gap detection output schema."""
    missing_information: List[str] = Field(default_factory=list, description="Missing required documentation")
    quality_warnings: List[str] = Field(default_factory=list, description="Quality concerns")
    suggestions: List[str] = Field(default_factory=list, description="Improvement suggestions")

    model_config = {
        "json_schema_extra": {
            "example": {
                "missing_information": [
                    "Allergies not documented",
                    "Past medical history incomplete - no surgical history",
                    "Social history missing smoking/alcohol status",
                ],
                "quality_warnings": [
                    "No vital signs recorded",
                    "Assessment lacks differential diagnosis",
                ],
                "suggestions": [
                    "Document current medications with dosages",
                    "Include family history of cardiac disease",
                    "Add ROS for constitutional symptoms",
                ],
            }
        }
    }
