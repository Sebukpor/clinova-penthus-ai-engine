"""
Clinova Penthus AI Engine - Database Models
SQLAlchemy ORM models for all clinical AI workflow entities.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func, text, JSON,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class with common configuration."""
    pass


def generate_uuid() -> uuid.UUID:
    """Generate a new UUID."""
    return uuid.uuid4()


class Tenant(Base):
    """Multi-tenant isolation root."""
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    settings: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    encounters: Mapped[List["Encounter"]] = relationship(back_populates="tenant", lazy="dynamic")
    documents: Mapped[List["Document"]] = relationship(back_populates="tenant", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name})>"


class User(Base):
    """User or service account for authentication."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    roles: Mapped[List[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    # Unique constraint on tenant + email
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"


class Encounter(Base):
    """Clinical encounter linking patient to workflow sessions."""
    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    patient_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="encounters")
    documents: Mapped[List["Document"]] = relationship(back_populates="encounter", lazy="dynamic")
    soap_results: Mapped[List["SOAPResult"]] = relationship(back_populates="encounter", lazy="dynamic")
    entity_results: Mapped[List["EntityResult"]] = relationship(back_populates="encounter", lazy="dynamic")
    fhir_resources: Mapped[List["FHIRResource"]] = relationship(back_populates="encounter", lazy="dynamic")
    clinical_contexts: Mapped[List["ClinicalContext"]] = relationship(back_populates="encounter", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Encounter(id={self.id}, patient_ref={self.patient_ref})>"


class Document(Base):
    """Source document (image or text) uploaded for processing."""
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256
    object_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="documents")
    encounter: Mapped["Encounter"] = relationship(back_populates="documents")
    ocr_result: Mapped[Optional["OCRResult"]] = relationship(back_populates="document", uselist=False)

    # Unique constraint on tenant + content_hash for deduplication
    __table_args__ = (
        UniqueConstraint("tenant_id", "content_hash", name="uq_documents_tenant_hash"),
        Index("idx_documents_tenant_encounter", "tenant_id", "encounter_id"),
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, hash={self.content_hash[:16]}...)>"


class OCRResult(Base):
    """OCR extraction result - durable source of truth."""
    __tablename__ = "ocr_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    entities: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    layout: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="ocr_result")

    __table_args__ = (
        UniqueConstraint("tenant_id", "document_id", name="uq_ocr_tenant_document"),
        Index("idx_ocr_document_lookup", "tenant_id", "document_id"),
    )

    def __repr__(self) -> str:
        return f"<OCRResult(id={self.id}, doc={self.document_id}, lang={self.language})>"


class SOAPResult(Base):
    """Generated SOAP note result."""
    __tablename__ = "soap_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    subjective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    encounter: Mapped["Encounter"] = relationship(back_populates="soap_results")

    __table_args__ = (
        Index("idx_soap_encounter", "tenant_id", "encounter_id"),
    )

    def __repr__(self) -> str:
        return f"<SOAPResult(id={self.id}, enc={self.encounter_id})>"


class EntityResult(Base):
    """Clinical entity extraction result."""
    __tablename__ = "entity_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    entities: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    encounter: Mapped["Encounter"] = relationship(back_populates="entity_results")

    __table_args__ = (
        Index("idx_entities_encounter", "tenant_id", "encounter_id"),
    )


class NormalizationResult(Base):
    """Clinical term normalization result."""
    __tablename__ = "normalization_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    normalized_terms: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_normalization_encounter", "tenant_id", "encounter_id"),
    )


class SummaryResult(Base):
    """Clinical summary generation result."""
    __tablename__ = "summary_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_findings: Mapped[List[str]] = mapped_column(JSONB, default=list)
    recommended_follow_up: Mapped[List[str]] = mapped_column(JSONB, default=list)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_summary_encounter", "tenant_id", "encounter_id"),
    )


class GapResult(Base):
    """Documentation gap detection result."""
    __tablename__ = "gap_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    missing_information: Mapped[List[str]] = mapped_column(JSONB, default=list)
    quality_warnings: Mapped[List[str]] = mapped_column(JSONB, default=list)
    suggestions: Mapped[List[str]] = mapped_column(JSONB, default=list)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_gap_encounter", "tenant_id", "encounter_id"),
    )


class TranslationResult(Base):
    """Clinical text translation result."""
    __tablename__ = "translation_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    source_language: Mapped[str] = mapped_column(String(10), nullable=False)
    target_language: Mapped[str] = mapped_column(String(10), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_translation_encounter", "tenant_id", "encounter_id"),
    )


class ClinicalContext(Base):
    """Shared clinical context state for an encounter/document."""
    __tablename__ = "clinical_contexts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    state: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    encounter: Mapped["Encounter"] = relationship(back_populates="clinical_contexts")

    __table_args__ = (
        UniqueConstraint("tenant_id", "encounter_id", "document_id", name="uq_context_tenant_encounter_doc"),
        Index("idx_context_encounter_lookup", "tenant_id", "encounter_id"),
    )

    def __repr__(self) -> str:
        return f"<ClinicalContext(id={self.id}, enc={self.encounter_id}, v={self.version})>"


class PromptVersion(Base):
    """Prompt version registry for clinical AI workflows."""
    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    prompt_key: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "soap.v1"
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    capability: Mapped[str] = mapped_column(String(30), nullable=False)  # ocr, soap, entities, etc.
    model_repo: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # draft, active, deprecated
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="development")
    response_format: Mapped[str] = mapped_column(String(20), nullable=False, default="json")
    schema_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0.1)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1200)
    system_message: Mapped[str] = mapped_column(Text, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[List[str]] = mapped_column(JSONB, default=list)
    is_ocr_breaking: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("prompt_key", "version", name="uq_prompt_key_version"),
        Index("idx_prompt_capability_env", "capability", "environment", "status"),
    )


class InferenceLog(Base):
    """Audit log for every model inference."""
    __tablename__ = "inference_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    workflow: Mapped[str] = mapped_column(String(30), nullable=False)
    model_repo: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_inference_workflow_time", "workflow", "created_at"),
        Index("idx_inference_request", "request_id"),
        Index("idx_inference_tenant", "tenant_id", "created_at"),
    )


class TerminologyCache(Base):
    """Cache for terminology service lookups."""
    __tablename__ = "terminology_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    system: Mapped[str] = mapped_column(String(20), nullable=False)  # SNOMED_CT, ICD11, RXNORM, LOINC
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    candidates: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "system", "query_hash", name="uq_terminology_tenant_system_hash"),
        Index("idx_terminology_lookup", "tenant_id", "system", "query_hash"),
    )


class FHIRResource(Base):
    """Generated FHIR resources."""
    __tablename__ = "fhir_resources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_delivery_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    encounter: Mapped["Encounter"] = relationship(back_populates="fhir_resources")

    __table_args__ = (
        Index("idx_fhir_encounter_type", "tenant_id", "encounter_id", "resource_type"),
    )


class AuditLog(Base):
    """Security audit log for all PHI access and clinical workflow actions."""
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="user")  # user, service, system
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_audit_tenant_time", "tenant_id", "created_at"),
        Index("idx_audit_actor", "actor_id", "created_at"),
        Index("idx_audit_action", "action", "resource_type"),
    )


class WorkflowState(Base):
    """Durable workflow execution state for async/retry workflows."""
    __tablename__ = "workflow_state"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    workflow: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending, running, completed, failed, retrying
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    output_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", name="uq_workflow_tenant_request"),
        Index("idx_workflow_status", "status", "next_retry_at"),
    )


class TerminologyRequest(Base):
    """Log of terminology service requests for audit."""
    __tablename__ = "terminology_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    encounter_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    system: Mapped[str] = mapped_column(String(20), nullable=False)
    query_terms: Mapped[List[str]] = mapped_column(JSONB, nullable=False)
    response_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_terminology_req_encounter", "tenant_id", "encounter_id"),
    )
