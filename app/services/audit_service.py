"""
Clinova Penthus AI Engine - Audit Service
Security audit logging for all PHI access and clinical workflow actions.
"""

from typing import Any, Dict, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class AuditService:
    """Service for writing security audit logs."""

    def __init__(self, db_repository=None):
        self.db = db_repository

    async def log(
        self,
        tenant_id: str,
        action: str,
        resource_type: str,
        actor_id: Optional[str] = None,
        actor_type: str = "user",
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Write an audit log entry.

        Args:
            tenant_id: Tenant identifier
            action: Action performed (e.g., workflow.soap, data.access)
            resource_type: Type of resource accessed
            actor_id: ID of the actor
            actor_type: Type of actor (user, service, system)
            resource_id: ID of the resource
            ip_address: Client IP address
            user_agent: Client user agent
            request_id: Request correlation ID
            metadata: Additional metadata
        """
        if not self.db:
            logger.debug("audit_db_not_available", action=action)
            return

        try:
            await self.db.audit_logs.create(
                tenant_id=tenant_id,
                action=action,
                resource_type=resource_type,
                actor_id=actor_id,
                actor_type=actor_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                metadata=metadata or {},
            )
            logger.debug(
                "audit_logged",
                action=action,
                tenant_id=tenant_id,
                resource_type=resource_type,
            )
        except Exception as e:
            logger.error("audit_log_write_failed", action=action, error=str(e))

    async def log_phi_access(
        self,
        tenant_id: str,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        access_type: str = "read",
        request_id: Optional[str] = None,
    ) -> None:
        """Log PHI access specifically."""
        await self.log(
            tenant_id=tenant_id,
            action=f"phi.{access_type}",
            resource_type=resource_type,
            actor_id=actor_id,
            resource_id=resource_id,
            request_id=request_id,
            metadata={"phi": True, "access_type": access_type},
        )
