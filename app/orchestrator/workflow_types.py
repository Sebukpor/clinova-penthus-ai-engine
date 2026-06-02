"""
Clinova Penthus AI Engine - Workflow Types
Enumerations and type definitions for clinical AI workflows.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowType(str, Enum):
    """Supported clinical AI workflow types."""
    OCR = "ocr"
    SOAP = "soap"
    ENTITIES = "entities"
    NORMALIZATION = "normalization"
    SUMMARY = "summary"
    GAPS = "gaps"
    TRANSLATION = "translation"
    SNOMED = "snomed"
    ICD = "icd"
    FHIR = "fhir"

    @classmethod
    def all(cls) -> List[str]:
        return [m.value for m in cls]

    @classmethod
    def ai_direct(cls) -> List[str]:
        """Workflows that call the AI model directly."""
        return [
            cls.OCR, cls.SOAP, cls.ENTITIES, cls.NORMALIZATION,
            cls.SUMMARY, cls.GAPS, cls.TRANSLATION, cls.FHIR,
        ]

    @classmethod
    def terminology(cls) -> List[str]:
        """Workflows that require terminology service calls."""
        return [cls.SNOMED, cls.ICD]

    @classmethod
    def requires_ocr(cls, workflow: str) -> bool:
        """Check if workflow typically requires OCR input."""
        return workflow in [
            cls.OCR, cls.SOAP, cls.ENTITIES, cls.NORMALIZATION,
            cls.SUMMARY, cls.GAPS, cls.SNOMED, cls.ICD, cls.FHIR,
        ]


class WorkflowDependency(str, Enum):
    """Workflow dependencies for execution ordering."""
    OCR = "ocr"
    ENTITIES = "entities"
    SOAP = "soap"
    NORMALIZATION = "normalization"


class WorkflowConfig(BaseModel):
    """Configuration for a workflow execution."""
    workflow_type: WorkflowType = Field(..., description="Type of workflow")
    requires_ocr: bool = Field(default=False, description="Whether OCR is required")
    requires_entities: bool = Field(default=False, description="Whether entity extraction is required")
    requires_soap: bool = Field(default=False, description="Whether SOAP generation is required")
    requires_normalization: bool = Field(default=False, description="Whether normalization is required")
    calls_terminology: bool = Field(default=False, description="Whether terminology service is called")
    calls_fhir: bool = Field(default=False, description="Whether FHIR generation is involved")
    prompt_capability: str = Field(..., description="Capability key for prompt lookup")
    schema_ref: str = Field(..., description="Output schema reference")


# Workflow configurations
WORKFLOW_CONFIGS: Dict[WorkflowType, WorkflowConfig] = {
    WorkflowType.OCR: WorkflowConfig(
        workflow_type=WorkflowType.OCR,
        requires_ocr=False,  # OCR is the workflow itself
        prompt_capability="ocr",
        schema_ref="OCRResult",
    ),
    WorkflowType.SOAP: WorkflowConfig(
        workflow_type=WorkflowType.SOAP,
        requires_ocr=True,
        prompt_capability="soap",
        schema_ref="SOAPResult",
    ),
    WorkflowType.ENTITIES: WorkflowConfig(
        workflow_type=WorkflowType.ENTITIES,
        requires_ocr=True,
        prompt_capability="entities",
        schema_ref="EntityResult",
    ),
    WorkflowType.NORMALIZATION: WorkflowConfig(
        workflow_type=WorkflowType.NORMALIZATION,
        requires_ocr=True,
        requires_entities=True,
        prompt_capability="normalization",
        schema_ref="NormalizationResult",
    ),
    WorkflowType.SUMMARY: WorkflowConfig(
        workflow_type=WorkflowType.SUMMARY,
        requires_ocr=True,
        requires_entities=True,
        prompt_capability="summary",
        schema_ref="SummaryResult",
    ),
    WorkflowType.GAPS: WorkflowConfig(
        workflow_type=WorkflowType.GAPS,
        requires_ocr=True,
        requires_entities=True,
        prompt_capability="gaps",
        schema_ref="GapResult",
    ),
    WorkflowType.TRANSLATION: WorkflowConfig(
        workflow_type=WorkflowType.TRANSLATION,
        requires_ocr=True,
        prompt_capability="translation",
        schema_ref="TranslationResult",
    ),
    WorkflowType.SNOMED: WorkflowConfig(
        workflow_type=WorkflowType.SNOMED,
        requires_ocr=True,
        requires_entities=True,
        requires_normalization=True,
        calls_terminology=True,
        prompt_capability="snomed",
        schema_ref="TerminologyResult",
    ),
    WorkflowType.ICD: WorkflowConfig(
        workflow_type=WorkflowType.ICD,
        requires_ocr=True,
        requires_entities=True,
        requires_normalization=True,
        calls_terminology=True,
        prompt_capability="icd",
        schema_ref="TerminologyResult",
    ),
    WorkflowType.FHIR: WorkflowConfig(
        workflow_type=WorkflowType.FHIR,
        requires_ocr=True,
        requires_entities=True,
        requires_normalization=True,
        calls_fhir=True,
        prompt_capability="fhir",
        schema_ref="FHIRResult",
    ),
}


def get_workflow_config(workflow_type: WorkflowType) -> WorkflowConfig:
    """Get configuration for a workflow type."""
    if isinstance(workflow_type, str):
        workflow_type = WorkflowType(workflow_type)
    return WORKFLOW_CONFIGS[workflow_type]
