"""
Clinova Penthus AI Engine - vLLM Client
OpenAI-compatible client for Penthus model with retry, timeout, and token tracking.
"""

import json
import time
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.errors import VLLMError, VLLMTimeoutError
from app.core.logging import get_logger
from app.core.observability import record_vllm_latency, record_vllm_tokens, vllm_span

logger = get_logger(__name__)


class VLLMResponse:
    """Structured vLLM response wrapper."""

    def __init__(
        self,
        content: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        finish_reason: Optional[str] = None,
        latency_ms: float = 0.0,
    ):
        self.content = content
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.finish_reason = finish_reason
        self.latency_ms = latency_ms


class VLLMClient:
    """OpenAI-compatible vLLM client for Penthus model."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.vllm.base_url.rstrip("/")
        self.model = self.settings.vllm.model
        self.timeout = self.settings.vllm.timeout_seconds
        self.max_retries = self.settings.vllm.max_retries
        self.retry_delay = self.settings.vllm.retry_delay_seconds
        self.api_key = self.settings.vllm.api_key

        # HTTP client with connection pooling
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            headers=headers,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        logger.info(
            "vllm_client_initialized",
            base_url=self.base_url,
            model=self.model,
            timeout=self.timeout,
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 10200,
        response_format: Optional[Dict[str, str]] = None,
        workflow: str = "unknown",
        request_id: Optional[str] = None,
        **kwargs,
    ) -> VLLMResponse:
        """
        Send chat completion request to vLLM with tracing and metrics.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
            response_format: Optional response format specification
            workflow: Workflow name for metrics
            request_id: Request ID for tracing

        Returns:
            VLLMResponse with content and token usage
        """
        settings = get_settings()
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        payload.update(kwargs)

        start_time = time.time()
        error_type: Optional[str] = None

        try:
            with vllm_span(workflow=workflow, request_id=request_id or "unknown"):
                response = await self._send_request(payload)

            elapsed_ms = (time.time() - start_time) * 1000

            # Parse response
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]

            # Extract token usage
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)

            record_vllm_tokens(self.model, input_tokens, output_tokens)
            record_vllm_latency(self.model, workflow, elapsed_ms)

            logger.debug(
                "vllm_request_success",
                workflow=workflow,
                latency_ms=round(elapsed_ms, 2),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=self.model,
            )

            return VLLMResponse(
                content=content,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=choice.get("finish_reason"),
                latency_ms=elapsed_ms,
            )

        except httpx.TimeoutException as e:
            elapsed_ms = (time.time() - start_time) * 1000
            error_type = "timeout"
            logger.error(
                "vllm_timeout",
                workflow=workflow,
                elapsed_ms=round(elapsed_ms, 2),
                error=str(e),
            )
            raise VLLMTimeoutError(
                message=f"vLLM request timed out after {self.timeout}s",
                details={"timeout_seconds": self.timeout, "elapsed_ms": round(elapsed_ms, 2)},
                request_id=request_id,
            )

        except httpx.HTTPStatusError as e:
            elapsed_ms = (time.time() - start_time) * 1000
            error_type = f"http_{e.response.status_code}"
            logger.error(
                "vllm_http_error",
                workflow=workflow,
                status_code=e.response.status_code,
                response=e.response.text[:500],
            )
            raise VLLMError(
                message=f"vLLM HTTP error: {e.response.status_code}",
                status_code=502,
                details={
                    "status_code": e.response.status_code,
                    "response_preview": e.response.text[:500],
                },
                request_id=request_id,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            error_type = type(e).__name__
            logger.error(
                "vllm_error",
                workflow=workflow,
                error_type=error_type,
                error=str(e),
            )
            raise VLLMError(
                message=f"vLLM request failed: {str(e)}",
                details={"error_type": error_type},
                request_id=request_id,
            )

    async def _send_request(self, payload: Dict[str, Any]) -> httpx.Response:
        """Send request to vLLM with retry logic."""
        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=self.retry_delay, min=1, max=10),
            retry=retry_if_exception_type((httpx.NetworkError, httpx.ConnectError, httpx.ReadError)),
            reraise=True,
        )
        async def _request() -> httpx.Response:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            return response

        return await _request()

    async def health_check(self) -> bool:
        """Check if vLLM service is healthy."""
        try:
            response = await self.client.get("/models", timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            logger.warning("vllm_health_check_failed", error=str(e))
            return False

    async def close(self) -> None:
        """Close HTTP client connections."""
        await self.client.aclose()
        logger.info("vllm_client_closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
