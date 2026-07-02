"""
Clinova Penthus AI Engine - Repository Layer
Async repository pattern for database access with tenant isolation.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import (
    AuditLog, ClinicalContext, Document, Encounter, EntityResult,
    FHIRResource, GapResult, InferenceLog, NormalizationResult,
    OCRResult, PromptVersion, SOAPResult, SummaryResult,
    TerminologyCache, TerminologyRequest, TranslationResult, WorkflowState,
)

logger = get_logger(__name__)


class BaseRepository:
    """Base repository with common operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _execute(self, stmt):
        """Execute statement and return result."""
        return await self.session.execute(stmt)


class DocumentRepository(BaseRepository):
    """Repository for Document operations."""

    async def get_by_id(self, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Optional[Document]:
        stmt = select(Document).where(
            and_(Document.tenant_id == tenant_id, Document.id == document_id)
        )
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_content_hash(self, tenant_id: uuid.UUID, content_hash: str) -> Optional[Document]:
        stmt = select(Document).where(
            and_(Document.tenant_id == tenant_id, Document.content_hash == content_hash)
        )
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID,
                     content_hash: str, **kwargs) -> Document:
        doc = Document(
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            content_hash=content_hash,
            **kwargs
        )
        self.session.add(doc)
        await self.session.flush()
        return doc


class OCRResultRepository(BaseRepository):
    """Repository for OCR result operations."""

    async def get_by_document(self, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Optional[OCRResult]:
        stmt = select(OCRResult).where(
            and_(OCRResult.tenant_id == tenant_id, OCRResult.document_id == document_id)
        )
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tenant_id: uuid.UUID, document_id: uuid.UUID,
                     raw_text: str, model_version: str, prompt_version: str,
                     language: str = "en",
                     entities: Optional[List[Dict]] = None,
                     layout: Optional[Dict] = None,
                     processing_time_ms: Optional[int] = None) -> OCRResult:
        ocr = OCRResult(
            tenant_id=tenant_id,
            document_id=document_id,
            raw_text=raw_text,
            language=language,
            entities=entities or [],
            layout=layout or {},
            model_version=model_version,
            prompt_version=prompt_version,
            processing_time_ms=processing_time_ms,
        )
        self.session.add(ocr)
        await self.session.flush()
        return ocr


class SOAPResultRepository(BaseRepository):
    """Repository for SOAP result operations."""

    async def get_by_encounter(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID) -> Optional[SOAPResult]:
        stmt = select(SOAPResult).where(
            and_(SOAPResult.tenant_id == tenant_id, SOAPResult.encounter_id == encounter_id)
        ).order_by(desc(SOAPResult.created_at))
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID,
                     subjective: str, objective: str, assessment: str, plan: str,
                     model_version: str, prompt_version: str,
                     document_id: Optional[uuid.UUID] = None,
                     processing_time_ms: Optional[int] = None) -> SOAPResult:
        soap = SOAPResult(
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            document_id=document_id,
            subjective=subjective,
            objective=objective,
            assessment=assessment,
            plan=plan,
            model_version=model_version,
            prompt_version=prompt_version,
            processing_time_ms=processing_time_ms,
        )
        self.session.add(soap)
        await self.session.flush()
        return soap


class EntityResultRepository(BaseRepository):
    """Repository for entity extraction result operations."""

    async def get_by_encounter(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID) -> Optional[EntityResult]:
        stmt = select(EntityResult).where(
            and_(EntityResult.tenant_id == tenant_id, EntityResult.encounter_id == encounter_id)
        ).order_by(desc(EntityResult.created_at))
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID,
                     entities: List[Dict], model_version: str, prompt_version: str,
                     document_id: Optional[uuid.UUID] = None,
                     processing_time_ms: Optional[int] = None) -> EntityResult:
        entity_result = EntityResult(
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            document_id=document_id,
            entities=entities,
            model_version=model_version,
            prompt_version=prompt_version,
            processing_time_ms=processing_time_ms,
        )
        self.session.add(entity_result)
        await self.session.flush()
        return entity_result


class NormalizationResultRepository(BaseRepository):
    """Repository for normalization result operations."""

    async def get_by_encounter(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID) -> Optional[NormalizationResult]:
        stmt = select(NormalizationResult).where(
            and_(NormalizationResult.tenant_id == tenant_id, NormalizationResult.encounter_id == encounter_id)
        ).order_by(desc(NormalizationResult.created_at))
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID,
                     normalized_terms: List[Dict], model_version: str, prompt_version: str,
                     document_id: Optional[uuid.UUID] = None,
                     processing_time_ms: Optional[int] = None) -> NormalizationResult:
        norm = NormalizationResult(
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            document_id=document_id,
            normalized_terms=normalized_terms,
            model_version=model_version,
            prompt_version=prompt_version,
            processing_time_ms=processing_time_ms,
        )
        self.session.add(norm)
        await self.session.flush()
        return norm


