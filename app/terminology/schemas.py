"""
Clinova Penthus AI Engine - Terminology Schemas
Pydantic schemas for terminology service requests and responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TerminologySearchRequest(BaseModel):
    """Request to terminology gateway for code lookup."""
    system: str = Field(..., description="Terminology system (SNOMED_CT, ICD11, RXNORM, LOINC)")
    terms: List[str] = Field(..., description="Normalized terms to search")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context (SOAP, entities)")
    max_results: int = Field(default=5, description="Maximum candidates per term")


class TerminologyCandidate(BaseModel):
    """Single terminology candidate result."""
    code: str = Field(..., description="Terminology code")
    display: str = Field(..., description="Display name")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Match confidence score")
    source: str = Field(default="unknown", description="Source terminology service")


class TerminologySearchResponse(BaseModel):
    """Response from terminology gateway."""
    system: str = Field(..., description="Terminology system")
    query_terms: List[str] = Field(..., description="Original query terms")
    candidates: List[TerminologyCandidate] = Field(default_factory=list, description="Matching candidates")
    total_results: int = Field(default=0, description="Total candidates returned")
    latency_ms: Optional[int] = Field(default=None, description="Query latency")
