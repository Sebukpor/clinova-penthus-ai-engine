# Penthus Clinical AI Engine - Production Security Hardening Report

**Generated:** 2026-06-11  
**Version:** 1.2.0  
**Environment:** Production (ocr-instance)  
**Status:** ⚠️ **REQUIRES IMMEDIATE ATTENTION**

---

## Executive Summary

The Penthus Clinical AI Engine has been successfully deployed with all services running and healthy. However, **critical security hardening measures are required before this deployment can be considered production-ready**. This document identifies all security gaps and provides actionable remediation steps.

### Current Deployment Status

| Component | Status | Security Status |
|-----------|--------|-----------------|
| penthus-api | ✅ Running | ⚠️ Not Hardened |
| penthus-nginx | ✅ Running | ⚠️ HTTP Only |
| penthus-vllm | ✅ Running | ✅ Internal |
| penthus-postgres | ✅ Running | ✅ Internal |
| penthus-redis | ✅ Running | ✅ Internal |

---

## 🔴 CRITICAL Security Issues (Must Fix Immediately)

### 1. API Key Authentication is Permissive

**File:** `app/core/security.py` (Lines 231-246)

**Current State:**
```python
async def _validate_api_key(api_key: str) -> Optional[AuthenticatedUser]:
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
```

**Risk:** Any client with a key matching `penthus_test_*` gains full API access. No tenant isolation, no key rotation, no audit trail.

**Impact:** HIGH - Unauthorized access to PHI data, potential HIPAA violation

**Remediation Steps:**

1. **Generate Secure API Keys:**
   ```python
   import secrets
   secure_key = f"penthus_{secrets.token_urlsafe(32)}"
   ```

2. **Store Keys in Database:** Add hashed keys to the `users` table (`api_key_hash` column exists but unused).

3. **Update Validation Logic:**
   ```python
   async def _validate_api_key(api_key: str) -> Optional[AuthenticatedUser]:
       from app.db.session import get_db_session
       from sqlalchemy import select
       from app.db.models import User
       
       async with get_db_session() as session:
           result = await session.execute(
               select(User).where(User.status == "active")
           )
           users = result.scalars().all()
           
           for user in users:
               if user.api_key_hash and verify_password(api_key, user.api_key_hash):
                   # Build user with proper tenant isolation
                   return _build_user_from_db(user)
       
       return None
   ```

4. **Create Key Management Script:** Provide admin CLI to generate/revoke keys.

---

### 2. Development Mode Bypasses Authentication

**File:** `app/core/security.py` (Lines 200-209)

**Current State:**
```python
if settings.is_development or settings.is_testing:
    return AuthenticatedUser(
        user_id="dev_user",
        tenant_id="test_tenant",
        roles=[Role.API_SERVICE],
        permissions=ROLE_PERMISSIONS[Role.API_SERVICE],
        auth_type="dev",
    )
```

**Risk:** If `ENVIRONMENT` is misconfigured, authentication is completely bypassed.

**Current Environment Check:**
```bash
curl http://localhost/api/v1/health
# Returns: "environment":"production"
```

**Issue:** Despite reporting "production", the code may still allow dev mode if environment variable is not properly set in the container.

**Remediation:**
1. Remove development bypass entirely in production builds
2. Add explicit check: `if settings.is_production and (settings.is_development or settings.is_testing): raise ConfigurationError()`
3. Use separate Docker images for dev vs prod

---

### 3. Secret Key is Default/Weak

**File:** `app/core/config.py` (Line 105)

**Current State:**
```python
secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
```

**Risk:** JWT tokens can be forged if this default is not changed.

**Verification Required:**
```bash
docker exec penthus-api env | grep SECRET_KEY
```

**Remediation:**
1. Generate secure key: `openssl rand -hex 32`
2. Store in OCI Vault or environment variable
3. Never commit to `.env` file in version control
4. Rotate keys periodically

---

### 4. CORS Allows All Origins

**File:** `app/core/config.py` (Line 144)

**Current State:**
```python
cors_origins: list[str] = Field(default=["*"], alias="CORS_ORIGINS")
```

**Risk:** Any website can make authenticated requests to your API (CSRF-style attacks).

