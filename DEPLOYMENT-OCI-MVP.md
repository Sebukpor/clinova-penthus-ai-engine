# Clinova Penthus AI Engine - OCI MVP Deployment Guide

## Overview

This guide provides complete instructions for deploying the Clinova Penthus AI Engine on a single OCI Compute instance using Docker Compose. This is a production-ready MVP deployment suitable for clinical workloads.

**Target Instance:** `ocr-instance` (Ubuntu, previously hosted OCR service)  
**Architecture:**
```
Internet
    |
    v
Nginx (Reverse Proxy, TLS, Rate Limiting)
    |
    v
FastAPI Application (2 workers)
    |
    +-- PostgreSQL 16 (Clinical Data, Audit Logs)
    +-- Redis 7 (Caching Layer, 512MB limit)
    +-- vLLM (Model Inference - GPU)
    |   or
    +-- vLLM-Mock (CPU-only testing)
```

---

## Prerequisites

### Completed Server Preparation

Ensure you have completed all steps in **SERVER-PREPARATION.md**:
- [ ] Stale `medical-ocr-api` container removed (~16GB reclaimed)
- [ ] Apache stopped and removed (Port 80 freed)
- [ ] NVIDIA drivers installed and verified (`nvidia-smi` works)
- [ ] Docker and Docker Compose installed
- [ ] Ports 80/443 available
- [ ] Repository cloned to VM
- [ ] `.env` file configured with secure values

### Required Information

| Item | Description | Example |
|------|-------------|---------|
| VM Public IP | OCI Compute instance public IP | `129.146.123.45` |
| SSH Key | Private key for SSH access | `~/.ssh/id_rsa` |
| Domain (optional) | Domain name for SSL | `api.clinova.com` |
| HuggingFace Token | For model download | `hf_xxxxx` |

---

## Step 1: Connect to VM and Navigate to Project

```bash
# SSH into the VM
ssh -i ~/.ssh/id_rsa opc@<VM_PUBLIC_IP>

# Navigate to project directory
cd ~/penthus

# Verify repository structure
ls -la
```

Expected output:
```
total 80
drwxrwxr-x  9 opc opc  4096 Jun 11 05:59 .
drwx------  5 opc opc  4096 Jun 11 05:59 ..
-rw-r--r--  1 opc opc  1520 Jun 11 05:59 .env.example
-rw-r--r--  1 opc opc  2767 Jun 11 05:59 .gitignore
-rw-r--r--  1 opc opc 26579 Jun 11 05:59 README.md
drwxrwxr-x 14 opc opc  4096 Jun 11 05:59 app
drwxrwxr-x  2 opc opc  4096 Jun 11 05:59 docs
drwxrwxr-x  5 opc opc  4096 Jun 11 05:59 infra
drwxrwxr-x  2 opc opc  4096 Jun 11 05:59 prompts
-rw-r--r--  1 opc opc  3582 Jun 11 05:59 pyproject.toml
drwxrwxr-x  2 opc opc  4096 Jun 11 05:59 tests
```

---

## Step 2: Verify Environment Configuration

```bash
# Check .env file exists
ls -la .env

# View current configuration (verify secrets are set)
cat .env | grep -E "SECRET_KEY|DB_PASSWORD|HF_TOKEN"

# Verify required variables
grep -E "^SECRET_KEY=changeme|^DB_PASSWORD=changeme" .env && echo "WARNING: Change default passwords!" || echo "Passwords appear customized"
```

**Required Environment Variables:**

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | JWT signing key (32+ bytes) | Yes |
| `DB_PASSWORD` | PostgreSQL password | Yes |
| `HF_TOKEN` | HuggingFace API token | Yes (for vLLM) |
| `ENVIRONMENT` | Should be `production` | Yes |

---

## Step 3: Build and Deploy

### Option A: Full Deployment (Recommended)

```bash
# Navigate to compose directory
cd ~/penthus/infra/compose

# Run full deployment
./deployment.sh deploy
```

This script will:
1. Check prerequisites (Docker, Docker Compose)
2. Build Docker images from source
3. Start all services
4. Run database migrations
5. Verify health endpoints

### Option B: Manual Step-by-Step

```bash
cd ~/penthus/infra/compose

# Step 1: Build images
docker compose build

# Step 2: Start services
docker compose up -d

# Step 3: Wait for PostgreSQL
sleep 30

# Step 4: Run migrations
docker exec penthus-api alembic upgrade head

# Step 5: Check status
docker compose ps
```

---

## Step 4: Verify Deployment

### 4.1 Container Status

```bash
# Check all containers are running
docker compose ps

# Expected output:
# NAME                STATUS                   PORTS
# penthus-api         Up (healthy)             8000/tcp
# penthus-nginx       Up (healthy)             0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
# penthus-postgres    Up (healthy)             5432/tcp
# penthus-redis       Up (healthy)             6379/tcp
# penthus-vllm        Up (health: starting)    8000/tcp
```

