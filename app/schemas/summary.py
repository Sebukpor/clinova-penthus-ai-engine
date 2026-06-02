"""
Clinova Penthus AI Engine - Summary Schemas
"""

from typing import List

from pydantic import BaseModel, Field


class SummaryResult(BaseModel):
    """Clinical summary generation output schema."""
    summary: str = Field(default="", description="Generated clinical summary")
    key_findings: List[str] = Field(default_factory=list, description="Key clinical findings")
    recommended_follow_up: List[str] = Field(default_factory=list, description="Recommended follow-up actions")

    model_config = {
        "json_schema_extra": {
            "example": {
                "summary": "45-year-old male presenting with 3-day history of fever and dry cough. Vital signs stable. Assessment: likely viral URI.",
                "key_findings": [
                    "Fever for 3 days (T 38.5C)",
                    "Dry cough, no hemoptysis",
                    "SpO2 97% on room air",
                ],
                "recommended_follow_up": [
                    "Follow up in 3 days if no improvement",
                    "Return immediately if dyspnea develops",
                    "Complete blood count if fever persists > 5 days",
                ],
            }
        }
    }
