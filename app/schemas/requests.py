"""
Clinova Penthus AI Engine - Request Schemas
Standardized request envelope for all clinical AI workflows.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class RequestMetadata(BaseModel):
    """Request metadata for routing and context."""
    source: str = Field(default="api", description="Source system (e.g., doctor_tablet, api, webhook)")
    specialty: Optional[str] = Field(default=None, description="Clinical specialty")
    facility_id: Optional[str] = Field(default=None)
    department_id: Optional[str] = Field(default=None)
    user_id: Optional[str] = Field(default=None)
    extra: Dict[str, Any] = Field(default_factory=dict)


class ClinicalRequest(BaseModel):
    """Standard request envelope for all clinical AI endpoints."""
    tenant_id: str = Field(..., description="Tenant ID for multi-tenant isolation")
    encounter_id: str = Field(..., description="Clinical encounter identifier")
    document_id: Optional[str] = Field(default=None, description="Document identifier")
    patient_id: Optional[str] = Field(default=None, description="Patient reference ID")
    image: Optional[str] = Field(
        default=None,
        description="Base64-encoded image or object storage URI"
    )
    text: Optional[str] = Field(
        default=None,
        description="Plain text input (alternative to image)"
    )
    language: str = Field(default="en", description="ISO 639-1 language code")
    target_language: Optional[str] = Field(
        default=None,
        description="Target language for translation workflows"
    )
    force_rerun_ocr: bool = Field(
        default=False,
        description="Force OCR re-execution even if cached result exists"
    )
    metadata: RequestMetadata = Field(default_factory=RequestMetadata)
    prompt_override: Optional[str] = Field(
        default=None,
        description="Override prompt version (requires admin permission)"
    )
    model_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Override model parameters (temperature, max_tokens)"
    )

    @field_validator("image")
    @classmethod
    def validate_image_size(cls, v: Optional[str]) -> Optional[str]:
        if v and v.startswith("data:"):
            # Validate base64 data URI format
            if ";base64," not in v:
                raise ValueError("Invalid base64 data URI format")
        return v

    @field_validator("text")
    @classmethod
    def validate_text_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Text cannot be empty if provided")
        return v

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if len(v) < 2 or len(v) > 5:
            raise ValueError("Language code must be 2-5 characters (ISO 639-1)")
        return v.lower()

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, v: Optional[str]) -> Optional[str]:
        if v and (len(v) < 2 or len(v) > 5):
            raise ValueError("Target language code must be 2-5 characters")
        return v.lower() if v else v

    model_config = {
        "json_schema_extra": {
            "example": {
                "tenant_id": "tenant_001",
                "encounter_id": "enc_001",
                "document_id": "doc_001",
                "patient_id": "pat_001",
                "image": "base64-or-object-storage-uri",
                "text": None,
                "language": "en",
                "metadata": {
                    "source": "doctor_tablet",
                    "specialty": "general_medicine",
                },
            }
        }
    }