### 4.2 Health Endpoints

```bash
# Test Nginx health
curl http://localhost/health

# Expected: {"status":"healthy","service":"penthus-nginx"}

# Test API health
curl http://localhost/api/v1/health

# Expected:
# {
#   "status": "healthy",
#   "version": "1.2.0",
#   "environment": "production",
#   "timestamp": "2024-06-11T..."
# }

# Test API readiness (checks all dependencies)
curl http://localhost/api/v1/readiness

# Expected:
# {
#   "ready": true,
#   "checks": {
#     "api": true,
#     "database": true,
#     "cache": true,
#     "vllm": true
#   },
#   "timestamp": "..."
# }
```

### 4.3 Run Health Check Script

```bash
cd ~/penthus/infra/compose
./healthcheck.sh
```

Expected output shows all services healthy:
```
============================================
Clinova Penthus AI Engine - Health Check
Timestamp: ...
============================================

[INFO] Checking container status...
[OK] penthus-nginx: running
[OK] penthus-api: running
[OK] penthus-postgres: running
[OK] penthus-redis: running
[OK] penthus-vllm: running

[INFO] Checking API health endpoint...
[OK] API health: HTTP 200

[INFO] Checking API readiness (dependencies)...
[OK] API readiness: all dependencies ready

...
Overall Status: HEALTHY
============================================
```

---

## Step 5: Test Clinical Workflows

### 5.1 OCR Workflow

```bash
# Test OCR endpoint (base64 encoded image)
curl -X POST http://localhost/api/v1/ocr/process \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant",
    "encounter_id": "test-encounter",
    "document_id": "doc-001",
    "image_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
  }' | python3 -m json.tool
```

### 5.2 SOAP Generation

```bash
curl -X POST http://localhost/api/v1/soap/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant",
    "encounter_id": "test-encounter",
    "document_id": "doc-001",
    "clinical_context": {}
  }' | python3 -m json.tool
```

### 5.3 Entity Extraction

```bash
curl -X POST http://localhost/api/v1/entities/extract \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant",
    "encounter_id": "test-encounter",
    "text": "Patient presents with hypertension and type 2 diabetes."
  }' | python3 -m json.tool
```

### 5.4 SNOMED CT Lookup

```bash
curl -X GET "http://localhost/api/v1/snomed/search?term=hypertension" \
  | python3 -m json.tool
```

### 5.5 ICD-11 Lookup

```bash
curl -X GET "http://localhost/api/v1/icd/search?term=diabetes" \
  | python3 -m json.tool
```

---

## Step 6: Configure Backup Cron Job

```bash
# Create backup directory
sudo mkdir -p /var/backups/penthus
sudo chown opc:opc /var/backups/penthus

# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * cd /home/opc/penthus/infra/compose && ./backup.sh >> /var/log/penthus/backup.log 2>&1

# Verify cron job
crontab -l

# Test backup manually
./backup.sh
```

---

## Step 7: Configure Monitoring (Optional)

### Systemd Service for Health Checks

```bash
# Create systemd service
sudo tee /etc/systemd/system/penthus-healthcheck.service > EOF
[Unit]
Description=Clinova Penthus Health Check
After=docker.service

[Service]
Type=oneshot
ExecStart=/home/opc/penthus/infra/compose/healthcheck.sh
User=opc
Group=opc

[Install]
WantedBy=multi-user.target
EOF

# Create timer for hourly checks
sudo tee /etc/systemd/system/penthus-healthcheck.timer > EOF
[Unit]
Description=Run Penthus health check hourly

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Unit=penthus-healthcheck.service

[Install]
WantedBy=timers.target
EOF

# Enable timer
sudo systemctl daemon-reload
sudo systemctl enable penthus-healthcheck.timer
sudo systemctl start penthus-healthcheck.timer

# Verify
systemctl list-timers | grep penthus
```

---

## Rollback Procedures

### Scenario 1: Failed Deployment

```bash
# Stop all services
cd ~/penthus/infra/compose
docker compose down

# Check logs for errors
docker compose logs api | tail -100

# Restore previous version if needed
git fetch origin
git checkout <previous-tag>

# Redeploy
./deployment.sh deploy
```

### Scenario 2: Database Migration Failure

```bash
# Check migration status
docker exec penthus-api alembic current

# Downgrade to previous version
docker exec penthus-api alembic downgrade -1

# Or downgrade to specific revision
docker exec penthus-api alembic downgrade <revision-id>

# Re-run migrations
docker exec penthus-api alembic upgrade head
```

### Scenario 3: Complete Rollback

