"""
Clinova Penthus AI Engine - Configuration
Centralized application settings using Pydantic Settings.
"""

import json
import os
from functools import lru_cache
from typing import Any, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """PostgreSQL database configuration."""
    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: str = "postgresql+asyncpg://penthus:changeme@localhost:5432/clinova"
    pool_size: int = 20
    max_overflow: int = 40
    pool_timeout: int = 30
    pool_recycle: int = 1800
    echo: bool = False


class RedisConfig(BaseSettings):
    """Redis cache configuration."""
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = "redis://localhost:6379/0"
    pool_size: int = 20
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    health_check_interval: int = 30


class VLLMConfig(BaseSettings):
    """vLLM model service configuration."""
    model_config = SettingsConfigDict(env_prefix="VLLM_")

    base_url: str = "http://localhost:8000/v1"
    model: str = "penthus-1.2-alpha-4b"
    timeout_seconds: int = 120
    max_retries: int = 3
    retry_delay_seconds: int = 2
    api_key: Optional[str] = None


class OCRConfig(BaseSettings):
    """OCR configuration."""
    model_config = SettingsConfigDict(env_prefix="OCR_")

    cache_ttl_seconds: int = 2592000  # 30 days
    force_rerun: bool = False


class ObjectStorageConfig(BaseSettings):
    """Object storage configuration (OCI / MinIO)."""
    model_config = SettingsConfigDict(env_prefix="OBJECT_STORAGE_")

    endpoint: str = "http://localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    region: str = "us-ashburn-1"
    bucket: str = "clinova-documents"
    secure: bool = False


class TerminologyConfig(BaseSettings):
    """Terminology gateway configuration."""
    model_config = SettingsConfigDict(env_prefix="TERMINOLOGY_")

    gateway_url: str = "http://localhost:8080"
    gateway_timeout_seconds: int = 10
    gateway_max_retries: int = 2
    cache_ttl_seconds: int = 604800  # 7 days


class FHIRConfig(BaseSettings):
    """FHIR interoperability configuration."""
    model_config = SettingsConfigDict(env_prefix="FHIR_")

    base_url: str = "http://localhost:8080/fhir"
    validation_enabled: bool = True
    r4_profile_url: str = "http://hl7.org/fhir/StructureDefinition/"


class ObservabilityConfig(BaseSettings):
    """OpenTelemetry and monitoring configuration."""
    model_config = SettingsConfigDict(env_prefix="OTEL_")

    exporter_otlp_endpoint: str = "http://localhost:4317"
    service_name: str = "penthus-ai-engine"
    service_version: str = "1.2.0"
    exporter_otlp_insecure: bool = True
    metrics_enabled: bool = True
    prometheus_port: int = 9090


class SecurityConfig(BaseSettings):
    """Security and authentication configuration."""
    model_config = SettingsConfigDict(env_prefix="")

    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    api_key_header: str = Field(default="X-API-Key", alias="API_KEY_HEADER")
    rate_limit_requests_per_minute: int = Field(default=60, alias="RATE_LIMIT_REQUESTS_PER_MINUTE")
    rate_limit_burst: int = Field(default=10, alias="RATE_LIMIT_BURST")


class FeatureFlags(BaseSettings):
    """Feature toggle configuration."""
    model_config = SettingsConfigDict(env_prefix="ENABLE_")

    snomed_endpoint: bool = True
    icd_endpoint: bool = True
    fhir_endpoint: bool = True
    gap_detection: bool = True
    translation: bool = True


class Settings(BaseSettings):
    """Central application settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="Penthus-Clinical-AI-Engine", alias="APP_NAME")
    app_version: str = Field(default="1.2.0", alias="APP_VERSION")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # API Server
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_workers: int = Field(default=1, alias="API_WORKERS")
    api_reload: bool = Field(default=True, alias="API_RELOAD")
    cors_origins: list[str] = Field(default=["*"], alias="CORS_ORIGINS")

    # Audit
    audit_log_enabled: bool = Field(default=True, alias="AUDIT_LOG_ENABLED")
    audit_log_phi_masking: bool = Field(default=True, alias="AUDIT_LOG_PHI_MASKING")

    # Sub-configs
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    vllm: VLLMConfig = Field(default_factory=VLLMConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    storage: ObjectStorageConfig = Field(default_factory=ObjectStorageConfig)
    terminology: TerminologyConfig = Field(default_factory=TerminologyConfig)
    fhir: FHIRConfig = Field(default_factory=FHIRConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    features: FeatureFlags = Field(default_factory=FeatureFlags)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [x.strip() for x in v.split(",")]
        return v

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_testing(self) -> bool:
        return self.environment.lower() == "testing"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


def reload_settings() -> Settings:
    """Force reload of application settings."""
    get_settings.cache_clear()
    return get_settings()
