"""
Clinova Penthus AI Engine - Health Routes
GET /api/v1/health and /api/v1/readiness - Health and readiness checks.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from app.api.deps import get_cache_client, get_vllm_client
from app.context.cache import CacheClient
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.observability import get_prometheus_metrics
from app.db.session import check_database_health
from app.llm.vllm_client import VLLMClient

logger = get_logger(__name__)
router = APIRouter()


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Check if the API service is healthy.",
)
async def health_check():
    """Basic health check endpoint."""
    settings = get_settings()
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "api": True,
        },
    }


@router.get(
    "/readiness",
    status_code=status.HTTP_200_OK,
    summary="Readiness Check",
    description="Check if all dependencies are ready.",
)
async def readiness_check(
    cache: CacheClient = Depends(get_cache_client),
    vllm: VLLMClient = Depends(get_vllm_client),
):
    """
    Readiness check with dependency validation.

    Checks database, Redis cache, and vLLM service availability.
    """
    checks = {
        "api": True,
        "database": False,
        "cache": False,
        "vllm": False,
    }

    # Check database
    try:
        checks["database"] = await check_database_health()
    except Exception as e:
        logger.warning("readiness_db_check_failed", error=str(e))

    # Check Redis cache
    try:
        checks["cache"] = await cache.health_check()
    except Exception as e:
        logger.warning("readiness_cache_check_failed", error=str(e))

    # Check vLLM
    try:
        checks["vllm"] = await vllm.health_check()
    except Exception as e:
        logger.warning("readiness_vllm_check_failed", error=str(e))

    all_ready = all(checks.values())

    return {
        "ready": all_ready,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/metrics",
    status_code=status.HTTP_200_OK,
    summary="Prometheus Metrics",
    description="Export Prometheus metrics for monitoring.",
)
async def metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response
    metrics_data = get_prometheus_metrics()
    return Response(
        content=metrics_data,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
