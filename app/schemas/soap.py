"""
Clinova Penthus AI Engine - SOAP Note Schemas
"""

from pydantic import BaseModel, Field


class SOAPResult(BaseModel):
    """SOAP note generation output schema."""
    subjective: str = Field(default="", description="Subjective findings - patient-reported symptoms")
    objective: str = Field(default="", description="Objective findings - examination and measurements")
    assessment: str = Field(default="", description="Clinical assessment and diagnosis")
    plan: str = Field(default="", description="Treatment plan and follow-up")

    model_config = {
        "json_schema_extra": {
            "example": {
                "subjective": "Patient reports fever for 3 days, dry cough, and fatigue. No chest pain.",
                "objective": "Temperature 38.5C, HR 92, BP 120/80, SpO2 97% on room air. Clear lung sounds.",
                "assessment": "Suspected upper respiratory tract infection, likely viral.",
                "plan": "1. Rest and hydration. 2. Acetaminophen 500mg q6h PRN fever. 3. Follow up in 3 days if no improvement.",
            }
        }
    }
