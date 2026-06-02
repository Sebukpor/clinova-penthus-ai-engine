"""
Clinova Penthus AI Engine - API Dependencies
FastAPI dependency injection for the orchestrator and services.
"""

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import Depends, Request

from app.context.cache import CacheClient
from app.context.store import ClinicalContextStore
from app.core.config import get_settings
from app.core.logging import clear_log_context, get_logger, set_correlation_id, set_tenant_context
from app.db.repositories import (
    AuditLogRepository, ClinicalContextRepository, DocumentRepository,
    EntityResultRepository, FHIRResourceRepository, InferenceLogRepository,
    NormalizationResultRepository, OCRResultRepository, PromptVersionRepository,
    SOAPResultRepository, SummaryResultRepository, WorkflowStateRepository,
)
from app.db.session import get_db_session
from app.llm.vllm_client import VLLMClient
from app.orchestrator.engine import ClinicalAIOrchestrator
from app.orchestrator.ocr_dependency import OCRDependencyResolver
from app.prompts.manager import PromptManager
from app.services.audit_service import AuditService
from app.services.document_service import DocumentService
from app.services.inference_log_service import InferenceLogService
from app.services.object_storage import ObjectStorageService
from app.terminology.client import TerminologyGatewayClient

logger = get_logger(__name__)

# Singleton instances
_vllm_client: Optional[VLLMClient] = None
_prompt_manager: Optional[PromptManager] = None
_cache_client: Optional[CacheClient] = None
_object_storage: Optional[ObjectStorageService] = None


async def get_vllm_client() -> VLLMClient:
    """Get or create vLLM client singleton."""
    global _vllm_client
    if _vllm_client is None:
        _vllm_client = VLLMClient()
    return _vllm_client


async def get_prompt_manager() -> PromptManager:
    """Get or create prompt manager singleton."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
        await _prompt_manager.initialize()
    return _prompt_manager


async def get_cache_client() -> CacheClient:
    """Get or create cache client singleton."""
    global _cache_client
    if _cache_client is None:
        _cache_client = await CacheClient().connect()
    return _cache_client


async def get_object_storage() -> ObjectStorageService:
    """Get or create object storage singleton."""
    global _object_storage
    if _object_storage is None:
        _object_storage = ObjectStorageService()
    return _object_storage


async def get_db_repositories(session=Depends(get_db_session)):
    """Get all database repositories."""
    return {
        "documents": DocumentRepository(session),
        "ocr_results": OCRResultRepository(session),
        "soap_results": SOAPResultRepository(session),
        "entity_results": EntityResultRepository(session),
        "normalization_results": NormalizationResultRepository(session),
        "summary_results": SummaryResultRepository(session),
        "clinical_contexts": ClinicalContextRepository(session),
        "prompt_versions": PromptVersionRepository(session),
        "inference_logs": InferenceLogRepository(session),
        "fhir_resources": FHIRResourceRepository(session),
        "audit_logs": AuditLogRepository(session),
        "workflow_state": WorkflowStateRepository(session),
    }


async def get_orchestrator(
    vllm: VLLMClient = Depends(get_vllm_client),
    prompts: PromptManager = Depends(get_prompt_manager),
    cache: CacheClient = Depends(get_cache_client),
    repos=Depends(get_db_repositories),
) -> ClinicalAIOrchestrator:
    """
    Build the Clinical AI Orchestrator with all dependencies.
    """
    # Build OCR resolver
    ocr_resolver = OCRDependencyResolver(
        vllm_client=vllm,
        prompt_manager=prompts,
        db_repository=repos if repos else None,
        cache_client=cache,
    )

    # Build terminology client
    terminology = TerminologyGatewayClient()

    # Build context store
    context_store = ClinicalContextStore(
        db_repository=repos.get("clinical_contexts") if repos else None,
        cache_client=cache,
    )

    # Build services
    object_storage = await get_object_storage()
    document_service = DocumentService(
        db_repository=repos.get("documents") if repos else None,
        object_storage=object_storage,
    )
    audit_service = AuditService(db_repository=repos.get("audit_logs") if repos else None)
    inference_service = InferenceLogService(db_repository=repos.get("inference_logs") if repos else None)

    return ClinicalAIOrchestrator(
        vllm_client=vllm,
        prompt_manager=prompts,
        ocr_resolver=ocr_resolver,
        context_store=context_store,
        terminology_client=terminology,
        audit_service=audit_service,
        inference_service=inference_service,
        document_service=document_service,
    )


async def get_request_id(request: Request) -> str:
    """Extract or generate request correlation ID."""
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    set_correlation_id(request_id)

    # Set tenant context if available
    tenant_id = request.headers.get("X-Tenant-ID", "unknown")
    set_tenant_context(tenant_id)

    return request_id


@asynccontextmanager
async def request_context(request_id: str, tenant_id: str):
    """Context manager for request lifecycle."""
    try:
        set_correlation_id(request_id)
        set_tenant_context(tenant_id)
        yield
    finally:
        clear_log_context()
