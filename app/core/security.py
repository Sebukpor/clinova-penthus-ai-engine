"""
Clinova Penthus AI Engine - Security
JWT authentication, API key validation, RBAC scaffolding, tenant isolation.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError, TenantIsolationError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Password hashing (for future user management)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
auth_scheme = HTTPBearer(auto_error=False)


class Role(str, Enum):
    """System roles for RBAC."""
    SYSTEM_ADMIN = "system_admin"
    CLINICAL_ADMIN = "clinical_admin"
    PHYSICIAN = "physician"
    NURSE = "nurse"
    API_SERVICE = "api_service"
    READ_ONLY = "read_only"


class Permission(str, Enum):
    """Granular permissions for clinical workflows."""
    OCR_EXECUTE = "ocr:execute"
    SOAP_EXECUTE = "soap:execute"
    ENTITIES_EXECUTE = "entities:execute"
    NORMALIZATION_EXECUTE = "normalization:execute"
    SUMMARY_EXECUTE = "summary:execute"
    GAPS_EXECUTE = "gaps:execute"
    TRANSLATION_EXECUTE = "translation:execute"
    SNOMED_EXECUTE = "snomed:execute"
    ICD_EXECUTE = "icd:execute"
    FHIR_EXECUTE = "fhir:execute"
    CONTEXT_READ = "context:read"
    ADMIN_PROMPTS = "admin:prompts"
    ADMIN_AUDIT = "admin:audit"
    ADMIN_TENANTS = "admin:tenants"


# Role-to-permissions mapping
ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.SYSTEM_ADMIN: list(Permission),
    Role.CLINICAL_ADMIN: [
        Permission.OCR_EXECUTE,
        Permission.SOAP_EXECUTE,
        Permission.ENTITIES_EXECUTE,
        Permission.NORMALIZATION_EXECUTE,
        Permission.SUMMARY_EXECUTE,
        Permission.GAPS_EXECUTE,
        Permission.TRANSLATION_EXECUTE,
        Permission.SNOMED_EXECUTE,
        Permission.ICD_EXECUTE,
        Permission.FHIR_EXECUTE,
        Permission.CONTEXT_READ,
        Permission.ADMIN_PROMPTS,
        Permission.ADMIN_AUDIT,
    ],
    Role.PHYSICIAN: [
        Permission.OCR_EXECUTE,
        Permission.SOAP_EXECUTE,
        Permission.ENTITIES_EXECUTE,
        Permission.NORMALIZATION_EXECUTE,
        Permission.SUMMARY_EXECUTE,
        Permission.GAPS_EXECUTE,
        Permission.TRANSLATION_EXECUTE,
        Permission.SNOMED_EXECUTE,
        Permission.ICD_EXECUTE,
        Permission.FHIR_EXECUTE,
        Permission.CONTEXT_READ,
    ],
    Role.NURSE: [
        Permission.OCR_EXECUTE,
        Permission.ENTITIES_EXECUTE,
        Permission.SUMMARY_EXECUTE,
        Permission.CONTEXT_READ,
    ],
    Role.API_SERVICE: [
        Permission.OCR_EXECUTE,
        Permission.SOAP_EXECUTE,
        Permission.ENTITIES_EXECUTE,
        Permission.NORMALIZATION_EXECUTE,
        Permission.SUMMARY_EXECUTE,
        Permission.GAPS_EXECUTE,
        Permission.TRANSLATION_EXECUTE,
        Permission.SNOMED_EXECUTE,
        Permission.ICD_EXECUTE,
        Permission.FHIR_EXECUTE,
        Permission.CONTEXT_READ,
    ],
    Role.READ_ONLY: [
        Permission.CONTEXT_READ,
    ],
}


class AuthenticatedUser:
    """Represents an authenticated principal."""

    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        roles: List[Role],
        permissions: List[Permission],
        auth_type: str = "jwt",  # "jwt" | "api_key"
        facility_id: Optional[str] = None,
        department_id: Optional[str] = None,
        email: Optional[str] = None,
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.roles = roles
        self.permissions = set(permissions)
        self.auth_type = auth_type
        self.facility_id = facility_id
        self.department_id = department_id
        self.email = email

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions or Role.SYSTEM_ADMIN in self.roles

    def has_role(self, role: Role) -> bool:
        """Check if user has a specific role."""
        return role in self.roles

    def can_access_tenant(self, tenant_id: str) -> bool:
        """Verify tenant isolation."""
        return self.tenant_id == tenant_id


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.security.access_token_expire_minutes))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.security.secret_key, algorithm=settings.security.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.security.secret_key, algorithms=[settings.security.jwt_algorithm])
        return payload
    except JWTError as e:
        raise UnauthorizedError(f"Invalid token: {str(e)}")


def _extract_token_from_header(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


async def authenticate_request(
    request: Request,
    api_key: Optional[str] = Security(api_key_header),
) -> AuthenticatedUser:
    """
    Authenticate request via API key or JWT token.
    Attempts API key first, falls back to JWT.
    """
    settings = get_settings()

    # Allow permissive authentication in development/testing for faster local testing
    settings = get_settings()
    if settings.is_development or settings.is_testing:
        return AuthenticatedUser(
            user_id="dev_user",
            tenant_id="test_tenant",
            roles=[Role.API_SERVICE],
            permissions=ROLE_PERMISSIONS[Role.API_SERVICE],
            auth_type="dev",
        )

    # Try API key authentication first
    if api_key:
        # In production, validate against database or OCI Vault
        # For now, implement a basic validation structure
        user = await _validate_api_key(api_key)
        if user:
            logger.debug("api_key_auth_success", user_id=user.user_id, tenant_id=user.tenant_id)
            return user

    # Try JWT authentication
    token = _extract_token_from_header(request)
    if token:
        payload = decode_access_token(token)
        user = _build_user_from_jwt(payload)
        logger.debug("jwt_auth_success", user_id=user.user_id, tenant_id=user.tenant_id)
        return user

    raise UnauthorizedError("Authentication required: provide API key or JWT token")


async def _validate_api_key(api_key: str) -> Optional[AuthenticatedUser]:
    """
    Validate API key against stored credentials.
    In production, this should query the database or OCI Vault.
    """
    # TODO: Implement proper API key validation against database
    # For scaffolding, we accept a well-known test key pattern
    if api_key.startswith("penthus_test_"):
        return AuthenticatedUser(
            user_id="test_service",
            tenant_id="test_tenant",
            roles=[Role.API_SERVICE],
            permissions=ROLE_PERMISSIONS[Role.API_SERVICE],
            auth_type="api_key",
        )
    return None


def _build_user_from_jwt(payload: Dict[str, Any]) -> AuthenticatedUser:
    """Build AuthenticatedUser from JWT payload."""
    roles = [Role(r) for r in payload.get("roles", [Role.READ_ONLY.value])]
    permissions: List[Permission] = []
    for role in roles:
        permissions.extend(ROLE_PERMISSIONS.get(role, []))
    # Deduplicate
    permissions = list(set(permissions))

    return AuthenticatedUser(
        user_id=payload.get("sub", "unknown"),
        tenant_id=payload.get("tenant_id", "unknown"),
        roles=roles,
        permissions=permissions,
        auth_type="jwt",
        facility_id=payload.get("facility_id"),
        department_id=payload.get("department_id"),
        email=payload.get("email"),
    )


def require_permission(permission: Permission):
    """Dependency factory to require a specific permission."""
    async def permission_checker(user: AuthenticatedUser = Depends(authenticate_request)) -> AuthenticatedUser:
        if not user.has_permission(permission):
            logger.warning(
                "permission_denied",
                user_id=user.user_id,
                required_permission=permission.value,
                user_permissions=[p.value for p in user.permissions],
            )
            raise ForbiddenError(f"Permission required: {permission.value}")
        return user
    return permission_checker


def require_tenant_access(tenant_id_param: str = "tenant_id"):
    """
    Dependency factory to enforce tenant isolation.
    Checks that the authenticated user's tenant matches the request tenant.
    """
    async def tenant_checker(
        request: Request,
        user: AuthenticatedUser = Depends(authenticate_request),
    ) -> AuthenticatedUser:
        # Extract tenant_id from path or query params
        path_tenant = request.path_params.get(tenant_id_param)
        query_tenant = request.query_params.get(tenant_id_param)
        body_tenant = None

        # Try to extract from JSON body for POST requests
        if request.method in ("POST", "PUT", "PATCH") and request.headers.get("content-type", "").startswith("application/json"):
            try:
                body = await request.json()
                body_tenant = body.get(tenant_id_param)
            except Exception:
                pass

        request_tenant = path_tenant or query_tenant or body_tenant

        if request_tenant and not user.can_access_tenant(request_tenant):
            logger.warning(
                "tenant_isolation_violation",
                user_id=user.user_id,
                user_tenant=user.tenant_id,
                request_tenant=request_tenant,
            )
            raise ForbiddenError("Tenant access denied")

        return user
    return tenant_checker


# Pre-built permission dependencies
require_ocr = require_permission(Permission.OCR_EXECUTE)
require_soap = require_permission(Permission.SOAP_EXECUTE)
require_entities = require_permission(Permission.ENTITIES_EXECUTE)
require_normalization = require_permission(Permission.NORMALIZATION_EXECUTE)
require_summary = require_permission(Permission.SUMMARY_EXECUTE)
require_gaps = require_permission(Permission.GAPS_EXECUTE)
require_translation = require_permission(Permission.TRANSLATION_EXECUTE)
require_snomed = require_permission(Permission.SNOMED_EXECUTE)
require_icd = require_permission(Permission.ICD_EXECUTE)
require_fhir = require_permission(Permission.FHIR_EXECUTE)
require_context_read = require_permission(Permission.CONTEXT_READ)
require_admin_prompts = require_permission(Permission.ADMIN_PROMPTS)
