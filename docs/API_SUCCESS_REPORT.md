# Penthus API Deployment Success Report & Developer Guide

**Deployment Date:** June 19, 2026  
**Environment:** Production (OCI Compute Instance)  
**Version:** 1.2.0  
**Status:** ✅ Fully Operational

---

## Executive Summary

The Penthus Clinical AI Engine has been successfully deployed to production and is fully operational. All core services are running healthy and ready to process clinical AI workloads. The complete pipeline — from document OCR through SOAP note generation, entity extraction, terminology mapping (SNOMED CT + ICD-11), FHIR R4 resource generation, summarization, translation, and documentation gap detection — has been verified end-to-end.

Key achievements in this deployment cycle:
- OCR pipeline fixed to correctly parse model output and extract structured clinical data
- SNOMED CT integration live against `http://92.4.73.217:8100`
- ICD-11 integration live against the NIH Clinical Tables API
- FHIR enriched with real terminology codes from SNOMED/ICD-11 services
- Clinical context store accumulating state across all workflow steps
- Swagger UI live and accessible for developer testing
- All 10 clinical AI endpoints verified working end-to-end

---

## 1. Deployment Verification Results

### 1.1 Container Health Status

All five Docker containers are running with healthy status:

| Container | Image | Port Mapping | Status |
|-----------|-------|--------------|--------|
| `penthus-nginx` | nginx:alpine | 80→80, 443→443 | ✅ Healthy |
| `penthus-api` | penthus-api:local | 8000 (internal) | ✅ Healthy |
| `penthus-vllm` | vllm/vllm-openai:latest | 8001→8000 | ✅ Healthy |
| `penthus-postgres` | postgres:16-alpine | 5432 (internal) | ✅ Healthy |
| `penthus-redis` | redis:7-alpine | 6379 (internal) | ✅ Healthy |

### 1.2 Endpoint Readiness Checks

All readiness checks passed successfully:

```bash
$ curl http://localhost/api/v1/readiness
{
  "ready": true,
  "checks": {
    "api": true,
    "database": true,
    "cache": true,
    "vllm": true
  },
  "timestamp": "2026-06-19T11:17:40.736655+00:00"
}
```

### 1.3 Infrastructure Component Status

| Component | Check Command | Result |
|-----------|---------------|--------|
| **PostgreSQL** | `docker exec penthus-postgres pg_isready -U penthus` | ✅ Accepting connections |
| **Redis** | `docker exec penthus-redis redis-cli ping` | ✅ PONG |
| **vLLM Model Server** | `curl http://localhost:8001/health` | ✅ Model loaded |
| **API Health** | `curl http://localhost/api/v1/health` | ✅ Healthy |
| **SNOMED CT Service** | `curl http://92.4.73.217:8100/csnoserv/api/search/search?term=fever` | ✅ Responding |
| **ICD-11 Service** | `curl https://clinicaltables.nlm.nih.gov/api/icd11_codes/v3/search?terms=fever` | ✅ Responding |

### 1.4 Model Server Details

```json
{
  "object": "list",
  "data": [
    {
      "id": "penthus-1.2-alpha-4b",
      "object": "model",
      "owned_by": "vllm",
      "root": "Sebukpor/medical-document-understanding-v2-fixed",
      "max_model_len": 16384
    }
  ]
}
```

**Model Configuration:**
- **Model ID:** `penthus-1.2-alpha-4b`
- **Repository:** `Sebukpor/medical-document-understanding-v2-fixed`
- **Max Context Length:** 16,384 tokens
- **Serving Engine:** vLLM OpenAI-compatible API (latest)
- **GPU:** NVIDIA A10 (23GB VRAM), 9GB allocated to model

---

## 2. API Endpoints Reference

### 2.1 Base URLs

```
Production:    http://141.148.221.154/api/v1
Swagger UI:    http://141.148.221.154/docs
OpenAPI JSON:  http://141.148.221.154/openapi.json
Local Testing: http://localhost/api/v1
```

### 2.2 Authentication

All endpoints require an API key passed in the `X-API-Key` header:

```bash
-H "X-API-Key: penthus_test_key"
```

> **Note:** The test key `penthus_test_key` grants access to all tenants and all permissions. In production, each tenant will have their own scoped API key stored in the database.

### 2.3 Clinical AI Workflow Endpoints

