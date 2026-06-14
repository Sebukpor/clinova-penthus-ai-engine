# Clinova Penthus AI Engine

**DAS MedHub Clinical AI Platform - AI-Powered Clinical Documentation and Intelligence**

Penthus is the Clinical AI Engine powering the Clinova platform. It uses a single vLLM-hosted DAS medhub Penthus model to power OCR, SOAP generation, entity extraction, summarization, translation, FHIR extraction, documentation gap detection, and clinical normalization. External terminology services perform official clinical coding.

---

## Table of Contents

- [Architecture Principles](#architecture-principles)
- [System Topology](#system-topology)
- [Core Architecture Components](#core-architecture-components)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Data Flow & Workflows](#data-flow--workflows)
- [Quick Start - Local Development](#quick-start---local-development)
- [API Endpoints](#api-endpoints)
- [API Usage Examples](#api-usage-examples)
- [Model Configuration](#model-configuration)
- [OCR Dependency Resolution](#ocr-dependency-resolution)
- [Prompt Management](#prompt-management)
- [Database Schema](#database-schema)
- [Production Deployment - OCI](#production-deployment---oci)
- [Testing](#testing)
- [Security](#security)
- [Observability](#observability)
- [License](#license)
- [Support](#support)

---

## Architecture Principles

- **One model deployment only** - All AI capabilities through a single vLLM endpoint
- **OCR is the shared foundational layer** - Every image-based workflow resolves OCR first
- **OCR results are persisted and reused** - No duplicate OCR execution
- **Stateless compute with durable external state** - PostgreSQL, Redis, object storage
- **The AI model normalizes but never codes** - SNOMED CT, ICD-11 assigned by terminology services
- **vLLM is internal only** - No public model endpoint
- **All outputs are validated JSON** - Pydantic schema validation on every response
- **Every inference is auditable** - Full inference logging
- **Every workflow is tenant-isolated** - Multi-tenant by design
- **PHI is encrypted in transit and at rest** - HIPAA/GDPR aligned

---

## System Topology

```
Doctor Tablet App / API Clients
  |
  v
API Gateway (OCI Load Balancer)
  |
  v
FastAPI Clinical AI Orchestrator
  |
  +---> OCR Dependency Resolver
  |       +---> PostgreSQL (OCR results)
  |       +---> Redis (OCR cache)
  |       +---> vLLM Penthus Model (if needed)
  |
  +---> Prompt Manager (YAML + DB registry)
  |
  +---> vLLM Penthus Model Service
  |       Model: Sebukpor/medical-document-understanding-v2-fixed
  |       Served via: vLLM OpenAI-compatible API
  |
  +---> Clinical Context Store (PostgreSQL + Redis)
  |
  +---> Terminology Gateway Client (interface)
  |       +---> External SNOMED CT / ICD-11 / RxNorm / LOINC services
  |
  +---> FHIR Mapper & Validator
  |       +---> FHIR R4 resources
  |
  +---> Audit & Inference Logging (PostgreSQL)
```

---

## Core Architecture Components

### 1. Clinical AI Orchestrator (`app/orchestrator/`)

The central coordination layer that manages all clinical AI workflows:

- **`engine.py`** - Main orchestration engine coordinating all workflows
- **`ocr_dependency.py`** - OCR resolution with caching and deduplication
- **`workflow_types.py`** - Workflow type definitions and configurations
- **Key Responsibilities:**
  - Routes requests to appropriate workflow handlers
  - Manages OCR dependency resolution (check DB → Redis → vLLM)
  - Builds clinical context from encounter data
  - Executes workflow-specific AI inference
  - Updates context store with results
  - Logs all inferences for audit trail

### 2. API Layer (`app/api/`)

FastAPI route handlers for all endpoints:

| Module | Purpose |
|--------|---------|
| `routes_ocr.py` | Document text extraction endpoint |
| `routes_soap.py` | SOAP note generation endpoint |
| `routes_entities.py` | Clinical entity extraction endpoint |
| `routes_normalization.py` | Term normalization endpoint |
| `routes_summary.py` | Clinical summarization endpoint |
| `routes_gaps.py` | Documentation gap detection endpoint |
| `routes_translation.py` | Clinical translation endpoint |
| `routes_fhir.py` | FHIR R4 resource generation endpoint |
| `routes_snomed.py` | SNOMED CT mapping endpoint |
| `routes_icd.py` | ICD-11 mapping endpoint |
| `routes_context.py` | Clinical context retrieval endpoint |
| `routes_health.py` | Health and readiness checks |
| `deps.py` | Dependency injection (vLLM, prompts, cache, DB) |

### 3. LLM Client (`app/llm/`)

vLLM interaction layer with OpenAI-compatible API:

- **`vllm_client.py`** - Async HTTP client with retry logic, timeout handling
- **`messages.py`** - Message formatting for chat completions
- **`json_repair.py`** - JSON parsing and repair utilities for model outputs
- **Features:**
  - Automatic retry with exponential backoff
  - Request timeout management
  - Structured JSON output parsing
  - Schema validation integration

### 4. Prompt Management (`app/prompts/`)

Dynamic prompt loading and rendering system:

- **`manager.py`** - Central prompt manager interface
- **`registry.py`** - YAML prompt file registry
- **`renderer.py`** - Jinja2-based prompt templating
- **Stored in `/prompts/`:**
  - `ocr.v1.yaml` - Document text extraction
  - `soap.v1.yaml` - SOAP note generation
  - `entities.v1.yaml` - Clinical entity extraction
  - `normalization.v1.yaml` - Term normalization
  - `summary.v1.yaml` - Clinical summarization
  - `gaps.v1.yaml` - Documentation gap detection
  - `translation.v1.yaml` - Clinical translation
  - `fhir.v1.yaml` - FHIR resource generation

### 5. Database Layer (`app/db/`)

SQLAlchemy 2.0 async database access:

- **`models.py`** - SQLAlchemy ORM models (OCR results, encounters, documents, etc.)
- **`session.py`** - Async session factory
- **`repositories.py`** - Repository pattern for data access
- **`migrations/`** - Alembic migration scripts
- **Schema includes:**
  - `ocr_results` - Persisted OCR extractions
  - `encounters` - Clinical encounter records
  - `documents` - Document metadata
  - `inference_logs` - Audit trail of all AI inferences
  - `prompt_versions` - Managed prompt versioning

### 6. Context Store (`app/context/`)

Clinical context persistence and caching:

- **`store.py`** - Context persistence layer (PostgreSQL + Redis)
- **`cache.py`** - Redis cache client with TTL management
- **Purpose:** Maintain encounter state across multiple workflow invocations

### 7. Services (`app/services/`)

Business logic services:

| Service | Responsibility |
|---------|----------------|
| `audit_service.py` | PHI access audit logging |
| `inference_log_service.py` | AI inference audit trail |
| `document_service.py` | Document lifecycle management |
| `object_storage.py` | OCI Object Storage / MinIO integration |
| `image_preprocessor.py` | Image preprocessing for OCR (denoising, deskewing, contrast enhancement) |

### 8. Schemas (`app/schemas/`)

Pydantic v2 request/response models:

- **`requests.py`** - Clinical request envelope with tenant/encounter isolation
- **`responses.py`** - Standardized response envelope with model info and latency
- **Domain schemas:** `ocr.py`, `soap.py`, `entities.py`, `normalization.py`, `summary.py`, `gaps.py`, `translation.py`, `fhir.py`, `context.py`

### 9. Terminology Gateway (`app/terminology/`)

Interface to external clinical terminology services:

- **`client.py`** - Terminology service client interface
- **`schemas.py`** - Terminology request/response schemas
- **Supports:** SNOMED CT, ICD-11, RxNorm, LOINC via external gateway

### 10. FHIR Module (`app/fhir/`)

FHIR R4 interoperability:

- **`mapper.py`** - Maps AI outputs to FHIR resources (Condition, Observation, Procedure, MedicationStatement, etc.)
- **`validator.py`** - Validates FHIR resources against R4 schema

### 11. Core Framework (`app/core/`)

Application foundation:

- **`config.py`** - Pydantic settings management (environment variables)
- **`errors.py`** - Custom exception hierarchy
- **`logging.py`** - Structured logging with structlog
- **`security.py`** - JWT authentication, API keys, RBAC
- **`observability.py`** - OpenTelemetry tracing, structured logging

### 12. Workers (`app/workers/`)

Background job processing:

- **`jobs.py`** - Async background task definitions
- **`queue.py`** - Job queue management (Redis-based)

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| **Web Framework** | FastAPI + Pydantic v2 |
| **Database** | PostgreSQL 16 + SQLAlchemy 2 + Alembic |
| **Cache** | Redis 7 |
| **Model Serving** | vLLM (OpenAI-compatible API) |
| **Base Model** | DAS medhub Penthus model |
| **Object Storage** | OCI Object Storage / MinIO |
| **Observability** | OpenTelemetry + Structured Logging |
| **Container** | Docker + Docker Compose |
| **Cloud** | Oracle Cloud Infrastructure (OCI) |

---

## Project Structure

```
clinova-penthus-ai-engine/
├── app/
│   ├── api/                    # FastAPI route modules
│   │   ├── deps.py             # Dependency injection
│   │   ├── routes_*.py         # Endpoint handlers (12 route files)
│   │   └── __init__.py
│   ├── core/                   # Core framework
│   │   ├── config.py           # Application settings (Pydantic)
│   │   ├── errors.py           # Exception hierarchy
│   │   ├── logging.py          # Structured logging (structlog)
│   │   ├── observability.py    # Metrics & tracing (OpenTelemetry)
│   │   └── security.py         # Auth & RBAC (JWT, API keys)
│   ├── context/                # Clinical context & cache
│   │   ├── store.py            # Context persistence (PostgreSQL + Redis)
│   │   └── cache.py            # Redis cache client
│   ├── db/                     # Database layer
│   │   ├── models.py           # SQLAlchemy ORM models
│   │   ├── session.py          # Async session factory
│   │   ├── repositories.py     # Repository pattern
│   │   └── migrations/         # Alembic migrations
│   ├── fhir/                   # FHIR interoperability
│   │   ├── mapper.py           # FHIR resource mapping
│   │   └── validator.py        # FHIR R4 validation
│   ├── llm/                    # vLLM client
│   │   ├── vllm_client.py      # OpenAI-compatible async client
│   │   ├── messages.py         # Message formatting
│   │   └── json_repair.py      # JSON parsing & repair utilities
│   ├── orchestrator/           # AI orchestration
│   │   ├── engine.py           # Main ClinicalAIOrchestrator class
│   │   ├── ocr_dependency.py   # OCR resolver with caching
│   │   ├── workflow_types.py   # Workflow enum and configs
│   │   └── __init__.py
│   ├── prompts/                # Prompt management
│   │   ├── manager.py          # Prompt loader interface
│   │   ├── renderer.py         # Jinja2 template renderer
│   │   └── registry.py         # YAML prompt registry
│   ├── schemas/                # Pydantic v2 schemas
│   │   ├── requests.py         # Request envelopes
│   │   ├── responses.py        # Response envelopes
│   │   └── *.py                # Domain-specific schemas
│   ├── services/               # Business services
│   │   ├── audit_service.py    # PHI audit logging
│   │   ├── inference_log_service.py  # Inference audit trail
│   │   ├── document_service.py # Document lifecycle
│   │   ├── object_storage.py   # OCI Object Storage / MinIO
│   │   └── image_preprocessor.py     # Image preprocessing for OCR
│   ├── terminology/            # Terminology gateway client
│   │   ├── client.py           # Gateway interface
│   │   └── schemas.py          # Terminology schemas
│   ├── workers/                # Background jobs
│   │   ├── jobs.py             # Async job definitions
│   │   └── queue.py            # Redis-based job queue
│   └── main.py                 # FastAPI application entry point
├── prompts/                    # YAML prompt templates
│   ├── ocr.v1.yaml
│   ├── soap.v1.yaml
│   ├── entities.v1.yaml
│   ├── normalization.v1.yaml
│   ├── summary.v1.yaml
│   ├── gaps.v1.yaml
│   ├── translation.v1.yaml
│   └── fhir.v1.yaml
├── infra/                      # Infrastructure Configuration
│   ├── docker/                 # Dockerfiles
│   │   ├── api.Dockerfile
│   │   └── vllm.Dockerfile
│   ├── compose/                # Docker Compose
│   │   ├── docker-compose.yml
│   │   ├── deployment.sh
│   │   └── nginx.conf
│   └── oci/                    # OCI-specific configs
├── tests/                      # Test suite
│   ├── test_ocr_dependency.py
│   ├── test_workflows.py
│   ├── test_prompt_manager.py
│   ├── test_vllm_client.py
│   ├── test_context_store.py
│   ├── test_tenant_isolation.py
│   └── test_routes.py
├── docs/                       # Documentation
│   └── OCI_DEPLOYMENT.md
├── pyproject.toml              # Project configuration
├── alembic.ini                 # Alembic configuration
├── .env.example                # Environment template
└── README.md                   # This file
```

**Total Python Files:** ~72 modules  
**Lines of Code:** ~8,000+ lines (excluding tests)

---

## Data Flow & Workflows

### Request Processing Pipeline

Every API request follows this standardized flow:

```
1. HTTP Request → Nginx → FastAPI
2. Authentication & Authorization (JWT/API Key + RBAC)
3. Tenant Isolation Validation
4. Request Schema Validation (Pydantic)
5. Clinical Context Resolution (PostgreSQL + Redis)
6. OCR Dependency Resolution (if image provided)
   ├─ Check PostgreSQL for existing OCR
   ├─ Check Redis cache
   └─ Execute vLLM OCR prompt (if cache miss)
7. Prompt Rendering (Jinja2 + YAML template)
8. vLLM Chat Completion (OpenAI-compatible API)
9. JSON Parsing & Schema Validation
10. Context Update (PostgreSQL + Redis)
11. Inference Logging (Audit Trail)
12. Response Envelope Construction
13. HTTP Response
```

### Workflow Types

| Workflow | Input | Output | Requires OCR |
|----------|-------|--------|--------------|
| **OCR** | Image (base64/URI) | Text + entities + layout | No (is OCR) |
| **SOAP** | Text or Image | SOAP note (S/O/A/P) | Yes (if image) |
| **Entities** | Text or Image | Clinical entities list | Yes (if image) |
| **Normalization** | Text or entities | Normalized terms | Optional |
| **Summary** | Text/SOAP/entities | Clinical summary | Optional |
| **Gaps** | Text/SOAP/entities | Documentation gaps | Optional |
| **Translation** | Text + target language | Translated text | Yes (if image) |
| **SNOMED** | Text or entities | SNOMED CT candidates | Optional |
| **ICD** | Text/SOAP/entities | ICD-11 candidates | Optional |
| **FHIR** | Text/SOAP/entities/normalized | FHIR R4 resources | Optional |

### OCR Dependency Resolution

The OCR resolver implements a three-tier caching strategy:

```python
# Pseudocode from ocr_dependency.py
async def resolve(self, ...):
    # 1. Check in-memory local cache (process lifetime)
    if content_hash in self._local_cache:
        return cached_result, True
    
    # 2. Check PostgreSQL (persistent storage)
    existing = await db.ocr_results.get_by_document(tenant_id, document_id)
    if existing:
        return existing, True
    
    # 3. Check Redis (distributed cache, 30-day TTL)
    cached = await redis.get(f"ocr:{tenant_id}:{content_hash}")
    if cached:
        await persist_to_db(cached)  # Backfill DB
        return cached, True
    
    # 4. Execute OCR via vLLM
    ocr_result = await vllm.chat_completion(ocr_prompt)
    
    # 5. Persist to all layers
    await db.ocr_results.create(...)
    await redis.set(cache_key, ocr_result, ttl=30_days)
    self._local_cache[content_hash] = ocr_result
    
    return ocr_result, False
```

**Guarantee:** OCR is never executed twice for the same content hash unless explicitly forced via `force_rerun_ocr=true`.

---

## Quick Start - Local Development

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- NVIDIA GPU (optional, for vLLM - mock available for CPU)
- 8GB+ RAM, 4+ CPU cores

### 1. Clone and Setup

```bash
git clone <repo-url>
cd clinova-penthus-ai-engine
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

pip install -e ".[dev]"
```

### 2. Environment Configuration

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Start Infrastructure Services

```bash
# Start PostgreSQL, Redis, MinIO, mock services
docker compose -f infra/compose/docker-compose.local.yml up -d postgres redis minio terminology-mock

# Create MinIO bucket (first run only)
docker compose -f infra/compose/docker-compose.local.yml up minio-init
```

### 4. Database Migrations

```bash
alembic upgrade head
```

### 5. Start API Server

```bash
# Option A: Development mode with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Option B: Using Docker Compose (with mock vLLM for CPU)
docker compose -f infra/compose/docker-compose.local.yml --profile cpu up -d

# Option C: Using Docker Compose (with GPU vLLM)
docker compose -f infra/compose/docker-compose.local.yml --profile gpu up -d
```

### 6. Verify Installation

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/readiness
```

---

## API Endpoints

### Clinical AI Workflows

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/ocr` | Extract text and entities from documents |
| POST | `/api/v1/soap` | Generate SOAP notes |
| POST | `/api/v1/entities` | Extract clinical entities |
| POST | `/api/v1/normalization` | Normalize clinical terms |
| POST | `/api/v1/summary` | Generate clinical summaries |
| POST | `/api/v1/gaps` | Detect documentation gaps |
| POST | `/api/v1/translation` | Translate clinical text |
| POST | `/api/v1/snomed` | Map to SNOMED CT candidates |
| POST | `/api/v1/icd` | Map to ICD-11 candidates |
| POST | `/api/v1/fhir` | Generate FHIR R4 resources |

### Utility Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/encounters/{id}/context` | Get clinical context |
| GET | `/api/v1/documents/{id}/ocr` | Get OCR result |
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/readiness` | Readiness check |

---

## API Usage Examples

### Request Format

All endpoints accept the standard request envelope:

```json
{
  "tenant_id": "tenant_001",
  "encounter_id": "enc_001",
  "document_id": "doc_001",
  "patient_id": "pat_001",
  "image": "base64-encoded-image-or-object-storage-uri",
  "text": null,
  "language": "en",
  "metadata": {
    "source": "doctor_tablet",
    "specialty": "general_medicine"
  }
}
```

### OCR Example

```bash
curl -X POST http://localhost:8000/api/v1/ocr \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "tenant_id": "tenant_001",
    "encounter_id": "enc_001",
    "document_id": "doc_001",
    "image": "data:image/jpeg;base64,/9j/4AAQ...",
    "language": "en"
  }'
```

### SOAP Generation Example

```bash
curl -X POST http://localhost:8000/api/v1/soap \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "tenant_id": "tenant_001",
    "encounter_id": "enc_001",
    "text": "Patient has fever for 3 days and dry cough. No chest pain. Vitals: T 38.5C, HR 92, BP 120/80, SpO2 97%.",
    "language": "en"
  }'
```

### Response Format

```json
{
  "request_id": "req_001",
  "tenant_id": "tenant_001",
  "encounter_id": "enc_001",
  "document_id": "doc_001",
  "workflow": "soap",
  "model": {
    "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
    "prompt_version": "soap.v1",
    "model_version": "penthus-1.2-alpha-4b"
  },
  "result": {
    "subjective": "Patient reports fever for 3 days and dry cough.",
    "objective": "Temperature 38.5C, HR 92, BP 120/80, SpO2 97%.",
    "assessment": "Suspected upper respiratory infection.",
    "plan": "Rest, hydration, acetaminophen. Follow up in 3 days."
  },
  "warnings": [],
  "latency_ms": 1200,
  "ocr_reused": false
}
```

---

## Model Configuration

| Parameter | Value |
|-----------|-------|
| Model Repository | `Sebukpor/medical-document-understanding-v2-fixed` |
| Architecture | qwen3_5 |
| Parameters | ~4.54B |
| Serving Engine | vLLM |
| Internal Model Name | `penthus-1.2-alpha-4b` |
| Internal URL | `http://penthus-vllm:8000/v1` |
| Data Type | bfloat16 |
| Max Model Length | 8192 |
| GPU Memory Utilization | 90% |
| Prefix Caching | Enabled |

---

## OCR Dependency Resolution

OCR is the foundational layer. Every endpoint receiving an image resolves OCR first:

1. Check PostgreSQL for existing OCR result
2. If missing, check Redis cache
3. If missing, execute OCR prompt through vLLM
4. Persist OCR result to PostgreSQL
5. Cache OCR result in Redis (30-day TTL)
6. Update clinical context
7. Continue with requested workflow

**Guarantee**: OCR is never executed twice for the same content hash unless explicitly forced.

---

## Prompt Management

Prompts are stored as YAML files in `prompts/` and loaded at startup. Production supports both file bootstrapping and database-managed active versions.

Available prompts:
- `ocr.v1.yaml` - Document text extraction
- `soap.v1.yaml` - SOAP note generation
- `entities.v1.yaml` - Clinical entity extraction
- `normalization.v1.yaml` - Term normalization
- `summary.v1.yaml` - Clinical summarization
- `gaps.v1.yaml` - Documentation gap detection
- `translation.v1.yaml` - Clinical translation
- `fhir.v1.yaml` - FHIR resource generation

---

## Database Schema

### Core Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| **ocr_results** | Persisted OCR extractions | id, tenant_id, document_id, raw_text, entities (JSONB), layout (JSONB), language, confidence, created_at |
| **encounters** | Clinical encounter records | id, tenant_id, patient_id, encounter_date, specialty, status |
| **documents** | Document metadata | id, tenant_id, encounter_id, content_hash, mime_type, storage_uri, created_at |
| **inference_logs** | AI inference audit trail | id, tenant_id, encounter_id, workflow, model_version, prompt_version, latency_ms, tokens_used, created_at |
| **prompt_versions** | Managed prompt versioning | id, capability, version, system_prompt, user_template, parameters, is_active, created_at |

### Indexes

```sql
-- Performance indexes
CREATE INDEX idx_ocr_tenant_document ON ocr_results(tenant_id, document_id);
CREATE INDEX idx_ocr_content_hash ON ocr_results(content_hash);
CREATE INDEX idx_encounters_tenant_patient ON encounters(tenant_id, patient_id);
CREATE INDEX idx_documents_tenant_hash ON documents(tenant_id, content_hash);
CREATE INDEX idx_inference_logs_tenant_workflow ON inference_logs(tenant_id, workflow, created_at);
```

---

## Production Deployment - OCI MVP (Single Server)

For production MVP deployment on a single OCI Compute instance using Docker Compose:

### Quick Start

```bash
# 1. Prepare the server (first time only)
# Follow SERVER-PREPARATION.md for complete VM setup

# 2. Deploy the application
cd ~/penthus/infra/compose
./deployment.sh deploy

# 3. Verify health
./healthcheck.sh

# 4. Test API endpoints
curl http://localhost/api/v1/health
```

### Documentation

| Document | Purpose |
|----------|---------|
| **SERVER-PREPARATION.md** | VM preparation (clean old OCR, install Docker) |
| **DEPLOYMENT-OCI-MVP.md** | Complete deployment guide |
| **DEPLOYMENT-REPORT.md** | Architecture and cost analysis |

### Architecture

```
Internet → Nginx → FastAPI → PostgreSQL + Redis + vLLM
```

All services run on a single OCI VM via Docker Compose.

### Requirements

- OCI Compute VM (GPU recommended, CPU supported with mock mode)
- 50GB+ disk space
- Docker and Docker Compose
- HuggingFace token for model download

---

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_ocr_dependency.py -v

# Run with markers
pytest -m unit
pytest -m integration
```

### Test Coverage

| Test File | Coverage |
|-----------|----------|
| `test_ocr_dependency.py` | OCR deduplication, cache, single-execution |
| `test_workflows.py` | Workflow routing, dependency resolution |
| `test_prompt_manager.py` | Prompt loading, rendering, versions |
| `test_vllm_client.py` | Retry logic, timeout handling |
| `test_context_store.py` | Context persistence, merging |
| `test_tenant_isolation.py` | Multi-tenant isolation |
| `test_routes.py` | Endpoint routing, validation |

---

## Security

- **Authentication**: JWT tokens + API keys
- **Authorization**: RBAC with role-permission mapping
- **Tenant Isolation**: Enforced at all layers
- **PHI Protection**: Masked in logs, encrypted at rest
- **Audit Logging**: All PHI access tracked
- **Network**: vLLM internal-only, TLS 1.3
- **Secrets**: OCI Vault integration

### Roles

| Role | Permissions |
|------|-------------|
| `system_admin` | Full access |
| `clinical_admin` | Clinical workflows + admin |
| `physician` | All clinical workflows |
| `nurse` | Limited clinical workflows |
| `api_service` | Service-to-service |
| `read_only` | Context read only |

---

## Observability

### Logging & Tracing

The application provides comprehensive observability through:

- **Structured Logging**: All events logged in JSON format using structlog
- **OpenTelemetry Tracing**: Distributed traces across all workflow components
- **Audit Logging**: Complete audit trail for PHI access and AI inferences

### Key Logged Events

- Workflow execution (latency, tokens, outcomes)
- vLLM inference calls
- OCR cache hits/misses
- Terminology service lookups
- Validation failures
- Authentication and authorization events
- Tenant isolation enforcement

### Tracing Coverage

OpenTelemetry traces across:
- Gateway request
- Auth
- Context resolution
- OCR resolution
- Prompt rendering
- vLLM chat completion
- Schema validation
- Persistence
- Terminology lookup

### Log Aggregation

Logs can be forwarded to external log aggregation services (e.g., ELK Stack, Loki, Cloud Logging) via standard stdout/stderr streams.

---

## License

Proprietary - DAS MedHub

---

## Support

For support, contact: engineering@dasmedhub.com
