"""
Clinova Penthus AI Engine - OCR Schemas
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OCREntity(BaseModel):
    """Entity extracted during OCR."""
    text: str = Field(..., description="Extracted text")
    type: str = Field(..., description="Entity type (symptom, duration, medication, etc.)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    bbox: Optional[List[float]] = Field(default=None, description="Bounding box [x1, y1, x2, y2]")


class OCRLayoutBlock(BaseModel):
    """Layout block from OCR."""
    type: str = Field(..., description="Block type (paragraph, heading, table, etc.)")
    text: str = Field(..., description="Block text content")
    bbox: Optional[List[float]] = Field(default=None, description="Bounding box")
    page: int = Field(default=1, description="Page number")


class OCRLayout(BaseModel):
    """Document layout information."""
    pages: int = Field(default=1, description="Number of pages")
    blocks: List[OCRLayoutBlock] = Field(default_factory=list, description="Layout blocks")


class OCRResult(BaseModel):
    """OCR extraction output schema."""
    document_id: str = Field(..., description="Source document ID")
    raw_text: str = Field(..., description="Extracted raw text")
    entities: List[OCREntity] = Field(default_factory=list, description="Extracted entities")
    layout: OCRLayout = Field(default_factory=OCRLayout, description="Document layout")
    language: str = Field(default="en", description="Detected language")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall OCR confidence")

    model_config = {
        "json_schema_extra": {
            "example": {
                "document_id": "doc_001",
                "raw_text": "Patient has fever for 3 days and cough.",
                "entities": [
                    {"text": "fever", "type": "symptom", "confidence": 0.97},
                    {"text": "3 days", "type": "duration", "confidence": 0.95},
                    {"text": "cough", "type": "symptom", "confidence": 0.96},
                ],
                "layout": {"pages": 1, "blocks": []},
                "language": "en",
                "confidence": 0.96,
            }
        }
    }