| Method | Endpoint | Description | Primary Input | Output |
|--------|----------|-------------|---------------|--------|
| `POST` | `/ocr` | Extract text and structured entities from medical document images | Image (base64) | Raw text + entities + layout |
| `POST` | `/soap` | Generate SOAP notes from clinical text or images | Text or Image | Structured SOAP note |
| `POST` | `/entities` | Extract clinical entities (diagnoses, medications, procedures) | Text or Image | Typed entity list |
| `POST` | `/normalization` | Normalize clinical abbreviations and terms | Text or Image | Normalized term list |
| `POST` | `/summary` | Generate concise clinical summaries | Text or Image | Summary + key findings |
| `POST` | `/gaps` | Detect documentation gaps and quality issues | Text or Image | Gap list + completeness score |
| `POST` | `/translation` | Translate clinical text preserving medical accuracy | Text + target language | Translated text |
| `POST` | `/snomed` | Normalize terms → SNOMED CT code candidates via external service | Text or Image | Normalized terms + SNOMED codes |
| `POST` | `/icd` | Normalize terms → ICD-11 code candidates via NIH service | Text or Image | Normalized terms + ICD-11 codes |
| `POST` | `/fhir` | Generate FHIR R4 resources enriched with terminology codes | Text or Image | FHIR R4 resource bundle |

### 2.4 Utility Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/encounters/{encounter_id}/context?tenant_id={id}` | Retrieve accumulated clinical context for an encounter |
| `GET` | `/documents/{document_id}/ocr?tenant_id={id}` | Get cached OCR result for a specific document |
| `GET` | `/health` | Basic health check |
| `GET` | `/readiness` | Full readiness check (database, cache, vLLM) |
| `GET` | `/metrics` | Prometheus metrics for monitoring |

### 2.5 Terminology Service Architecture

SNOMED CT and ICD-11 endpoints use a two-step workflow:

```
Step 1 — AI Normalization:
  Clinical text → Penthus model → Normalized terms
  (e.g. "IOP" → "Intraocular Pressure", "SOB" → "Shortness of breath")

Step 2 — Terminology Gateway:
  Normalized terms → External service → Codes + candidates

  SNOMED CT:  http://92.4.73.217:8100/csnoserv/api/search/search
  ICD-11:     https://clinicaltables.nlm.nih.gov/api/icd11_codes/v3/search
```

> The AI model **does not assign codes directly**. Codes always come from the external terminology services. If a service is unavailable, normalized terms are returned with a warning and `terminology_service_available: false`.

### 2.6 FHIR Resource Generation

The FHIR endpoint generates complete FHIR R4 resource bundles using the full clinical context accumulated across workflow steps. When SNOMED/ICD-11 have been called previously for the same encounter, their codes are automatically injected into the FHIR resources:

```
OCR → SOAP → Entities → Normalization → SNOMED/ICD → FHIR
                                          ↑               ↑
                                     real codes     injected here
```

**Resources generated** (verified): Patient, Encounter, Condition, Observation, MedicationRequest, AllergyIntolerance, DiagnosticReport, Composition.

---

## 3. Database Schema & Data Model

### 3.1 Overview

PostgreSQL is the primary database for persistent storage. Redis handles caching and session management. All clinical data is stored with multi-tenant isolation enforced at the database level via foreign key constraints.

### 3.2 Core Tables

#### `tenants` Table
Stores tenant/organization information for multi-tenant isolation.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key, unique tenant identifier |
| `name` | TEXT | Human-readable tenant name |
| `status` | VARCHAR(20) | `active` or `inactive` |
| `settings` | JSONB | Tenant-specific configuration |
| `created_at` | TIMESTAMP WITH TIME ZONE | Creation timestamp |