**Remediation:**
```bash
# Set in environment
CORS_ORIGINS='["https://your-clinic-domain.com","https://emr.your-domain.com"]'
```

---

### 5. Nginx Serving HTTP Only (No HTTPS)

**File:** `infra/compose/nginx.conf` (Lines 56-133)

**Current State:**
```nginx
server {
    listen 80;
    server_name _;
    # ... no HTTPS redirect
}

# HTTPS server block (uncomment when SSL certificates are configured)
# server {
#     listen 443 ssl http2;
#     ...
# }
```

**Risk:** All traffic including API keys and PHI data transmitted in cleartext.

**Impact:** CRITICAL - HIPAA violation, man-in-the-middle attacks possible

**Remediation Steps:**

1. **Obtain SSL Certificate:**
   - Use Let's Encrypt: `certbot --nginx -d your-domain.com`
   - Or use OCI Load Balancer with managed certificates

2. **Update Nginx Config:**
   ```nginx
   # Force HTTPS redirect
   server {
       listen 80;
       server_name your-domain.com;
       return 301 https://$server_name$request_uri;
   }

   server {
       listen 443 ssl http2;
       server_name your-domain.com;
       
       ssl_certificate /etc/nginx/ssl/fullchain.pem;
       ssl_certificate_key /etc/nginx/ssl/privkey.pem;
       ssl_protocols TLSv1.2 TLSv1.3;
       ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
       ssl_prefer_server_ciphers off;
       ssl_session_cache shared:SSL:10m;
       ssl_session_timeout 1d;
       ssl_session_tickets off;
       
       # HSTS header
       add_header Strict-Transport-Security "max-age=63072000" always;
       
       # ... rest of config
   }
   ```

3. **Update Docker Compose:** Mount certificate volumes

---

### 6. No Rate Limiting Enforcement

**File:** `infra/compose/nginx.conf` (Line 46)

**Current State:**
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
```

**Applied:** Line 76 - `limit_req zone=api_limit burst=20 nodelay;`

**Issue:** Rate limiting is configured but may not be sufficient for DDoS protection. Also, no rate limiting at the FastAPI level.

**Remediation:**
1. Add stricter limits for authentication endpoints
2. Implement per-API-key rate limiting
3. Add SlowAPI middleware to FastAPI:
   ```python
   from slowapi import Limiter, _rate_limit_exceeded_handler
   from slowapi.util import get_remote_address
   
   limiter = Limiter(key_func=get_remote_address)
   app.state.limiter = limiter
   app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
   
   @app.post("/api/v1/soap")
   @limiter.limit("10/minute")
   async def generate_soap(...):
   ```

---

## 🟡 HIGH Priority Security Issues

### 7. Database Credentials May Be Weak

**File:** `app/core/config.py` (Line 19)

**Current State:**
```python
url: str = "postgresql+asyncpg://penthus:changeme@localhost:5432/clinova"
```

**Risk:** Default password `changeme` may still be in use.

**Verification:**
```bash
docker exec penthus-postgres psql -U penthus -c "\du"
# Test if default password works
```

**Remediation:**
1. Change Postgres password immediately
2. Use strong password: `openssl rand -base64 32`
3. Update `.env` and restart containers
4. Restrict database user permissions to minimum required

---

### 8. Audit Logging May Not Be Enforced

**File:** `app/core/config.py` (Lines 147-148)

**Current State:**
```python
audit_log_enabled: bool = Field(default=True, alias="AUDIT_LOG_ENABLED")
audit_log_phi_masking: bool = Field(default=True, alias="AUDIT_LOG_PHI_MASKING")
```

**Verification Required:** Confirm these are set to `True` in production environment.

**Remediation:**
1. Verify audit logs are being written to database
2. Ensure PHI masking is working (check `app/services/audit_service.py`)
3. Set up log retention policy (HIPAA requires 6 years)
4. Forward logs to SIEM system

---

### 9. No Input Validation on File Uploads

**File:** `app/api/routes_ocr.py` (review needed)

**Risk:** Malicious files could be uploaded (PDF exploits, image bombs, etc.)

**Remediation:**
1. Validate MIME type strictly
2. Scan files for malware (ClamAV integration)
3. Limit file size (already set to 20M in nginx)
4. Sanitize filenames
5. Store uploads outside web root

---

### 10. Swagger/OpenAPI Docs Exposed

**File:** `app/main.py` (Lines 88-90)

**Current State:**
```python
docs_url="/docs" if settings.is_development else None,
redoc_url="/redoc" if settings.is_development else None,
openapi_url="/openapi.json" if settings.is_development else None,
```

**Status:** ✅ Correctly disabled in production based on `is_development` flag.

**Verification:**
```bash
curl -I http://localhost/docs
# Should return 404 in production
```

---

## 🟢 MEDIUM Priority Security Issues

### 11. No Health Check Authentication

**Current State:** `/health` endpoint is publicly accessible without authentication.

**Risk:** Information disclosure about system status.

**Recommendation:** 
- Keep basic health check public for load balancer
- Add detailed health check at `/api/v1/health/internal` requiring auth

---

### 12. Redis Has No Password

**Current State:** Redis connection URL likely uses default no-auth setup.

**Verification:**
```bash
docker exec penthus-redis redis-cli ping
# If returns PONG without AUTH, it's unprotected
```

**Remediation:**
1. Set Redis password in `docker-compose.yml`
2. Update `REDIS_URL` to include password: `redis://:password@redis:6379/0`
3. Restart Redis container