class SummaryResultRepository(BaseRepository):
    """Repository for summary result operations."""

    async def get_by_encounter(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID) -> Optional[SummaryResult]:
        stmt = select(SummaryResult).where(
            and_(SummaryResult.tenant_id == tenant_id, SummaryResult.encounter_id == encounter_id)
        ).order_by(desc(SummaryResult.created_at))
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID,
                     summary: str, key_findings: List[str], recommended_follow_up: List[str],
                     model_version: str, prompt_version: str,
                     document_id: Optional[uuid.UUID] = None,
                     processing_time_ms: Optional[int] = None) -> SummaryResult:
        summary_result = SummaryResult(
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            document_id=document_id,
            summary=summary,
            key_findings=key_findings,
            recommended_follow_up=recommended_follow_up,
            model_version=model_version,
            prompt_version=prompt_version,
            processing_time_ms=processing_time_ms,
        )
        self.session.add(summary_result)
        await self.session.flush()
        return summary_result


class GapResultRepository(BaseRepository):
    """Repository for gap detection result operations."""

    async def get_by_encounter(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID) -> Optional[GapResult]:
        stmt = select(GapResult).where(
            and_(GapResult.tenant_id == tenant_id, GapResult.encounter_id == encounter_id)
        ).order_by(desc(GapResult.created_at))
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID,
                     missing_information: List[str], quality_warnings: List[str],
                     suggestions: List[str], model_version: str, prompt_version: str,
                     document_id: Optional[uuid.UUID] = None,
                     processing_time_ms: Optional[int] = None) -> GapResult:
        gap = GapResult(
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            document_id=document_id,
            missing_information=missing_information,
            quality_warnings=quality_warnings,
            suggestions=suggestions,
            model_version=model_version,
            prompt_version=prompt_version,
            processing_time_ms=processing_time_ms,
        )
        self.session.add(gap)
        await self.session.flush()
        return gap


class TranslationResultRepository(BaseRepository):
    """Repository for translation result operations."""

    async def get_by_encounter(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID) -> Optional[TranslationResult]:
        stmt = select(TranslationResult).where(
            and_(TranslationResult.tenant_id == tenant_id, TranslationResult.encounter_id == encounter_id)
        ).order_by(desc(TranslationResult.created_at))
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID,
                     source_language: str, target_language: str,
                     source_text: str, translated_text: str,
                     confidence: Optional[float],
                     model_version: str, prompt_version: str,
                     document_id: Optional[uuid.UUID] = None,
                     processing_time_ms: Optional[int] = None) -> TranslationResult:
        trans = TranslationResult(
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            document_id=document_id,
            source_language=source_language,
            target_language=target_language,
            source_text=source_text,
            translated_text=translated_text,
            confidence=confidence,
            model_version=model_version,
            prompt_version=prompt_version,
            processing_time_ms=processing_time_ms,
        )
        self.session.add(trans)
        await self.session.flush()
        return trans


class ClinicalContextRepository(BaseRepository):
    """Repository for clinical context operations."""

    async def get_by_encounter(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID,
                               document_id: Optional[uuid.UUID] = None) -> Optional[ClinicalContext]:
        conditions = [
            ClinicalContext.tenant_id == tenant_id,
            ClinicalContext.encounter_id == encounter_id,
        ]
        if document_id:
            conditions.append(ClinicalContext.document_id == document_id)

        stmt = select(ClinicalContext).where(and_(*conditions)).order_by(desc(ClinicalContext.version))
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create_or_update(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID,
                               state: Dict[str, Any],
                               document_id: Optional[uuid.UUID] = None) -> ClinicalContext:
        # Try to get existing context
        existing = await self.get_by_encounter(tenant_id, encounter_id, document_id)

        if existing:
            existing.state = state
            existing.version += 1
            existing.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            return existing
        else:
            ctx = ClinicalContext(
                tenant_id=tenant_id,
                encounter_id=encounter_id,
                document_id=document_id,
                state=state,
                version=1,
            )
            self.session.add(ctx)
            await self.session.flush()
            return ctx


class PromptVersionRepository(BaseRepository):
    """Repository for prompt version operations."""

    async def get_active_by_capability(self, capability: str,
                                       environment: str = "production") -> Optional[PromptVersion]:
        stmt = select(PromptVersion).where(
            and_(
                PromptVersion.capability == capability,
                PromptVersion.environment == environment,
                PromptVersion.status == "active",
            )
        ).order_by(desc(PromptVersion.created_at))
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_key_version(self, prompt_key: str, version: str) -> Optional[PromptVersion]:
        stmt = select(PromptVersion).where(
            and_(PromptVersion.prompt_key == prompt_key, PromptVersion.version == version)
        )
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> PromptVersion:
        pv = PromptVersion(**kwargs)
        self.session.add(pv)
        await self.session.flush()
        return pv


