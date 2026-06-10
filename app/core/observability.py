"""
Clinova Penthus AI Engine - Core Observability
Structured JSON logging and request metrics (no OpenTelemetry/Prometheus).
"""

import time
from contextlib import contextmanager, asynccontextmanager
from typing import Any, Dict, Generator, Optional

from fastapi import Request, Response

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# No-op metric objects for test/runtime compatibility.
class _NoopMetric:
    def labels(self, **kwargs):
        return self

    def inc(self, amount: int = 1) -> None:
        return None

    def observe(self, value: float) -> None:
        return None


HTTP_REQUESTS_TOTAL = _NoopMetric()
HTTP_REQUEST_DURATION = _NoopMetric()

# Simple in-memory counters for basic metrics
_request_counts: Dict[str, int] = {}
_latency_totals: Dict[str, float] = {}


def setup_observability(app_name: str, app_version: str) -> None:
    """Initialize observability (simplified - no OTel/Prometheus)."""
    logger.info("observability_initialized", app=app_name, version=app_version)


def instrument_fastapi(app: Any) -> None:
    """No-op - FastAPI instrumentation handled by middleware."""
    pass


def instrument_sqlalchemy(engine: Any) -> None:
    """No-op - SQLAlchemy instrumentation removed."""
    pass


def instrument_redis() -> None:
    """No-op - Redis instrumentation removed."""
    pass


def get_tracer() -> Any:
    """Return a simple mock tracer for compatibility."""
    class MockTracer:
        def start_as_current_span(self, name: str, attributes: Optional[Dict] = None):
            return _null_context_manager()
    
    return MockTracer()


def _null_context_manager():
    """Null context manager for removed tracing."""
    class NullContext:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
    return NullContext()


# Metric helpers (simplified)
# ============================

def record_workflow_latency(workflow: str, latency_ms: float) -> None:
    """Record workflow processing latency."""
    key = f"workflow:{workflow}"
    _latency_totals[key] = _latency_totals.get(key, 0) + latency_ms
    _request_counts[key] = _request_counts.get(key, 0) + 1


def record_workflow_error(workflow: str, error_type: str) -> None:
    """Record a workflow error."""
    logger.error("workflow_error", workflow=workflow, error_type=error_type)


def record_vllm_latency(model: str, workflow: str, latency_ms: float) -> None:
    """Record vLLM inference latency."""
    key = f"vllm:{model}:{workflow}"
    _latency_totals[key] = _latency_totals.get(key, 0) + latency_ms
    _request_counts[key] = _request_counts.get(key, 0) + 1


def record_vllm_tokens(model: str, input_tokens: int, output_tokens: int) -> None:
    """Record token usage."""
    logger.debug("vllm_tokens", model=model, input_tokens=input_tokens, output_tokens=output_tokens)


def record_ocr_cache_hit(source: str = "hit") -> None:
    """Record OCR cache result."""
    logger.debug("ocr_cache", result=source)


def record_terminology_cache_hit(system: str, hit: bool = True) -> None:
    """Record terminology cache result."""
    result = "hit" if hit else "miss"
    logger.debug("terminology_cache", system=system, result=result)


def record_validation_failure(workflow: str, validation_type: str = "schema") -> None:
    """Record validation failure."""
    logger.warning("validation_failure", workflow=workflow, validation_type=validation_type)


def record_tenant_request(tenant_id: str, workflow: str) -> None:
    """Record tenant-scoped request."""
    logger.debug("tenant_request", tenant_id=tenant_id, workflow=workflow)


def record_inference_log(**kwargs) -> None:
    """Log inference details."""
    logger.info("inference_logged", **kwargs)


# Context managers (simplified - no actual tracing)
# =================================================

@contextmanager
def workflow_span(workflow: str, request_id: str, **attrs) -> Generator[Any, None, None]:
    """Context manager for workflow timing with automatic latency recording."""
    start_time = time.time()
    try:
        yield None
    except Exception as e:
        record_workflow_error(workflow, type(e).__name__)
        raise
    finally:
        elapsed_ms = (time.time() - start_time) * 1000
        record_workflow_latency(workflow, elapsed_ms)


@asynccontextmanager
async def async_workflow_span(workflow: str, request_id: str, **attrs):
    """Async context manager for workflow timing."""
    start_time = time.time()
    try:
        yield None
    except Exception as e:
        record_workflow_error(workflow, type(e).__name__)
        raise
    finally:
        elapsed_ms = (time.time() - start_time) * 1000
        record_workflow_latency(workflow, elapsed_ms)


@contextmanager
def vllm_span(workflow: str, **attrs) -> Generator[Any, None, None]:
    """Context manager for vLLM call timing."""
    start_time = time.time()
    try:
        yield None
    finally:
        elapsed_ms = (time.time() - start_time) * 1000
        settings = get_settings()
        record_vllm_latency(settings.vllm.model, workflow, elapsed_ms)


@contextmanager
def terminology_span(system: str, **attrs) -> Generator[Any, None, None]:
    """Context manager for terminology gateway call timing."""
    start_time = time.time()
    try:
        yield None
    finally:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.debug("terminology_call", system=system, latency_ms=elapsed_ms)


def get_prometheus_metrics() -> bytes:
    """Return empty metrics (Prometheus removed)."""
    return b""