---

### 13. Container Network Isolation

**Current State:** All containers on same Docker network.

**Recommendation:**
- Separate frontend (nginx) from backend (api) network
- Database should only be accessible by API container
- Use Docker network segmentation

---

### 14. No Security Headers on API Responses

**Current State:** Nginx adds some headers (lines 61-64 in nginx.conf):
```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

**Missing Headers:**
- `Content-Security-Policy`
- `Permissions-Policy`
- `Strict-Transport-Security` (only with HTTPS)

---

### 15. Dependency Vulnerabilities

**Action Required:**
```bash
docker exec penthus-api pip list --outdated
# Or use safety/pip-audit
pip install pip-audit
pip-audit
```

**Remediation:** Set up automated dependency scanning in CI/CD.

---

## Security Implementation Checklist

### Immediate Actions (This Week)

- [ ] **1.1** Generate secure API keys using `secrets.token_urlsafe(32)`
- [ ] **1.2** Hash and store API keys in `users.api_key_hash` table
- [ ] **1.3** Update `_validate_api_key()` to query database
- [ ] **1.4** Revoke all `penthus_test_*` keys
- [ ] **2.1** Remove development authentication bypass
- [ ] **3.1** Generate new `SECRET_KEY` (32+ bytes)
- [ ] **3.2** Verify `SECRET_KEY` is set in container environment
- [ ] **4.1** Set `CORS_ORIGINS` to specific domains only
- [ ] **5.1** Obtain SSL certificate (Let's Encrypt or OCI)
- [ ] **5.2** Update nginx.conf to enable HTTPS
- [ ] **5.3** Configure HTTP to HTTPS redirect
- [ ] **7.1** Change PostgreSQL default password
- [ ] **12.1** Set Redis password

### Short-Term Actions (This Month)

- [ ] **6.1** Implement per-API-key rate limiting
- [ ] **6.2** Add SlowAPI middleware to FastAPI
- [ ] **8.1** Verify audit logging is functional
- [ ] **8.2** Test PHI masking in logs
- [ ] **9.1** Implement file upload validation
- [ ] **9.2** Integrate ClamAV or similar malware scanner
- [ ] **12.2** Enable Redis AUTH
- [ ] **13.1** Segment Docker networks
- [ ] **14.1** Add missing security headers
- [ ] **15.1** Run vulnerability scan on dependencies

### Long-Term Actions (Next Quarter)

- [ ] Implement OCI Vault integration for all secrets
- [ ] Set up automated security scanning in CI/CD
- [ ] Implement Web Application Firewall (WAF)
- [ ] Conduct penetration testing
- [ ] Achieve HIPAA compliance certification
- [ ] Implement automated backup encryption
- [ ] Set up intrusion detection system (IDS)
- [ ] Create incident response plan

---

## Code Changes Required

### File: `app/core/security.py`

Replace the `_validate_api_key` function:

```python
async def _validate_api_key(api_key: str) -> Optional[AuthenticatedUser]:
    """
    Validate API key against stored credentials in database.
    """
    from sqlalchemy import select
    from app.db.session import get_db_session
    from app.db.models import User
    
    if not api_key or len(api_key) < 20:
        return None
    
    async with get_db_session() as session:
        try:
            result = await session.execute(
                select(User).where(
                    User.status == "active",
                    User.api_key_hash.isnot(None)
                )
            )
            users = result.scalars().all()
            
            for user in users:
                if pwd_context.verify(api_key, user.api_key_hash):
                    # Update last login
                    user.last_login = utc_now()
                    await session.commit()
                    
                    # Build roles and permissions
                    roles = [Role(r) for r in user.roles] if user.roles else [Role.API_SERVICE]
                    permissions: List[Permission] = []
                    for role in roles:
                        permissions.extend(ROLE_PERMISSIONS.get(role, []))
                    
                    logger.info(
                        "api_key_auth_success",
                        user_id=str(user.id),
                        tenant_id=str(user.tenant_id),
                    )
                    
                    return AuthenticatedUser(
                        user_id=str(user.id),
                        tenant_id=str(user.tenant_id),
                        roles=roles,
                        permissions=list(set(permissions)),
                        auth_type="api_key",
                    )
        
        except Exception as e:
            logger.error("api_key_validation_error", error=str(e))
            return None
    
    return None
