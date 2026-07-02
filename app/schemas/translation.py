"""
Clinova Penthus AI Engine - Translation Schemas
"""

from pydantic import BaseModel, Field


class TranslationResult(BaseModel):
    """Clinical text translation output schema."""
    source_language: str = Field(..., description="Detected source language code")
    target_language: str = Field(..., description="Target language code")
    translated_text: str = Field(..., description="Translated clinical text")

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_language": "es",
                "target_language": "en",
                "translated_text": "The patient has had fever for three days and dry cough.",
            }
        }
    }
