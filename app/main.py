"""
Clinova Penthus AI Engine - FastAPI Application Entry Point
Penthus Clinical AI Orchestrator API.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes_context import router as context_router
from app.api.routes_entities import router as entities_router
from app.api.routes_fhir import router as fhir_router
from app.api.routes_gaps import router as gaps_router
from app.api.routes_health import router as health_router
from app.api.routes_icd import router as icd_router
from app.api.routes_normalization import router as normalization_router
from app.api.routes_ocr import router as ocr_router
from app.api.routes_snomed import router as snomed_router
from app.api.routes_soap import router as soap_router
from app.api.routes_summary import router as summary_router
from app.api.routes_translation import router as translation_router
from app.core.config import get_settings
from app.core.errors import PenthusError
from app.core.logging import configure_logging, get_logger
from app.core.observability import HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION, instrument_fastapi, setup_observability

logger = get_logger(__name__)


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    # Configure logging
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan handler."""
        logger.info(
            "application_starting",
            app=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        )

        # Initialize observability
        setup_observability(settings.app_name, settings.app_version)
        instrument_fastapi(app)

        # Initialize prompt manager
        from app.api.deps import get_prompt_manager
        prompts = await get_prompt_manager()
        logger.info("prompts_initialized", count=len(prompts.list_prompts()))

        yield

        # Shutdown
        from app.api.deps import get_vllm_client, get_cache_client
        try:
            vllm = await get_vllm_client()
            await vllm.close()
        except Exception as e:
            logger.warning("vllm_close_error", error=str(e))

        try:
            cache = await get_cache_client()
            await cache.disconnect()
        except Exception as e:
            logger.warning("cache_close_error", error=str(e))

        logger.info("application_shutdown_complete")

    # Create FastAPI app
    app = FastAPI(
        title=settings.app_name,
        description=(
            "Clinova Penthus Clinical AI Engine - "
            "AI-powered clinical documentation and intelligence platform. "
            "Single vLLM-hosted model powers OCR, SOAP, entity extraction, "
            "summarization, translation, FHIR extraction, and clinical normalization."
        ),
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS middleware
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Request timing middleware
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        """Record request metrics."""
        import time
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        method = request.method
        path = request.url.path
        status_code = str(response.status_code)

        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            endpoint=path,
            status_code=status_code,
        ).inc()
        HTTP_REQUEST_DURATION.labels(
            method=method,
            endpoint=path,
        ).observe(duration)

        return response

    # Exception handlers
    @app.exception_handler(PenthusError)
    async def penthus_exception_handler(request: Request, exc: PenthusError):
        """Handle Penthus errors."""
        logger.error(
            "penthus_error",
            code=exc.code.value,
            message=exc.message,
            request_id=exc.request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions."""
        logger.exception("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An internal error occurred",
                    "details": {},
                }
            },
        )

    # Register routers
    api_prefix = "/api/v1"

    app.include_router(health_router, prefix=api_prefix, tags=["Health"])
    app.include_router(ocr_router, prefix=f"{api_prefix}/ocr", tags=["OCR"])
    app.include_router(soap_router, prefix=f"{api_prefix}/soap", tags=["SOAP"])
    app.include_router(entities_router, prefix=f"{api_prefix}/entities", tags=["Entities"])
    app.include_router(normalization_router, prefix=f"{api_prefix}/normalization", tags=["Normalization"])
    app.include_router(summary_router, prefix=f"{api_prefix}/summary", tags=["Summary"])
    app.include_router(gaps_router, prefix=f"{api_prefix}/gaps", tags=["Gap Detection"])
    app.include_router(translation_router, prefix=f"{api_prefix}/translation", tags=["Translation"])
    app.include_router(fhir_router, prefix=f"{api_prefix}/fhir", tags=["FHIR"])
    app.include_router(snomed_router, prefix=f"{api_prefix}/snomed", tags=["Terminology"])
    app.include_router(icd_router, prefix=f"{api_prefix}/icd", tags=["Terminology"])
    app.include_router(context_router, prefix=api_prefix, tags=["Context"])

    # Root endpoint
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return app


# Create application instance
app = create_application()


def start() -> None:
    """Entry point for running the application."""
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers if not settings.api_reload else 1,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    start()