class InferenceLogRepository(BaseRepository):
    """Repository for inference log operations."""

    async def create(self, tenant_id: uuid.UUID, request_id: str, workflow: str,
                     model_repo: str, model_version: str, prompt_version: str,
                     latency_ms: int, validation_status: str = "success",
                     input_tokens: Optional[int] = None, output_tokens: Optional[int] = None,
                     error: Optional[str] = None, metadata: Optional[Dict] = None) -> InferenceLog:
        log = InferenceLog(
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
        self.session.add(log)
        await self.session.flush()
        return log


class TerminologyCacheRepository(BaseRepository):
    """Repository for terminology cache operations."""

    async def get(self, tenant_id: uuid.UUID, system: str, query_hash: str) -> Optional[TerminologyCache]:
        stmt = select(TerminologyCache).where(
            and_(
                TerminologyCache.tenant_id == tenant_id,
                TerminologyCache.system == system,
                TerminologyCache.query_hash == query_hash,
                TerminologyCache.expires_at > datetime.now(timezone.utc),
            )
        )
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def set(self, tenant_id: uuid.UUID, system: str, query_hash: str,
                  query_text: str, candidates: List[Dict],
                  ttl_seconds: int = 604800) -> TerminologyCache:
        cache = TerminologyCache(
            tenant_id=tenant_id,
            system=system,
            query_hash=query_hash,
            query_text=query_text,
            candidates=candidates,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
        self.session.add(cache)
        await self.session.flush()
        return cache


class FHIRResourceRepository(BaseRepository):
    """Repository for FHIR resource operations."""

    async def get_by_encounter(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID) -> List[FHIRResource]:
        stmt = select(FHIRResource).where(
            and_(FHIRResource.tenant_id == tenant_id, FHIRResource.encounter_id == encounter_id)
        ).order_by(desc(FHIRResource.created_at))
        result = await self._execute(stmt)
        return result.scalars().all()

    async def create(self, tenant_id: uuid.UUID, encounter_id: uuid.UUID,
                     resource_type: str, resource: Dict[str, Any],
                     model_version: str, prompt_version: str) -> FHIRResource:
        fhir = FHIRResource(
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            resource_type=resource_type,
            resource=resource,
            model_version=model_version,
            prompt_version=prompt_version,
        )
        self.session.add(fhir)
        await self.session.flush()
        return fhir


class AuditLogRepository(BaseRepository):
    """Repository for audit log operations."""

    async def create(self, tenant_id: uuid.UUID, action: str, resource_type: str,
                     actor_id: Optional[str] = None, actor_type: str = "user",
                     resource_id: Optional[str] = None, ip_address: Optional[str] = None,
                     user_agent: Optional[str] = None, request_id: Optional[str] = None,
                     metadata: Optional[Dict] = None) -> AuditLog:
        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            metadata=metadata or {},
        )
        self.session.add(audit)
        await self.session.flush()
        return audit


class WorkflowStateRepository(BaseRepository):
    """Repository for workflow state operations."""

    async def get_by_request(self, tenant_id: uuid.UUID, request_id: str) -> Optional[WorkflowState]:
        stmt = select(WorkflowState).where(
            and_(WorkflowState.tenant_id == tenant_id, WorkflowState.request_id == request_id)
        )
        result = await self._execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, tenant_id: uuid.UUID, request_id: str, workflow: str,
                     input_data: Dict[str, Any], status: str = "pending",
                     max_retries: int = 3) -> WorkflowState:
        ws = WorkflowState(
            tenant_id=tenant_id,
            request_id=request_id,
            workflow=workflow,
            input_data=input_data,
            status=status,
            max_retries=max_retries,
        )
        self.session.add(ws)
        await self.session.flush()
        return ws

    async def update_status(self, tenant_id: uuid.UUID, request_id: str,
                           status: str, output_data: Optional[Dict] = None,
                           error_info: Optional[str] = None) -> None:
        updates = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if output_data is not None:
            updates["output_data"] = output_data
        if error_info is not None:
            updates["error_info"] = error_info
        if status == "completed":
            updates["completed_at"] = datetime.now(timezone.utc)

        stmt = update(WorkflowState).where(
            and_(WorkflowState.tenant_id == tenant_id, WorkflowState.request_id == request_id)
        ).values(**updates)
        await self._execute(stmt)


class TerminologyRequestRepository(BaseRepository):
    """Repository for terminology request audit operations."""

    async def create(self, tenant_id: uuid.UUID, system: str, query_terms: List[str],
                     encounter_id: Optional[uuid.UUID] = None,
                     response_count: Optional[int] = None,
                     latency_ms: Optional[int] = None,
                     error: Optional[str] = None) -> TerminologyRequest:
        req = TerminologyRequest(
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            system=system,
            query_terms=query_terms,
            response_count=response_count,
            latency_ms=latency_ms,
            error=error,
        )
        self.session.add(req)
        await self.session.flush()
        return req