```bash
# Stop and remove everything
docker compose down -v

# Restore database from backup
BACKUP_FILE=$(ls -t /var/backups/penthus/postgres_*.sql.gz | head -1)
gunzip -c "$BACKUP_FILE" | docker exec -i penthus-postgres psql -U penthus -d clinova

# Restart services
docker compose up -d
```

---

## Upgrade Procedures

### Minor Version Upgrade

```bash
# Navigate to project
cd ~/penthus

# Pull latest changes
git pull origin main

# Review changes
git diff HEAD~1

# Stop services
cd infra/compose
docker compose down

# Rebuild images
docker compose build --no-cache

# Start services
docker compose up -d

# Run migrations
docker exec penthus-api alembic upgrade head

# Verify
./healthcheck.sh
```

### Major Version Upgrade

```bash
# Create backup before major upgrade
./backup.sh

# Tag current state
cd ~/penthus
git tag pre-upgrade-$(date +%Y%m%d)

# Follow minor upgrade steps above
# Monitor logs closely for first hour
docker compose logs -f api
```

---

## Troubleshooting

### API Container Won't Start

```bash
# Check logs
docker compose logs api

# Common issues:
# 1. Database not ready - wait longer
# 2. Environment variable missing - check .env
# 3. Port already in use - check with ss -tlnp
```

### vLLM Out of Memory

```bash
# Reduce GPU memory usage
# Edit docker-compose.yml, change:
# --gpu-memory-utilization 0.90
# to:
# --gpu-memory-utilization 0.75

docker compose restart vllm
```

### Database Connection Errors

```bash
# Check PostgreSQL status
docker exec penthus-postgres pg_isready -U penthus -d clinova

# Check connection string
docker exec penthus-api env | grep DATABASE_URL

# Restart PostgreSQL
docker compose restart postgres
```

### High Latency

```bash
# Check vLLM queue
curl http://localhost:8000/metrics | grep vllm

# Check Redis cache hit rate
docker exec penthus-redis redis-cli INFO stats | grep keyspace_hits

# Consider scaling workers
# Edit .env: API_WORKERS=4
docker compose restart api
```

---

## Security Hardening

### Enable HTTPS

```bash
# Place SSL certificates in ssl directory
mkdir -p ~/penthus/infra/compose/ssl
cp /path/to/fullchain.pem ~/penthus/infra/compose/ssl/
cp /path/to/privkey.pem ~/penthus/infra/compose/ssl/

# Uncomment HTTPS block in nginx.conf
# Restart nginx
docker compose restart nginx

# Verify HTTPS
curl -k https://localhost/health
```

### Configure Rate Limiting

Rate limiting is already configured in nginx.conf:
- 10 requests/second per IP
- Burst of 20 requests

Adjust in `nginx.conf`:
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
```

### Enable Audit Logging

Audit logging is enabled by default. View logs:

```bash
# View audit logs in database
docker exec penthus-postgres psql -U penthus -d clinova -c \
  "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 10;"
```

---

## Performance Tuning

### PostgreSQL Optimization

```bash
# Edit postgresql.conf (inside container)
docker exec -it penthus-postgres psql -U penthus -d clinova

# Recommended settings for 4GB RAM:
# shared_buffers = 1GB
# effective_cache_size = 3GB
# work_mem = 16MB
# maintenance_work_mem = 256MB
```

### Redis Optimization

Already configured in docker-compose.yml:
- Max memory: 512MB
- Eviction policy: allkeys-lru
- Persistence: AOF enabled

### vLLM Optimization

For GPU instances:
- `--gpu-memory-utilization 0.90` - Use 90% of GPU memory
- `--max-model-len 8192` - Maximum context length
- `--enable-prefix-caching` - Cache common prefixes

---

## Cost Optimization

### CPU-Only Mode (Development/Testing)

```bash
# Use mock vLLM instead of real model
cd ~/penthus/infra/compose
docker compose --profile cpu up -d

# This starts vllm-mock instead of vllm
# No GPU required, suitable for testing
```

### Scheduled Shutdown (Non-Production)

```bash
# Stop services during off-hours
docker compose stop

# Start when needed
docker compose start
```

---

## Support Contacts

| Issue Type | Contact |
|------------|---------|
| Technical Issues | engineering@dasmedhub.com |
| Clinical Questions | clinical@dasmedhub.com |
| Security Concerns | security@dasmedhub.com |

---

## Appendix: Quick Reference Commands

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f api

# Restart specific service
docker compose restart api

# Run health check
./healthcheck.sh

# Create backup
./backup.sh

# Database shell
docker exec -it penthus-postgres psql -U penthus -d clinova

# Redis shell
docker exec -it penthus-redis redis-cli

# API shell
docker exec -it penthus-api python

# Clean up unused resources
docker system prune -a --volumes -f
```
