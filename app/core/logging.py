"""
Clinova Penthus AI Engine - Structured Logging
PHI-safe structured logging using structlog with correlation IDs.
"""

import logging
import sys
from contextvars import ContextVar
from typing import Any, Dict, Optional

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars
from structlog.processors import (
    JSONRenderer,
    StackInfoRenderer,
    TimeStamper,
    format_exc_info,
    remove_processors_meta,
    add_log_level,
)
from structlog.stdlib import (
    BoundLogger,
    LoggerFactory,
    add_log_level as stdlib_add_log_level,
    filter_by_level,
)

from app.core.config import get_settings

# Context variable for request correlation
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
tenant_id_var: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)
encounter_id_var: ContextVar[Optional[str]] = ContextVar("encounter_id", default=None)


def get_correlation_id() -> Optional[str]:
    """Get current request correlation ID."""
    return request_id_var.get()


def set_correlation_id(request_id: str) -> None:
    """Set request correlation ID in context."""
    request_id_var.set(request_id)
    bind_contextvars(request_id=request_id)


def set_tenant_context(tenant_id: str, encounter_id: Optional[str] = None) -> None:
    """Set tenant and encounter context for logging."""
    tenant_id_var.set(tenant_id)
    bind_contextvars(tenant_id=tenant_id)
    if encounter_id:
        encounter_id_var.set(encounter_id)
        bind_contextvars(encounter_id=encounter_id)


def clear_log_context() -> None:
    """Clear all bound context variables."""
    clear_contextvars()
    request_id_var.set(None)
    tenant_id_var.set(None)
    encounter_id_var.set(None)


class PHIMaskingProcessor:
    """Masks potential PHI fields in log entries."""

    PHI_FIELDS = {
        "patient_name", "patient_id", "mrn", "ssn", "dob", "date_of_birth",
        "phone", "email", "address", "raw_text", "phi", "ssn",
        "medical_record_number", "national_id",
    }
    MASK = "[REDACTED]"

    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        settings = get_settings()
        if not settings.audit_log_phi_masking:
            return event_dict

        for key in list(event_dict.keys()):
            if key.lower() in self.PHI_FIELDS:
                event_dict[key] = self.MASK
            elif isinstance(event_dict[key], dict):
                event_dict[key] = self._mask_dict(event_dict[key])
            elif isinstance(event_dict[key], list) and event_dict[key]:
                if isinstance(event_dict[key][0], dict):
                    event_dict[key] = [self._mask_dict(item) for item in event_dict[key]]
        return event_dict

    def _mask_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        for k, v in data.items():
            if k.lower() in self.PHI_FIELDS:
                result[k] = self.MASK
            elif isinstance(v, dict):
                result[k] = self._mask_dict(v)
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                result[k] = [self._mask_dict(item) for item in v]
            else:
                result[k] = v
        return result


def configure_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    shared_processors = [
        filter_by_level,
        stdlib_add_log_level,
        TimeStamper(fmt="iso"),
        merge_contextvars,
        StackInfoRenderer(),
        format_exc_info,
        PHIMaskingProcessor(),
    ]

    if settings.is_development:
        # Pretty console output for development
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            context_class=dict,
            logger_factory=LoggerFactory(),
            wrapper_class=BoundLogger,
            cache_logger_on_first_use=True,
        )
    else:
        # JSON output for production
        structlog.configure(
            processors=shared_processors + [
                remove_processors_meta,
                JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=LoggerFactory(),
            wrapper_class=BoundLogger,
            cache_logger_on_first_use=True,
        )


def get_logger(name: str) -> BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
