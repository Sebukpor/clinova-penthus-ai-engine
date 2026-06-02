"""
Clinova Penthus AI Engine - Observability
OpenTelemetry tracing, Prometheus metrics, and structured request logging.
"""

import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Callable, Dict, Generator, Optional

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, Info, Gauge, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource as OTelResource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Prometheus Metrics
# ==================

APP_INFO = Info("penthus_app", "Application information")

# Request metrics
HTTP_REQUESTS_TOTAL = Counter(
    "penthus_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
HTTP_REQUEST_DURATION = Histogram(
    "penthus_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# Workflow metrics
WORKFLOW_LATENCY = Histogram(
    "clinova_workflow_latency_ms",
    "Workflow processing latency in milliseconds",
    ["workflow"],
    buckets=[50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000],
)
WORKFLOW_ERRORS_TOTAL = Counter(
    "clinova_workflow_errors_total",
    "Total workflow errors",
    ["workflow", "error_type"],
)
WORKFLOW_REQUESTS_IN_FLIGHT = Gauge(
    "clinova_requests_in_flight",
    "Number of workflow requests currently being processed",
    ["workflow"],
)

# vLLM metrics
VLLM_LATENCY = Histogram(
    "clinova_vllm_latency_ms",
    "vLLM inference latency in milliseconds",
    ["model", "workflow"],
    buckets=[100, 250, 500, 1000, 2500, 5000, 10000],
)
VLLM_TOKENS_TOTAL = Counter(
    "clinova_vllm_tokens_total",
    "Total tokens processed by vLLM",
    ["model", "token_type"],
)

# OCR metrics
OCR_CACHE_HIT = Counter(
    "clinova_ocr_cache_hit_total",
    "OCR cache hit/miss counter",
    ["result"],  # "hit", "miss", "db_hit"
)

# Terminology metrics
TERMINOLOGY_CACHE_HIT = Counter(
    "clinova_terminology_cache_hit_total",
    "Terminology cache hit/miss counter",
    ["system", "result"],
)
TERMINOLOGY_LATENCY = Histogram(
    "clinova_terminology_latency_ms",
    "Terminology gateway latency in milliseconds",
    ["system"],
    buckets=[10, 25, 50, 100, 250, 500, 1000],
)

# Validation metrics
VALIDATION_FAILURES = Counter(
    "clinova_validation_failures_total",
    "Schema validation failure counter",
    ["workflow", "validation_type"],
)

# Tenant metrics
TENANT_REQUESTS = Counter(
    "clinova_tenant_requests_total",
    "Requests per tenant",
    ["tenant_id", "workflow"],
)

# Tracer
# ======

tracer: Optional[trace.Tracer] = None


def setup_observability(app_name: str, app_version: str) -> None:
    """Initialize OpenTelemetry and set up instrumentation."""
    global tracer
    settings = get_settings()

    # Set Prometheus app info
    APP_INFO.info({"name": app_name, "version": app_version, "environment": settings.environment})

    if not settings.observability.metrics_enabled:
        return

    # Configure OpenTelemetry
    resource = OTelResource.create(
        attributes={
            "service.name": settings.observability.service_name,
            "service.version": settings.observability.service_version,
            "deployment.environment": settings.environment,
        }
    )

    provider = TracerProvider(resource=resource)

    # OTLP exporter
    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.observability.exporter_otlp_endpoint,
            insecure=settings.observability.exporter_otlp_insecure,
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    except Exception as e:
        logger.warning("otlp_exporter_setup_failed", error=str(e))

    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(app_name, app_version)

    # Instrument HTTPX
    HTTPXClientInstrumentor().instrument()

    logger.info("observability_initialized", app=app_name, version=app_version)


def instrument_fastapi(app: Any) -> None:
    """Instrument FastAPI app with OpenTelemetry."""
    settings = get_settings()
    if settings.observability.metrics_enabled:
        FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy(engine: Any) -> None:
    """Instrument SQLAlchemy with OpenTelemetry."""
    settings = get_settings()
    if settings.observability.metrics_enabled:
        SQLAlchemyInstrumentor().instrument(engine=engine)


def instrument_redis() -> None:
    """Instrument Redis with OpenTelemetry."""
    settings = get_settings()
    if settings.observability.metrics_enabled:
        RedisInstrumentor().instrument()


def get_tracer() -> trace.Tracer:
    """Get the global tracer instance."""
    global tracer
    if tracer is None:
        tracer = trace.get_tracer("penthus-ai-engine")
    return tracer


# Metric helpers
# ==============

def record_workflow_latency(workflow: str, latency_ms: float) -> None:
    """Record workflow processing latency."""
    WORKFLOW_LATENCY.labels(workflow=workflow).observe(latency_ms)


def record_workflow_error(workflow: str, error_type: str) -> None:
    """Record a workflow error."""
    WORKFLOW_ERRORS_TOTAL.labels(workflow=workflow, error_type=error_type).inc()


def record_vllm_latency(model: str, workflow: str, latency_ms: float) -> None:
    """Record vLLM inference latency."""
    VLLM_LATENCY.labels(model=model, workflow=workflow).observe(latency_ms)


def record_vllm_tokens(model: str, input_tokens: int, output_tokens: int) -> None:
    """Record token usage."""
    VLLM_TOKENS_TOTAL.labels(model=model, token_type="input").inc(input_tokens)
    VLLM_TOKENS_TOTAL.labels(model=model, token_type="output").inc(output_tokens)


def record_ocr_cache_hit(source: str = "hit") -> None:
    """Record OCR cache result."""
    OCR_CACHE_HIT.labels(result=source).inc()


def record_terminology_cache_hit(system: str, hit: bool = True) -> None:
    """Record terminology cache result."""
    result = "hit" if hit else "miss"
    TERMINOLOGY_CACHE_HIT.labels(system=system, result=result).inc()


def record_validation_failure(workflow: str, validation_type: str = "schema") -> None:
    """Record validation failure."""
    VALIDATION_FAILURES.labels(workflow=workflow, validation_type=validation_type).inc()


def record_tenant_request(tenant_id: str, workflow: str) -> None:
    """Record tenant-scoped request."""
    TENANT_REQUESTS.labels(tenant_id=tenant_id, workflow=workflow).inc()


# Context managers for spans and timing
# ======================================

@contextmanager
def workflow_span(workflow: str, request_id: str, **attrs) -> Generator[trace.Span, None, None]:
    """Context manager for workflow tracing with automatic latency recording."""
    t = get_tracer()
    start_time = time.time()
    with t.start_as_current_span(
        name=f"workflow.{workflow}",
        attributes={"workflow": workflow, "request_id": request_id, **attrs},
    ) as span:
        WORKFLOW_REQUESTS_IN_FLIGHT.labels(workflow=workflow).inc()
        try:
            yield span
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            record_workflow_error(workflow, type(e).__name__)
            raise
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            record_workflow_latency(workflow, elapsed_ms)
            WORKFLOW_REQUESTS_IN_FLIGHT.labels(workflow=workflow).dec()
            span.set_attribute("latency_ms", elapsed_ms)


@asynccontextmanager
async def async_workflow_span(workflow: str, request_id: str, **attrs):
    """Async context manager for workflow tracing."""
    t = get_tracer()
    start_time = time.time()
    with t.start_as_current_span(
        name=f"workflow.{workflow}",
        attributes={"workflow": workflow, "request_id": request_id, **attrs},
    ) as span:
        WORKFLOW_REQUESTS_IN_FLIGHT.labels(workflow=workflow).inc()
        try:
            yield span
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            record_workflow_error(workflow, type(e).__name__)
            raise
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            record_workflow_latency(workflow, elapsed_ms)
            WORKFLOW_REQUESTS_IN_FLIGHT.labels(workflow=workflow).dec()
            span.set_attribute("latency_ms", elapsed_ms)


@contextmanager
def vllm_span(workflow: str, **attrs) -> Generator[trace.Span, None, None]:
    """Context manager for vLLM call tracing."""
    t = get_tracer()
    start_time = time.time()
    settings = get_settings()
    with t.start_as_current_span(
        name="vllm.chat_completion",
        attributes={"workflow": workflow, "model": settings.vllm.model, **attrs},
    ) as span:
        try:
            yield span
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            raise
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            record_vllm_latency(settings.vllm.model, workflow, elapsed_ms)
            span.set_attribute("latency_ms", elapsed_ms)


@contextmanager
def terminology_span(system: str, **attrs) -> Generator[trace.Span, None, None]:
    """Context manager for terminology gateway call tracing."""
    t = get_tracer()
    start_time = time.time()
    with t.start_as_current_span(
        name=f"terminology.{system}",
        attributes={"terminology_system": system, **attrs},
    ) as span:
        try:
            yield span
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            raise
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            TERMINOLOGY_LATENCY.labels(system=system).observe(elapsed_ms)
            span.set_attribute("latency_ms", elapsed_ms)


def get_prometheus_metrics() -> bytes:
    """Generate latest Prometheus metrics output."""
    return generate_latest()