#### `encounters` Table
Represents clinical encounters (patient visits, consultations, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `tenant_id` | UUID | Foreign key → `tenants.id` |
| `patient_id` | VARCHAR | Patient identifier from external EMR |
| `encounter_type` | VARCHAR | `inpatient`, `outpatient`, `emergency` |
| `started_at` | TIMESTAMP | Encounter start time |
| `department` | VARCHAR | Department name |
| `created_at` | TIMESTAMP | Record creation timestamp |

#### `documents` Table
Stores uploaded medical documents and their metadata.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `tenant_id` | UUID | Foreign key → `tenants.id` |
| `encounter_id` | UUID | Foreign key → `encounters.id` |
| `content_hash` | VARCHAR(64) | SHA-256 hash for deduplication |
| `object_uri` | TEXT | Object storage URI |
| `mime_type` | VARCHAR | MIME type (e.g. `image/jpeg`) |
| `language` | VARCHAR | ISO language code |
| `created_at` | TIMESTAMP | Upload timestamp |

#### `ocr_results` Table
Stores OCR extraction results with unique constraint per tenant+document.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `tenant_id` | UUID | Foreign key → `tenants.id` |
| `document_id` | UUID | Foreign key → `documents.id` |
| `raw_text` | TEXT | Extracted clinical text |
| `entities` | JSONB | Detected entities list |
| `layout` | JSONB | Page/block layout info |
| `language` | VARCHAR | Detected language |
| `confidence` | FLOAT | Extraction confidence (0.0–1.0) |
| `model_version` | VARCHAR | Model used |
| `prompt_version` | VARCHAR | Prompt version used |

**Unique constraint:** `uq_ocr_tenant_document` on `(tenant_id, document_id)` — OCR results are upserted on conflict.

#### `clinical_contexts` Table
Accumulates workflow state across all steps for an encounter.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `tenant_id` | UUID | Foreign key → `tenants.id` |
| `encounter_id` | UUID | Foreign key → `encounters.id` |
| `document_id` | UUID | Optional document reference |
| `state` | JSONB | Full accumulated context (ocr, soap, entities, snomed_candidates, icd_candidates, fhir_resources, workflow_state) |
| `version` | INTEGER | Optimistic concurrency version |
| `updated_at` | TIMESTAMP | Last update timestamp |
| `created_at` | TIMESTAMP | Creation timestamp |

**Context state structure:**
```json
{
  "ocr": { "raw_text": "..." },
  "soap": { "subjective": "...", "objective": "...", "assessment": "...", "plan": "..." },
  "entities": [...],
  "normalized_terms": [...],
  "snomed_candidates": [{ "code": "386661006", "display": "Fever", "source": "SNOMED_CT" }],
  "icd_candidates": [{ "code": "1A07", "display": "Typhoid fever", "source": "ICD11" }],
  "fhir_resources": [...],
  "workflow_state": {
    "ocr": { "completed": true, "timestamp": "..." },
    "soap": { "completed": true, "timestamp": "..." }
  }
}
```

### 3.3 Key Identifiers Explained

| Field | Description | Example | Usage |
|-------|-------------|---------|-------|
| `tenant_id` | Organization/customer identifier. All data is scoped per tenant. | `"550e8400-e29b-41d4-a716-446655440000"` | Required in all requests |
| `encounter_id` | Clinical encounter (visit/consultation). Groups all documents and notes for one visit. | `"550e8400-e29b-41d4-a716-446655440001"` | Required in all workflow requests |
| `document_id` | Specific uploaded document. Enables OCR result caching — same document won't be re-processed. | `"123e4567-e89b-12d3-a456-426614174000"` | Optional but strongly recommended |
| `patient_id` | External patient ID from your EMR/EHR. Passed through for your reference. | `"PAT-2026-001234"` | Optional |
| `request_id` | Auto-generated UUID per API request. Use for debugging and audit logs. | `"d4c1a71b2b265a88..."` | Returned in all responses |

### 3.4 Redis Cache Structure

| Key Pattern | Content | TTL |
|-------------|---------|-----|
| `ocr:{tenant_id}:{content_hash}` | Full OCR result JSON | 30 days |
| `context:{tenant_id}:{encounter_id}` | Clinical context state | 7 days |

---

## 4. Developer Guide: Making API Calls

### 4.1 Standard Request Envelope

All workflow endpoints accept a consistent request format:

```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
  "document_id": "123e4567-e89b-12d3-a456-426614174000",
  "patient_id": "PAT-2026-001234",
  "image": "data:image/jpeg;base64,/9j/4AAQ...",
  "text": "optional clinical text input",
  "language": "en",
  "target_language": "fr",
  "force_rerun_ocr": false,
  "metadata": {
    "source": "doctor_tablet",
    "specialty": "general_medicine"
  }
}
```

**Required fields:** `tenant_id`, `encounter_id`

**Optional fields:**

| Field | Description |
|-------|-------------|
| `document_id` | Enables OCR caching — same document won't be re-processed |
| `image` | Base64 encoded image (`data:image/jpeg;base64,...`) |
| `text` | Plain clinical text (alternative to image) |
| `language` | ISO 639-1 source language code (default: `"en"`) |
| `target_language` | Target language for translation endpoint |
| `force_rerun_ocr` | Set `true` to bypass OCR cache and re-run extraction |
| `metadata` | Additional context (source system, specialty, etc.) |

### 4.2 Standard Response Envelope

All endpoints return a consistent response format:

```json
{
  "request_id": "d4c1a71b2b265a88f93ab26720101d5f",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
  "document_id": "123e4567-e89b-12d3-a456-426614174000",
  "workflow": "soap",
  "model": {
    "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
    "prompt_version": "soap.v1",
    "model_version": "penthus-1.2-alpha-4b"
  },
  "result": { ... },
  "warnings": [],
  "latency_ms": 34200,
  "ocr_reused": true
}
```

> **`ocr_reused: true`** means the OCR result was served from cache (Redis or PostgreSQL) — no model inference was performed for OCR. Latency will be significantly lower.

---

## 5. Usage Examples

### 5.1 OCR — Extract Text from Medical Document

**Use Case:** Convert scanned medical documents, lab reports, prescriptions, or handwritten notes into structured clinical text.

```bash
curl -X POST http://141.148.221.154/api/v1/ocr \
  -H "Content-Type: application/json" \
  -H "X-API-Key: penthus_test_key" \
  -d '{
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
    "document_id": "123e4567-e89b-12d3-a456-426614174000",
    "image": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAA...",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "request_id": "d4c1a71b2b265a88f93ab26720101d5f",
  "workflow": "ocr",
  "result": {
    "raw_text": "\n--- PATIENT DEMOGRAPHICS ---\nAppointment Date: 26/06/2026\nDept: Ophthalmology\n\n--- CLINICAL NOTES ---\nExamination Findings: AR +0.75/-1.50 x 180, VA 6/12P. IOP 21.0 mmHg, 23.0.\n\n--- PRESCRIPTION ---\n - drug_dose: E19 combination BCS 00 | route: TEAR | frequency: 6TID | duration: 1 month\n\n--- DOCTOR DETAILS ---\nSignature Present: True\nName Stamp: DR. SANA ZAFAR, ASSISTANT PROFESSOR, DEPT OF OPHTHALMOLOGY",
    "entities": [
      {
        "type": "DOCTOR_NAME",
        "text": "DR. SANA ZAFAR, ASSISTANT PROFESSOR, DEPT OF OPHTHALMOLOGY",
        "confidence": 0.95
      }
    ],
    "layout": { "pages": 1, "blocks": [] },
    "language": "en",
    "confidence": 0.95
  },
  "latency_ms": 34200,
  "ocr_reused": false
}
```

---

### 5.2 SOAP Note Generation

**Use Case:** Generate structured SOAP notes from physician dictation, clinical text, or scanned documents.

```bash
curl -X POST http://141.148.221.154/api/v1/soap \
  -H "Content-Type: application/json" \
  -H "X-API-Key: penthus_test_key" \
  -d '{
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
    "text": "Patient has fever for 3 days and dry cough. Vitals: T 38.5C, HR 92, BP 120/80, SpO2 97%. Lungs clear on auscultation.",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "workflow": "soap",
  "result": {
    "data": {
      "subjective": "Patient reports fever for 3 days accompanied by dry cough. No chest pain.",
      "objective": "Temperature 38.5°C, Heart Rate 92 bpm, Blood Pressure 120/80 mmHg, SpO2 97% on room air. Lungs clear to auscultation bilaterally.",
      "assessment": "Upper respiratory infection, likely viral etiology.",
      "plan": "Supportive care with rest and hydration. Acetaminophen 650mg q6h PRN fever. Follow up in 3 days if symptoms persist."
    }
  },
  "latency_ms": 55321,
  "ocr_reused": false
}
```

---

### 5.3 Clinical Entity Extraction

**Use Case:** Extract structured clinical entities — diagnoses, medications, procedures, measurements — from unstructured text.

```bash
curl -X POST http://141.148.221.154/api/v1/entities \
  -H "Content-Type: application/json" \
  -H "X-API-Key: penthus_test_key" \
  -d '{
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
    "text": "Patient with Type 2 Diabetes on Metformin 500mg BID. Started Lisinopril 10mg for hypertension. IOP 21mmHg bilaterally.",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "workflow": "entities",
  "result": {
    "entities": [
      { "type": "CONDITION", "text": "Type 2 Diabetes", "confidence": 0.95 },
      { "type": "MEDICATION", "text": "Metformin", "dose": "500mg", "frequency": "BID", "confidence": 0.93 },
      { "type": "CONDITION", "text": "hypertension", "confidence": 0.92 },
      { "type": "MEDICATION", "text": "Lisinopril", "dose": "10mg", "confidence": 0.94 },
      { "type": "MEASUREMENT", "text": "IOP 21mmHg", "confidence": 0.97 }
    ]
  },
  "latency_ms": 12400,
  "ocr_reused": false
}
```

---

### 5.4 SNOMED CT Mapping

**Use Case:** Map clinical terms to SNOMED CT concepts for interoperability and coding.

```bash
curl -X POST http://141.148.221.154/api/v1/snomed \
  -H "Content-Type: application/json" \
  -H "X-API-Key: penthus_test_key" \
  -d '{
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
    "text": "patient has fever and refractive error",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "workflow": "snomed",
  "result": {
    "system": "SNOMED_CT",
    "query_terms": ["fever", "refractive error"],
    "normalized_terms": [
      { "source_text": "fever", "normalized_text": "fever", "category": "symptom", "confidence": 0.95 },
      { "source_text": "refractive error", "normalized_text": "refractive error", "category": "finding", "confidence": 0.95 }
    ],
    "candidates": [
      { "code": "248425001", "display": "Pyrexia", "score": 0.9, "source": "SNOMED_CT" },
      { "code": "386661006", "display": "Fever", "score": 0.9, "source": "SNOMED_CT" },
      { "code": "39021009", "display": "Refractive error", "score": 0.9, "source": "SNOMED_CT" }
    ],
    "ai_normalized": true,
    "terminology_service_available": true,
    "warning": null
  },
  "latency_ms": 16800,
  "ocr_reused": false
}
```

---

### 5.5 ICD-11 Coding

**Use Case:** Map clinical diagnoses to ICD-11 codes via the NIH Clinical Tables service.

```bash
curl -X POST http://141.148.221.154/api/v1/icd \
  -H "Content-Type: application/json" \
  -H "X-API-Key: penthus_test_key" \
  -d '{
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
    "text": "patient has fever and refractive error",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "workflow": "icd",
  "result": {
    "system": "ICD11",
    "query_terms": ["fever", "refractive error of eye"],
    "normalized_terms": [
      { "source_text": "fever", "normalized_text": "fever" },
      { "source_text": "refractive error", "normalized_text": "refractive error of eye" }
    ],
    "candidates": [
      { "code": "1A07", "display": "Typhoid fever", "score": 0.9, "source": "ICD11" },
      { "code": "9D00", "display": "Refractive error of eye", "score": 0.9, "source": "ICD11" }
    ],
    "ai_normalized": true,
    "terminology_service_available": true,
    "warning": null
  },
  "latency_ms": 15300,
  "ocr_reused": false
}
```

---

### 5.6 FHIR R4 Resource Generation

**Use Case:** Generate structured FHIR R4 resources from clinical encounter data. When SNOMED/ICD-11 have been called first for the same encounter, their codes are automatically embedded in the resources.

```bash
curl -X POST http://141.148.221.154/api/v1/fhir \
  -H "Content-Type: application/json" \
  -H "X-API-Key: penthus_test_key" \
  -d '{
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
    "text": "Patient has fever and refractive error. Prescribed eye drops.",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "workflow": "fhir",
  "result": {
    "resources": [
      { "resourceType": "Patient", "resource": { "resourceType": "Patient", "id": "patient-001" } },
      { "resourceType": "Encounter", "resource": { "resourceType": "Encounter", "status": "finished", "class": { "code": "AMB" } } },
      { "resourceType": "Condition", "resource": { "resourceType": "Condition", "code": { "coding": [{ "system": "http://snomed.info/sct", "code": "386661006", "display": "Fever" }] } } },
      { "resourceType": "Condition", "resource": { "resourceType": "Condition", "code": { "coding": [{ "system": "http://snomed.info/sct", "code": "39021009", "display": "Refractive error" }] } } },
      { "resourceType": "Observation", "resource": { "resourceType": "Observation", "status": "final" } },
      { "resourceType": "MedicationRequest", "resource": { "resourceType": "MedicationRequest", "status": "active" } },
      { "resourceType": "DiagnosticReport", "resource": { "resourceType": "DiagnosticReport", "status": "final" } }
    ]
  },
  "latency_ms": 68833,
  "ocr_reused": false
}
```

---

### 5.7 Documentation Gap Detection

**Use Case:** Identify missing elements in clinical documentation for quality improvement and compliance.

```bash
curl -X POST http://141.148.221.154/api/v1/gaps \
  -H "Content-Type: application/json" \
  -H "X-API-Key: penthus_test_key" \
  -d '{
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
    "text": "Patient came in with chest pain. Did EKG. Gave aspirin. Sent home.",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "workflow": "gaps",
  "result": {
    "gaps": [
      { "category": "demographics", "description": "Patient name not documented", "priority": "high" },
      { "category": "history", "description": "Chief complaint characterization missing (onset, duration, quality)", "priority": "high" },
      { "category": "vitals", "description": "Vital signs not recorded", "priority": "high" },
      { "category": "assessment", "description": "Differential diagnosis not stated", "priority": "medium" },
      { "category": "plan", "description": "Follow-up instructions not specified", "priority": "medium" }
    ],
    "completeness_score": 0.35,
    "recommendations": [
      "Add patient demographics",
      "Document full HPI",
      "Record vital signs"
    ]
  },
  "latency_ms": 11200
}
```

---

### 5.8 Clinical Translation

**Use Case:** Translate clinical text between languages while preserving medical terminology accuracy.

```bash
curl -X POST http://141.148.221.154/api/v1/translation \
  -H "Content-Type: application/json" \
  -H "X-API-Key: penthus_test_key" \
  -d '{
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
    "text": "Patient presents with acute abdominal pain, nausea, and vomiting.",
    "language": "en",
    "target_language": "fr"
  }'
```

**Example Response:**
```json
{
  "workflow": "translation",
  "result": {
    "translated_text": "Le patient présente des douleurs abdominales aiguës, des nausées et des vomissements.",
    "source_language": "en",
    "target_language": "fr",
    "confidence": 0.93
  },
  "latency_ms": 18900
}
```

---

### 5.9 Retrieve Clinical Context

**Use Case:** Retrieve the full accumulated context for an encounter after running multiple workflows.

```bash
curl "http://141.148.221.154/api/v1/encounters/550e8400-e29b-41d4-a716-446655440001/context?tenant_id=550e8400-e29b-41d4-a716-446655440000&document_id=123e4567-e89b-12d3-a456-426614174000" \
  -H "X-API-Key: penthus_test_key"
```

**Example Response:**
```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "encounter_id": "550e8400-e29b-41d4-a716-446655440001",
  "context": {
    "ocr": { "raw_text": "--- PATIENT DEMOGRAPHICS ---\n..." },
    "soap": { "subjective": "...", "objective": "...", "assessment": "...", "plan": "..." },
    "snomed_candidates": [{ "code": "386661006", "display": "Fever", "source": "SNOMED_CT" }],
    "icd_candidates": [{ "code": "1A07", "display": "Typhoid fever", "source": "ICD11" }],
    "fhir_resources": [...],
    "workflow_state": {
      "ocr": { "completed": true },
      "soap": { "completed": true },
      "snomed": { "completed": true },
      "icd": { "completed": true },
      "fhir": { "completed": true }
    }
  }
}
```

---

## 6. Python Client Example

### 6.1 Installation

```bash
pip install httpx
```

### 6.2 Full Client Code

```python
import httpx
import base64
import asyncio
from typing import Optional, Dict, Any


class PenthusClient:
    """Async client for Penthus Clinical AI API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        }

    async def ocr_document(
        self,
        image_path: str,
        tenant_id: str,
        encounter_id: str,
        document_id: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Perform OCR on a document image."""
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        payload = {
            "tenant_id": tenant_id,
            "encounter_id": encounter_id,
            "document_id": document_id,
            "image": f"data:image/jpeg;base64,{image_data}",
            "language": language,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/ocr",
                json=payload,
                headers=self.headers,
                timeout=120.0,
            )
            response.raise_for_status()
            return response.json()

    async def generate_soap(
        self,
        tenant_id: str,
        encounter_id: str,
        text: Optional[str] = None,
        image_path: Optional[str] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Generate SOAP note from clinical text or image."""
        payload = {
            "tenant_id": tenant_id,
            "encounter_id": encounter_id,
            "language": language,
        }
        if text:
            payload["text"] = text
        if image_path:
            with open(image_path, "rb") as f:
                payload["image"] = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/soap",
                json=payload,
                headers=self.headers,
                timeout=120.0,
            )
            response.raise_for_status()
            return response.json()

    async def map_snomed(
        self, tenant_id: str, encounter_id: str, text: str
    ) -> Dict[str, Any]:
        """Map clinical terms to SNOMED CT codes."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/snomed",
                json={"tenant_id": tenant_id, "encounter_id": encounter_id, "text": text},
                headers=self.headers,
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()

    async def map_icd(
        self, tenant_id: str, encounter_id: str, text: str
    ) -> Dict[str, Any]:
        """Map clinical terms to ICD-11 codes."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/icd",
                json={"tenant_id": tenant_id, "encounter_id": encounter_id, "text": text},
                headers=self.headers,
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()

    async def generate_fhir(
        self, tenant_id: str, encounter_id: str, text: str
    ) -> Dict[str, Any]:
        """Generate FHIR R4 resources from clinical data."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/fhir",
                json={"tenant_id": tenant_id, "encounter_id": encounter_id, "text": text},
                headers=self.headers,
                timeout=120.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_context(
        self, tenant_id: str, encounter_id: str, document_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve accumulated clinical context for an encounter."""
        url = f"{self.base_url}/api/v1/encounters/{encounter_id}/context?tenant_id={tenant_id}"
        if document_id:
            url += f"&document_id={document_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, timeout=30.0)
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> Dict[str, Any]:
        """Check API health status."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/health", headers=self.headers, timeout=5.0
            )
            response.raise_for_status()
            return response.json()


# Full pipeline example
async def run_full_pipeline():
    client = PenthusClient(
        base_url="http://141.148.221.154",
        api_key="penthus_test_key",
    )

    tenant_id = "550e8400-e29b-41d4-a716-446655440000"
    encounter_id = "550e8400-e29b-41d4-a716-446655440001"
    document_id = "123e4567-e89b-12d3-a456-426614174000"

    # 1. OCR
    print("Running OCR...")
    ocr = await client.ocr_document("document.jpg", tenant_id, encounter_id, document_id)
    print(f"OCR confidence: {ocr['result']['confidence']}")

    # 2. SOAP
    print("Generating SOAP...")
    soap = await client.generate_soap(tenant_id, encounter_id, image_path="document.jpg")
    print(f"Assessment: {soap['result'].get('data', {}).get('assessment', '')[:100]}")

    # 3. SNOMED
    print("Mapping SNOMED CT...")
    snomed = await client.map_snomed(tenant_id, encounter_id, ocr["result"]["raw_text"])
    print(f"SNOMED candidates: {len(snomed['result']['candidates'])}")

    # 4. ICD-11
    print("Mapping ICD-11...")
    icd = await client.map_icd(tenant_id, encounter_id, ocr["result"]["raw_text"])
    print(f"ICD-11 candidates: {len(icd['result']['candidates'])}")

    # 5. FHIR (enriched with SNOMED + ICD context)
    print("Generating FHIR resources...")
    fhir = await client.generate_fhir(tenant_id, encounter_id, ocr["result"]["raw_text"])
    print(f"FHIR resources generated: {len(fhir['result']['resources'])}")

    # 6. Get full context
    ctx = await client.get_context(tenant_id, encounter_id, document_id)
    print(f"Context keys: {list(ctx['context'].keys())}")


asyncio.run(run_full_pipeline())
```

---

## 7. Error Handling

### 7.1 Common HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| `200` | Success | Process response normally |
| `400` | Bad Request | Check request payload format and required fields |
| `401` | Unauthorized | Verify API key is present and correct |
| `403` | Forbidden | Check tenant_id matches your API key's tenant |
| `404` | Not Found | Verify endpoint URL and resource existence |
| `422` | Validation Error | Check field types and required fields |
| `500` | Internal Server Error | Check server logs; contact support |
| `503` | Service Unavailable | vLLM model server still loading; retry in 60s |
| `504` | Gateway Timeout | Request exceeded 120s; use shorter input or retry |

### 7.2 Error Response Format

```json
{
  "error": {
    "code": "vllm_timeout",
    "message": "vLLM request timed out after 120s",
    "details": {
      "timeout_seconds": 120,
      "elapsed_ms": 120002
    },
    "request_id": "bb4ea28f713eb4879ccdd1308945ef5a"
  }
}
```

### 7.3 Terminology Service Unavailable

If SNOMED or ICD-11 external services are unreachable, the API returns a graceful degraded response:

```json
{
  "result": {
    "normalized_terms": [...],
    "candidates": [],
    "terminology_service_available": false,
    "warning": "Terminology gateway unavailable: Cannot reach SNOMED CT service. Returning normalized terms only."
  },
  "warnings": ["Terminology gateway unavailable: ..."]
}
```

---

## 8. Best Practices

### 8.1 Performance Optimization

1. **Always provide `document_id`** when sending images — OCR results are cached in Redis (30 days) and PostgreSQL. Subsequent calls with the same `document_id` return instantly without re-running the model.
2. **Pipeline workflows in order**: OCR → SOAP → Entities → SNOMED/ICD → FHIR. Each step enriches the encounter context used by subsequent steps.
3. **Use `text` input for text-only workflows** (SOAP, entities, gaps, translation) — no OCR overhead.
4. **Use `force_rerun_ocr: true`** only when the document has genuinely changed.

### 8.2 Recommended Pipeline Order

```
1. /ocr          → Extract text from document image (cached by document_id)
2. /soap         → Generate SOAP note from OCR text
3. /entities     → Extract clinical entities
4. /normalization → Normalize clinical terms
5. /snomed       → Map to SNOMED CT codes (stored in encounter context)
6. /icd          → Map to ICD-11 codes (stored in encounter context)
7. /fhir         → Generate FHIR resources (enriched with SNOMED + ICD codes)
8. /summary      → Generate clinical summary
9. /gaps         → Detect documentation gaps
```

### 8.3 Security Recommendations

1. **API Key Management**: Store keys in environment variables or a secrets manager, never in source code
2. **Tenant Isolation**: Always pass the correct `tenant_id` — the API enforces strict tenant isolation
3. **HTTPS**: Use HTTPS in production (configure SSL certificates in nginx)
4. **PHI Handling**: Encrypt sensitive data in transit and at rest

### 8.4 Retry Strategy

```python
import asyncio
import random
from httpx import RequestError, HTTPStatusError

async def retry_with_backoff(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except (RequestError, HTTPStatusError) as e:
            if attempt == max_retries - 1:
                raise
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            print(f"Attempt {attempt + 1} failed, retrying in {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)
```

---

## 9. Monitoring & Observability

### 9.1 Health Endpoints

```bash
# Basic health check
curl http://141.148.221.154/api/v1/health

# Full readiness check (database, cache, vLLM)
curl http://141.148.221.154/api/v1/readiness

# Prometheus metrics
curl http://141.148.221.154/api/v1/metrics
```

### 9.2 Key Metrics to Track

| Metric | Source | Description |
|--------|--------|-------------|
| `latency_ms` | Response field | End-to-end request latency |
| `ocr_reused` | Response field | `true` = cache hit, no model inference |
| `terminology_service_available` | SNOMED/ICD result | External service health |
| `confidence` | OCR result | OCR extraction quality |
| HTTP 5xx rate | nginx/metrics | Server error rate |
| GPU memory | `nvidia-smi` | vLLM memory utilization |

### 9.3 Docker Container Management

```bash
# Check all containers
docker ps

# Restart API only (preserves vLLM model in GPU memory)
cd /home/ubuntu/clinova-penthus-ai-engine/infra/compose
docker compose restart api

# Full stack restart
docker compose down && docker compose up -d

# View logs
docker logs penthus-api --tail 50 -f
docker logs penthus-vllm --tail 20 -f

# Check GPU memory
nvidia-smi
```

> ⚠️ **Important:** vLLM takes 3–5 minutes to load the model after a restart. The API will return 503 during this time. Monitor `curl http://localhost:8001/health` and wait for `200` before sending requests.

---

## 10. Support & Resources

| Resource | Location |
|----------|----------|
| **Interactive API Docs (Swagger UI)** | `http://141.148.221.154/docs` |
| **OpenAPI Schema** | `http://141.148.221.154/openapi.json` |
| **GitHub Repository** | `https://github.com/Sebukpor/clinova-penthus-ai-engine` |
| **Test API Key** | `penthus_test_key` |
| **Test Tenant ID** | `550e8400-e29b-41d4-a716-446655440000` |
| **Test Encounter ID** | `550e8400-e29b-41d4-a716-446655440001` |
| **Test Document ID** | `123e4567-e89b-12d3-a456-426614174000` |

---

## 11. Quick Reference Card

```bash
BASE="http://141.148.221.154/api/v1"
KEY="penthus_test_key"
TENANT="550e8400-e29b-41d4-a716-446655440000"
ENC="550e8400-e29b-41d4-a716-446655440001"
DOC="123e4567-e89b-12d3-a456-426614174000"

# Health
curl $BASE/health

# OCR (with image)
curl -X POST $BASE/ocr -H "X-API-Key: $KEY" \
  -d "{\"tenant_id\":\"$TENANT\",\"encounter_id\":\"$ENC\",\"document_id\":\"$DOC\",\"image\":\"data:image/jpeg;base64,...\"}"

# SOAP (text input)
curl -X POST $BASE/soap -H "X-API-Key: $KEY" \
  -d "{\"tenant_id\":\"$TENANT\",\"encounter_id\":\"$ENC\",\"text\":\"Patient has fever\"}"

# SNOMED
curl -X POST $BASE/snomed -H "X-API-Key: $KEY" \
  -d "{\"tenant_id\":\"$TENANT\",\"encounter_id\":\"$ENC\",\"text\":\"fever and cough\"}"

# ICD-11
curl -X POST $BASE/icd -H "X-API-Key: $KEY" \
  -d "{\"tenant_id\":\"$TENANT\",\"encounter_id\":\"$ENC\",\"text\":\"fever and cough\"}"

# FHIR
curl -X POST $BASE/fhir -H "X-API-Key: $KEY" \
  -d "{\"tenant_id\":\"$TENANT\",\"encounter_id\":\"$ENC\",\"text\":\"Patient has fever\"}"

# Get encounter context
curl "$BASE/encounters/$ENC/context?tenant_id=$TENANT&document_id=$DOC" -H "X-API-Key: $KEY"

# Get cached OCR
curl "$BASE/documents/$DOC/ocr?tenant_id=$TENANT" -H "X-API-Key: $KEY"
```

---

**Document Version:** 2.0  
**Last Updated:** June 19, 2026  
**Maintained By:** DAS medhub Engineering Team
