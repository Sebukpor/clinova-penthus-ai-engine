"""
Clinova Penthus AI Engine - Error Handling
Centralized exception hierarchy and error response models.
"""

from enum import Enum
from typing import Any, Dict, Optional

from fastapi import HTTPException, status


class ErrorCode(str, Enum):
    """Standardized error codes for API responses."""
    # General
    INTERNAL_ERROR = "internal_error"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    RATE_LIMITED = "rate_limited"
    SERVICE_UNAVAILABLE = "service_unavailable"
    BAD_REQUEST = "bad_request"

    # Clinical AI
    OCR_FAILED = "ocr_failed"
    OCR_CACHE_ERROR = "ocr_cache_error"
    WORKFLOW_NOT_SUPPORTED = "workflow_not_supported"
    PROMPT_NOT_FOUND = "prompt_not_found"
    PROMPT_RENDER_ERROR = "prompt_render_error"
    VLLM_TIMEOUT = "vllm_timeout"
    VLLM_ERROR = "vllm_error"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    JSON_PARSE_ERROR = "json_parse_error"
    JSON_REPAIR_FAILED = "json_repair_failed"
    SCHEMA_VALIDATION_ERROR = "schema_validation_error"

    # Terminology
    TERMINOLOGY_GATEWAY_ERROR = "terminology_gateway_error"
    TERMINOLOGY_TIMEOUT = "terminology_timeout"
    TERMINOLOGY_NOT_FOUND = "terminology_not_found"

    # FHIR
    FHIR_VALIDATION_ERROR = "fhir_validation_error"
    FHIR_MAPPING_ERROR = "fhir_mapping_error"
    FHIR_DELIVERY_ERROR = "fhir_delivery_error"

    # Data
    TENANT_ISOLATION_ERROR = "tenant_isolation_error"
    DOCUMENT_NOT_FOUND = "document_not_found"
    ENCOUNTER_NOT_FOUND = "encounter_not_found"
    CONTEXT_NOT_FOUND = "context_not_found"


class PenthusError(Exception):
    """Base exception for Penthus AI Engine."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        self.request_id = request_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
                "request_id": self.request_id,
            }
        }


class ValidationError(PenthusError):
    """Input validation error."""

    def __init__(
        self,
        message: str = "Validation error",
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
            request_id=request_id,
        )


class UnauthorizedError(PenthusError):
    """Authentication error."""

    def __init__(
        self,
        message: str = "Unauthorized",
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=ErrorCode.UNAUTHORIZED,
            status_code=status.HTTP_401_UNAUTHORIZED,
            request_id=request_id,
        )


class ForbiddenError(PenthusError):
    """Authorization / RBAC error."""

    def __init__(
        self,
        message: str = "Forbidden",
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=ErrorCode.FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            request_id=request_id,
        )


class NotFoundError(PenthusError):
    """Resource not found error."""

    def __init__(
        self,
        message: str = "Resource not found",
        code: ErrorCode = ErrorCode.NOT_FOUND,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_404_NOT_FOUND,
            request_id=request_id,
        )


class TenantIsolationError(PenthusError):
    """Tenant isolation violation."""

    def __init__(
        self,
        message: str = "Tenant isolation violation",
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=ErrorCode.TENANT_ISOLATION_ERROR,
            status_code=status.HTTP_403_FORBIDDEN,
            request_id=request_id,
        )


class OCRDependencyError(PenthusError):
    """OCR resolution or execution failure."""

    def __init__(
        self,
        message: str = "OCR processing failed",
        code: ErrorCode = ErrorCode.OCR_FAILED,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
            request_id=request_id,
        )


class VLLMError(PenthusError):
    """vLLM service communication error."""

    def __init__(
        self,
        message: str = "vLLM service error",
        code: ErrorCode = ErrorCode.VLLM_ERROR,
        status_code: int = status.HTTP_503_SERVICE_UNAVAILABLE,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            details=details,
            request_id=request_id,
        )


class VLLMTimeoutError(VLLMError):
    """vLLM request timeout."""

    def __init__(
        self,
        message: str = "vLLM request timed out",
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=ErrorCode.VLLM_TIMEOUT,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            details=details,
            request_id=request_id,
        )


class ModelOutputError(PenthusError):
    """Invalid or unparseable model output."""

    def __init__(
        self,
        message: str = "Invalid model output",
        code: ErrorCode = ErrorCode.INVALID_MODEL_OUTPUT,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
            request_id=request_id,
        )


class JSONRepairError(PenthusError):
    """JSON repair fallback failed."""

    def __init__(
        self,
        message: str = "JSON repair failed",
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=ErrorCode.JSON_REPAIR_FAILED,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
            request_id=request_id,
        )


class PromptNotFoundError(PenthusError):
    """Requested prompt version not found."""

    def __init__(
        self,
        message: str = "Prompt not found",
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=ErrorCode.PROMPT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
            request_id=request_id,
        )


class UnsupportedWorkflowError(PenthusError):
    """Requested workflow is not supported."""

    def __init__(
        self,
        workflow: str,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=f"Workflow '{workflow}' is not supported",
            code=ErrorCode.WORKFLOW_NOT_SUPPORTED,
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"workflow": workflow},
            request_id=request_id,
        )


class TerminologyGatewayError(PenthusError):
    """Terminology gateway communication error."""

    def __init__(
        self,
        message: str = "Terminology gateway error",
        code: ErrorCode = ErrorCode.TERMINOLOGY_GATEWAY_ERROR,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
            request_id=request_id,
        )


class FHIRError(PenthusError):
    """FHIR processing error."""

    def __init__(
        self,
        message: str = "FHIR processing error",
        code: ErrorCode = ErrorCode.FHIR_VALIDATION_ERROR,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
            request_id=request_id,
        )


class RateLimitError(PenthusError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code=ErrorCode.RATE_LIMITED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            request_id=request_id,
        )


def http_exception_from_penthus_error(error: PenthusError) -> HTTPException:
    """Convert a PenthusError to a FastAPI HTTPException."""
    return HTTPException(
        status_code=error.status_code,
        detail=error.to_dict(),
    )