```

### File: `app/core/config.py`

Add validation for production settings:

```python
from pydantic import field_validator, ValidationError

class SecurityConfig(BaseSettings):
    # ... existing fields ...
    
    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v):
        if v == "change-me-in-production":
            import os
            if os.getenv("ENVIRONMENT", "development").lower() == "production":
                raise ValueError("SECRET_KEY must be changed in production")
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v
```

### File: `infra/compose/nginx.conf`

Enable HTTPS (after obtaining certificates):

```nginx
# HTTP server - redirect to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';" always;

    # ... rest of existing configuration ...
}
```

---

## Testing Security Hardening

After implementing changes, verify:

### 1. API Key Validation
```bash
# Should fail with old test key
curl -H "X-API-Key: penthus_test_123" http://localhost/api/v1/soap \
  -H "Content-Type: application/json" \
  -d '{"text": "test"}'

# Should succeed with new secure key
curl -H "X-API-Key: penthus_<secure-key>" http://localhost/api/v1/soap \
  -H "Content-Type: application/json" \
  -d '{"text": "test"}'
```

### 2. HTTPS Enforcement
```bash
# Should redirect to HTTPS
curl -I http://your-domain.com/api/v1/health

# Should work with HTTPS
curl -I https://your-domain.com/api/v1/health
```

### 3. CORS Restrictions
```bash
# From unauthorized origin - should fail
curl -H "Origin: http://evil.com" http://localhost/api/v1/health

# From authorized origin - should succeed
curl -H "Origin: https://your-clinic-domain.com" http://localhost/api/v1/health
```

### 4. Rate Limiting
```bash
# Send 50 rapid requests - should get 429 after limit
for i in {1..50}; do
  curl -I http://localhost/api/v1/health &
done
```

### 5. Swagger Docs Disabled
```bash
# Should return 404
curl -I http://localhost/docs
curl -I http://localhost/redoc
```

---

## Compliance Considerations

### HIPAA Requirements Addressed

| Requirement | Status | Notes |
|-------------|--------|-------|
| Access Control | 🔴 Partial | API keys need proper implementation |
| Audit Controls | 🟡 Partial | Logging enabled but needs verification |
| Integrity Controls | 🟡 Partial | Data hashing exists but needs enforcement |
| Transmission Security | 🔴 Not Implemented | HTTPS required |
| Authentication | 🔴 Partial | Permissive key validation |

### Recommended Next Steps for Compliance

1. **Conduct Risk Assessment**: Document all PHI data flows
2. **Sign BAA**: Ensure all vendors (OCI, etc.) have signed Business Associate Agreements
3. **Encryption at Rest**: Enable TDE for PostgreSQL, encrypt Redis persistence
4. **Backup Strategy**: Implement encrypted, off-site backups with 6-year retention
5. **Access Review**: Quarterly review of all API keys and user access
6. **Incident Response Plan**: Document procedures for data breach response

