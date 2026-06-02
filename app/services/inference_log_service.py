"""
Clinova Penthus AI Engine - Inference Log Service
Tracks every model inference for audit and performance monitoring.
"""

from typing import Any, Dict, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class InferenceLogService:
    """Service for logging model inferences."""

    def __init__(self, db_repository=None):
        self.db = db_repository

    async def log(
        self,
        tenant_id: str,
        request_id: str,
        workflow: str,
        model_repo: str,
        model_version: str,
        prompt_version: str,
        latency_ms: int,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        validation_status: str = "success",
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log a model inference event.

        Args:
            tenant_id: Tenant identifier
            request_id: Request correlation ID
            workflow: Workflow type
            model_repo: Model repository ID
            model_version: Model version
            prompt_version: Prompt version used
            latency_ms: Inference latency in milliseconds
            input_tokens: Input token count
            output_tokens: Output token count
            validation_status: Output validation status
            error: Error message if failed
            metadata: Additional metadata
        """
        if not self.db:
            logger.debug("inference_db_not_available", workflow=workflow)
            return

        try:
            await self.db.inference_logs.create(
                tenant_id=tenant_id,
                request_id=request_id,
                workflow=workflow,
                model_repo=model_repo,
                model_version=model_version,
                prompt_version=prompt_version,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                validation_status=validation_status,
                error=error,
                metadata=metadata or {},
            )
            logger.debug(
                "inference_logged",
                workflow=workflow,
                request_id=request_id,
                latency_ms=latency_ms,
            )
        except Exception as e:
            logger.error("inference_log_write_failed", workflow=workflow, error=str(e))
