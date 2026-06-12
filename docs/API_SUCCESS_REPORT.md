# Penthus API Deployment Success Report & Developer Guide

**Deployment Date:** June 11, 2026  
**Environment:** Production (OCI Compute Instance)  
**Version:** 1.2.0  
**Status:** ✅ Fully Operational

---

## Executive Summary

The Penthus Clinical AI Engine has been successfully deployed to production. All core services are running healthy and ready to process clinical AI workloads including OCR, SOAP note generation, entity extraction, summarization, translation, FHIR extraction, and documentation gap detection.

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
# API Readiness Check
$ curl http://localhost/api/v1/readiness
{
  "ready": true,
  "checks": {
    "api": true,
    "database": true,
    "cache": true,
    "vllm": true
  },
  "timestamp": "2026-06-11T11:17:40.736655+00:00"
}
```

### 1.3 Infrastructure Component Status

| Component | Check Command | Result |
|-----------|---------------|--------|
| **PostgreSQL** | `docker exec penthus-postgres pg_isready -U postgres` | ✅ Accepting connections |
| **Redis** | `docker exec penthus-redis redis-cli ping` | ✅ PONG |
| **vLLM Model Server** | `curl http://localhost:8001/v1/models` | ✅ Model loaded |
| **API Health** | `curl http://localhost/api/v1/health` | ✅ Healthy |

### 1.4 Model Server Details

```json
{
  "object": "list",
  "data": [
    {
      "id": "penthus-1.2-alpha-4b",
      "object": "model",
      "created": 1781176698,
      "owned_by": "vllm",
      "root": "Sebukpor/medical-document-understanding-v2-fixed",
      "parent": null,
      "max_model_len": 8192
    }
  ]
}
```

**Model Configuration:**
- **Model ID:** `penthus-1.2-alpha-4b`
- **Repository:** `Sebukpor/medical-document-understanding-v2-fixed`
- **Max Context Length:** 8192 tokens
- **Serving Engine:** vLLM OpenAI-compatible API

---

## 2. API Endpoints Reference

### 2.1 Base URL

```
Production: http://<your-server-ip>/api/v1
Local Testing: http://localhost/api/v1
```

### 2.2 Clinical AI Workflow Endpoints

| Method | Endpoint | Description | Input | Output |
|--------|----------|-------------|-------|--------|
| `POST` | `/ocr` | Extract text and structured entities from medical documents | Image (base64 or URI) | Raw text + detected entities |
| `POST` | `/soap` | Generate SOAP notes from clinical text | Clinical text | Structured SOAP note |
| `POST` | `/entities` | Extract clinical entities (problems, medications, procedures) | Clinical text | List of entities with types |
| `POST` | `/normalization` | Normalize clinical terms to standard vocabulary | Clinical term | Normalized term + synonyms |
| `POST` | `/summary` | Generate concise clinical summaries | Long clinical text | Summarized text |
| `POST` | `/gaps` | Detect documentation gaps in clinical notes | Clinical note | List of missing elements |
| `POST` | `/translation` | Translate clinical text between languages | Text + target language | Translated text |
| `POST` | `/snomed` | Map clinical concepts to SNOMED CT codes | Clinical concept | SNOMED CT candidates |
| `POST` | `/icd` | Map diagnoses to ICD-11 codes | Diagnosis description | ICD-11 code candidates |
| `POST` | `/fhir` | Generate FHIR R4 resources from clinical data | Clinical data | FHIR JSON resource |

### 2.3 Utility Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/encounters/{id}/context` | Retrieve clinical context for an encounter |
| `GET` | `/documents/{id}/ocr` | Get cached OCR result for a document |
| `GET` | `/health` | Health check with component status |
| `GET` | `/readiness` | Readiness check for load balancer |
| `GET` | `/metrics` | Prometheus metrics endpoint |

---

## 3. Database Schema & Data Model

### 3.1 Overview

The Penthus API uses PostgreSQL as the primary database for persistent storage and Redis for caching and session management. All clinical data is stored with multi-tenant isolation.

### 3.2 Core Tables

#### `tenants` Table
Stores tenant/organization information for multi-tenant isolation.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key, unique tenant identifier |
| `name` | VARCHAR(255) | Human-readable tenant name (e.g., "Acme Hospital") |
| `slug` | VARCHAR(50) | URL-friendly identifier (e.g., "acme-hospital") |
| `api_key` | VARCHAR(255) | API key for authentication |
| `created_at` | TIMESTAMP | Tenant creation timestamp |
| `is_active` | BOOLEAN | Whether tenant is active |

**Example:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Acme Medical Center",
  "slug": "acme-medical",
  "api_key": "sk_live_abc123xyz789",
  "created_at": "2026-01-15T10:30:00Z",
  "is_active": true
}
```

#### `encounters` Table
Represents clinical encounters (patient visits, consultations, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key, unique encounter identifier |
| `tenant_id` | UUID | Foreign key to `tenants.id` |
| `patient_id` | VARCHAR(100) | Patient identifier (from external EMR) |
| `encounter_number` | VARCHAR(50) | Encounter number (from external EMR) |
| `encounter_type` | VARCHAR(50) | Type: "inpatient", "outpatient", "emergency" |
| `started_at` | TIMESTAMP | Encounter start time |
| `ended_at` | TIMESTAMP | Encounter end time |
| `department` | VARCHAR(100) | Department where encounter occurred |
| `provider_id` | VARCHAR(100) | Attending provider identifier |
| `created_at` | TIMESTAMP | Record creation timestamp |
| `updated_at` | TIMESTAMP | Last update timestamp |

**Example:**
```json
{
  "id": "660f9500-f39c-52e5-b827-557766550000",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "patient_id": "PAT-2026-001234",
  "encounter_number": "ENC-20260611-0042",
  "encounter_type": "outpatient",
  "started_at": "2026-06-11T09:00:00Z",
  "ended_at": null,
  "department": "General Medicine",
  "provider_id": "DR-5678",
  "created_at": "2026-06-11T09:00:00Z",
  "updated_at": "2026-06-11T09:00:00Z"
}
```

#### `documents` Table
Stores uploaded medical documents and OCR results.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key, unique document identifier |
| `tenant_id` | UUID | Foreign key to `tenants.id` |
| `encounter_id` | UUID | Foreign key to `encounters.id` |
| `document_type` | VARCHAR(50) | Type: "lab_report", "prescription", "discharge_summary" |
| `file_name` | VARCHAR(255) | Original file name |
| `storage_uri` | VARCHAR(500) | Object storage URI (e.g., s3://bucket/path) |
| `mime_type` | VARCHAR(50) | MIME type (e.g., "image/jpeg", "application/pdf") |
| `ocr_status` | VARCHAR(20) | Status: "pending", "processing", "completed", "failed" |
| `ocr_result` | JSONB | Extracted text and entities from OCR |
| `page_count` | INTEGER | Number of pages |
| `language` | VARCHAR(10) | Detected language code |
| `confidence_score` | FLOAT | OCR confidence score (0.0-1.0) |
| `created_at` | TIMESTAMP | Upload timestamp |
| `processed_at` | TIMESTAMP | OCR completion timestamp |

**Example:**
```json
{
  "id": "770fa600-g4ad-63f6-c938-668877660000",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "encounter_id": "660f9500-f39c-52e5-b827-557766550000",
  "document_type": "lab_report",
  "file_name": "blood_test_results.pdf",
  "storage_uri": "s3://penthus-docs/tenant_001/lab_report_001.pdf",
  "mime_type": "application/pdf",
  "ocr_status": "completed",
  "ocr_result": {
    "raw_text": "LABORATORY RESULTS\nPatient: John Doe\n...",
    "entities": [...],
    "confidence": 0.97
  },
  "page_count": 2,
  "language": "en",
  "confidence_score": 0.97,
  "created_at": "2026-06-11T09:15:00Z",
  "processed_at": "2026-06-11T09:15:45Z"
}
```

#### `clinical_notes` Table
Stores generated clinical notes (SOAP, summaries, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key, unique note identifier |
| `tenant_id` | UUID | Foreign key to `tenants.id` |
| `encounter_id` | UUID | Foreign key to `encounters.id` |
| `document_id` | UUID | Foreign key to `documents.id` (optional) |
| `note_type` | VARCHAR(50) | Type: "soap", "summary", "discharge" |
| `content` | JSONB | Structured note content |
| `raw_text` | TEXT | Plain text version |
| `model_version` | VARCHAR(100) | AI model version used |
| `prompt_version` | VARCHAR(50) | Prompt template version |
| `status` | VARCHAR(20) | Status: "draft", "finalized", "archived" |
| `created_by` | VARCHAR(100) | Creator identifier (user or system) |
| `created_at` | TIMESTAMP | Creation timestamp |
| `metadata` | JSONB | Additional metadata |

**Example:**
```json
{
  "id": "880gb700-h5be-74g7-d049-779988770000",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "encounter_id": "660f9500-f39c-52e5-b827-557766550000",
  "note_type": "soap",
  "content": {
    "subjective": "Patient reports fever for 3 days...",
    "objective": "Temperature 38.5°C...",
    "assessment": "Upper respiratory infection...",
    "plan": "1. Supportive care..."
  },
  "raw_text": "SOAP NOTE\nSubjective: Patient reports...",
  "model_version": "penthus-1.2-alpha-4b",
  "prompt_version": "soap.v1",
  "status": "draft",
  "created_by": "system",
  "created_at": "2026-06-11T09:20:00Z",
  "metadata": {
    "latency_ms": 1450,
    "request_id": "req_soap_001"
  }
}
```

#### `audit_logs` Table
Tracks all API requests and data modifications for compliance.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `tenant_id` | UUID | Foreign key to `tenants.id` |
| `request_id` | VARCHAR(100) | Unique request identifier |
| `endpoint` | VARCHAR(255) | API endpoint called |
| `method` | VARCHAR(10) | HTTP method |
| `user_id` | VARCHAR(100) | User who made the request |
| `ip_address` | INET | Client IP address |
| `request_payload` | JSONB | Request body (sanitized) |
| `response_status` | INTEGER | HTTP response status code |
| `latency_ms` | INTEGER | Request latency in milliseconds |
| `created_at` | TIMESTAMP | Request timestamp |

### 3.3 Field Definitions

#### Key Identifiers Explained

| Field | Description | Example | Usage |
|-------|-------------|---------|-------|
| `tenant_id` | **Multi-tenant isolation identifier**. Uniquely identifies the organization/customer. All data is scoped to a tenant for security and data isolation. | `"tenant_001"` or UUID | Required in all API requests |
| `encounter_id` | **Clinical encounter identifier**. Represents a single patient visit, consultation, or hospital stay. Groups all documents and notes for that visit. | `"enc_20260611_0042"` or UUID | Required for workflow endpoints |
| `document_id` | **Document identifier**. Unique ID for an uploaded medical document (lab report, prescription, etc.). Used for OCR caching and retrieval. | `"doc_lab_001"` or UUID | Optional; enables OCR result caching |
| `patient_id` | **Patient identifier**. External patient ID from your EMR/EHR system. Not used internally by Penthus but passed through for context. | `"PAT-2026-001234"` | Optional; for your reference |
| `request_id` | **Request trace identifier**. Auto-generated UUID for each API request. Used for debugging, audit logs, and tracing. | `"req_abc123xyz"` | Returned in all responses |

#### Metadata Fields

| Field | Description | Example Values |
|-------|-------------|----------------|
| `source` | Origin of the request | `"doctor_tablet"`, `"web_portal"`, `"mobile_app"`, `"integration"` |
| `specialty` | Medical specialty context | `"general_medicine"`, `"cardiology"`, `"pediatrics"` |
| `priority` | Processing priority | `"routine"`, `"urgent"`, `"stat"` |
| `locale` | Regional settings | `"en-US"`, `"en-GB"`, `"es-MX"` |

### 3.4 Redis Cache Structure

Redis is used for:
- **OCR Result Caching**: Cached by `document_id` to avoid re-processing
- **Session Storage**: Temporary session data for async workflows
- **Rate Limiting**: Token bucket counters per tenant/API key

**Cache Keys:**
```
ocr:{document_id}          -> JSON (OCR results, TTL: 7 days)
session:{encounter_id}     -> JSON (context data, TTL: 24 hours)
ratelimit:{tenant_id}      -> Integer (token count, TTL: 1 minute)
```

---

## 4. Developer Guide: Making API Calls

### 4.1 Standard Request Envelope

All workflow endpoints accept a consistent request format:

```json
{
  "tenant_id": "tenant_001",
  "encounter_id": "enc_001",
  "document_id": "doc_001",
  "patient_id": "pat_001",
  "image": "base64-encoded-image-or-object-storage-uri",
  "text": "optional clinical text",
  "language": "en",
  "metadata": {
    "source": "doctor_tablet",
    "specialty": "general_medicine"
  }
}
```

**Required Fields:**
- `tenant_id` - Multi-tenant isolation identifier
- `encounter_id` - Clinical encounter identifier

**Optional Fields:**
- `document_id` - Document reference for OCR caching
- `patient_id` - Patient identifier
- `image` - Base64-encoded image or object storage URI
- `text` - Plain clinical text (for text-based workflows)
- `language` - ISO 639-1 language code (default: "en")
- `metadata` - Additional context metadata

### 4.2 Standard Response Envelope

All endpoints return a consistent response format:

```json
{
  "request_id": "req_abc123",
  "tenant_id": "tenant_001",
  "encounter_id": "enc_001",
  "document_id": "doc_001",
  "workflow": "soap",
  "model": {
    "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
    "prompt_version": "soap.v1",
    "model_version": "penthus-1.2-alpha-4b"
  },
  "result": { ... },
  "warnings": [],
  "latency_ms": 1200,
  "ocr_reused": false
}
```

---

## 5. Usage Examples

### 5.1 OCR - Extract Text from Medical Document

**Use Case:** Convert scanned medical documents, lab reports, or handwritten notes into structured text.

```bash
curl -X POST http://localhost/api/v1/ocr \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "tenant_id": "tenant_001",
    "encounter_id": "enc_001",
    "document_id": "doc_lab_report_001",
    "image": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAA...",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "request_id": "req_ocr_001",
  "tenant_id": "tenant_001",
  "encounter_id": "enc_001",
  "document_id": "doc_lab_report_001",
  "workflow": "ocr",
  "model": {
    "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
    "prompt_version": "ocr.v1",
    "model_version": "penthus-1.2-alpha-4b"
  },
  "result": {
    "raw_text": "LABORATORY RESULTS\nPatient: John Doe\nDate: 2026-06-11\n...",
    "entities": [
      {"type": "PATIENT_NAME", "text": "John Doe"},
      {"type": "DATE", "text": "2026-06-11"},
      {"type": "LAB_TEST", "text": "Hemoglobin", "value": "14.2 g/dL"}
    ],
    "layout": {"pages": 1, "confidence": 0.97},
    "language": "en",
    "confidence": 0.97
  },
  "warnings": [],
  "latency_ms": 850,
  "ocr_reused": false
}
```

---

### 5.2 SOAP Note Generation

**Use Case:** Generate structured SOAP notes from physician dictation or rough clinical notes.

```bash
curl -X POST http://localhost/api/v1/soap \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "tenant_id": "tenant_001",
    "encounter_id": "enc_001",
    "text": "Patient has fever for 3 days and dry cough. No chest pain. Vitals: T 38.5C, HR 92, BP 120/80, SpO2 97%. Lungs clear on auscultation.",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "request_id": "req_soap_001",
  "tenant_id": "tenant_001",
  "encounter_id": "enc_001",
  "workflow": "soap",
  "model": {
    "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
    "prompt_version": "soap.v1",
    "model_version": "penthus-1.2-alpha-4b"
  },
  "result": {
    "subjective": "Patient reports fever for 3 days accompanied by dry cough. Denies chest pain.",
    "objective": "Temperature 38.5°C, Heart Rate 92 bpm, Blood Pressure 120/80 mmHg, SpO2 97% on room air. Lungs clear to auscultation bilaterally.",
    "assessment": "Upper respiratory infection, likely viral etiology.",
    "plan": "1. Supportive care with rest and hydration\n2. Acetaminophen 650mg q6h PRN fever\n3. Return precautions reviewed\n4. Follow up in 3 days if symptoms persist or worsen"
  },
  "warnings": [],
  "latency_ms": 1450,
  "ocr_reused": null
}
```

---

### 5.3 Clinical Entity Extraction

**Use Case:** Extract problems, medications, procedures, and other clinical entities from unstructured text.

```bash
curl -X POST http://localhost/api/v1/entities \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "tenant_id": "tenant_001",
    "encounter_id": "enc_001",
    "text": "Patient with history of Type 2 Diabetes Mellitus on Metformin 500mg BID presents with hypertension. Started Lisinopril 10mg daily. Also takes Atorvastatin 20mg for hyperlipidemia.",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "request_id": "req_entities_001",
  "tenant_id": "tenant_001",
  "encounter_id": "enc_001",
  "workflow": "entities",
  "model": {
    "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
    "prompt_version": "entities.v1",
    "model_version": "penthus-1.2-alpha-4b"
  },
  "result": {
    "problems": [
      {"text": "Type 2 Diabetes Mellitus", "category": "problem"},
      {"text": "hypertension", "category": "problem"},
      {"text": "hyperlipidemia", "category": "problem"}
    ],
    "medications": [
      {"text": "Metformin", "dose": "500mg", "frequency": "BID"},
      {"text": "Lisinopril", "dose": "10mg", "frequency": "daily"},
      {"text": "Atorvastatin", "dose": "20mg", "frequency": "unspecified"}
    ],
    "procedures": [],
    "symptoms": []
  },
  "warnings": [],
  "latency_ms": 980
}
```

---

### 5.4 Documentation Gap Detection

**Use Case:** Identify missing elements in clinical documentation for quality improvement.

```bash
curl -X POST http://localhost/api/v1/gaps \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "tenant_id": "tenant_001",
    "encounter_id": "enc_001",
    "text": "Patient came in complaining of chest pain. Did EKG. Gave aspirin. Sent home.",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "request_id": "req_gaps_001",
  "tenant_id": "tenant_001",
  "encounter_id": "enc_001",
  "workflow": "gaps",
  "model": {
    "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
    "prompt_version": "gaps.v1",
    "model_version": "penthus-1.2-alpha-4b"
  },
  "result": {
    "missing_elements": [
      {
        "category": "history_of_present_illness",
        "description": "Detailed characterization of chest pain (onset, duration, quality, radiation, aggravating/alleviating factors)",
        "severity": "high"
      },
      {
        "category": "review_of_systems",
        "description": "Complete review of systems not documented",
        "severity": "medium"
      },
      {
        "category": "physical_exam",
        "description": "Vital signs and detailed physical examination findings not documented",
        "severity": "high"
      },
      {
        "category": "assessment",
        "description": "Differential diagnosis and working diagnosis not clearly stated",
        "severity": "high"
      },
      {
        "category": "plan",
        "description": "Follow-up instructions, return precautions, and medication details not specified",
        "severity": "medium"
      }
    ],
    "documentation_quality_score": 0.35
  },
  "warnings": [],
  "latency_ms": 1100
}
```

---

### 5.5 FHIR Resource Generation

**Use Case:** Convert clinical narratives into standardized FHIR R4 resources.

```bash
curl -X POST http://localhost/api/v1/fhir \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "tenant_id": "tenant_001",
    "encounter_id": "enc_001",
    "text": "Patient John Doe, DOB 1980-05-15, diagnosed with Type 2 Diabetes. Prescribed Metformin 500mg twice daily. HbA1c 7.2%.",
    "resource_type": "Condition",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "request_id": "req_fhir_001",
  "tenant_id": "tenant_001",
  "encounter_id": "enc_001",
  "workflow": "fhir",
  "model": {
    "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
    "prompt_version": "fhir.v1",
    "model_version": "penthus-1.2-alpha-4b"
  },
  "result": {
    "resourceType": "Condition",
    "id": "condition-diabetes-001",
    "clinicalStatus": {
      "coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
        "code": "active"
      }]
    },
    "verificationStatus": {
      "coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
        "code": "confirmed"
      }]
    },
    "code": {
      "coding": [{
        "system": "http://snomed.info/sct",
        "code": "44054006",
        "display": "Type 2 diabetes mellitus"
      }]
    },
    "subject": {
      "reference": "Patient/pat-001",
      "display": "John Doe"
    },
    "evidence": [{
      "detail": [{
        "reference": "Observation/hba1c-001",
        "display": "HbA1c 7.2%"
      }]
    }]
  },
  "warnings": [],
  "latency_ms": 1650
}
```

---

### 5.6 Clinical Translation

**Use Case:** Translate clinical text between supported languages while preserving medical terminology accuracy.

```bash
curl -X POST http://localhost/api/v1/translation \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "tenant_id": "tenant_001",
    "encounter_id": "enc_001",
    "text": "Patient presents with acute abdominal pain, nausea, and vomiting. Physical exam reveals tenderness in the right lower quadrant.",
    "target_language": "es",
    "language": "en"
  }'
```

**Example Response:**
```json
{
  "request_id": "req_trans_001",
  "tenant_id": "tenant_001",
  "encounter_id": "enc_001",
  "workflow": "translation",
  "model": {
    "repo_id": "Sebukpor/medical-document-understanding-v2-fixed",
    "prompt_version": "translation.v1",
    "model_version": "penthus-1.2-alpha-4b"
  },
  "result": {
    "original_text": "Patient presents with acute abdominal pain, nausea, and vomiting. Physical exam reveals tenderness in the right lower quadrant.",
    "translated_text": "El paciente presenta dolor abdominal agudo, náuseas y vómitos. El examen físico revela sensibilidad en el cuadrante inferior derecho.",
    "source_language": "en",
    "target_language": "es",
    "confidence": 0.96
  },
  "warnings": [],
  "latency_ms": 920
}
```

---

## 6. Python Client Example

### 6.1 Installation

```bash
pip install httpx
```

### 6.2 Sample Client Code

```python
import httpx
import base64
from typing import Optional, Dict, Any

class PenthusClient:
    """Async client for Penthus Clinical AI API."""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["X-API-Key"] = api_key
    
    async def generate_soap(
        self,
        text: str,
        tenant_id: str,
        encounter_id: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """Generate SOAP note from clinical text."""
        payload = {
            "tenant_id": tenant_id,
            "encounter_id": encounter_id,
            "text": text,
            "language": language
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/soap",
                json=payload,
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def extract_entities(
        self,
        text: str,
        tenant_id: str,
        encounter_id: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """Extract clinical entities from text."""
        payload = {
            "tenant_id": tenant_id,
            "encounter_id": encounter_id,
            "text": text,
            "language": language
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/entities",
                json=payload,
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def ocr_document(
        self,
        image_path: str,
        tenant_id: str,
        encounter_id: str,
        document_id: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """Perform OCR on a document image."""
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        payload = {
            "tenant_id": tenant_id,
            "encounter_id": encounter_id,
            "document_id": document_id,
            "image": f"data:image/jpeg;base64,{image_data}",
            "language": language
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/ocr",
                json=payload,
                headers=self.headers,
                timeout=60.0
            )
            response.raise_for_status()
            return response.json()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check API health status."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/health",
                headers=self.headers,
                timeout=5.0
            )
            response.raise_for_status()
            return response.json()


# Usage Example
async def main():
    client = PenthusClient(
        base_url="http://your-server-ip",
        api_key="your-api-key"
    )
    
    # Check health
    health = await client.health_check()
    print(f"API Status: {health['status']}")
    
    # Generate SOAP note
    soap_result = await client.generate_soap(
        text="Patient complains of headache and mild fever for 2 days.",
        tenant_id="tenant_001",
        encounter_id="enc_12345"
    )
    print(f"SOAP Note: {soap_result['result']}")


# Run with: asyncio.run(main())
```

---

## 7. Error Handling

### 7.1 Common HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| `200` | Success | Process response normally |
| `400` | Bad Request | Check request payload format |
| `401` | Unauthorized | Verify API key |
| `403` | Forbidden | Check tenant permissions |
| `404` | Not Found | Verify endpoint URL |
| `408` | Request Timeout | Retry with longer timeout |
| `429` | Too Many Requests | Implement rate limiting |
| `500` | Internal Server Error | Contact support |
| `503` | Service Unavailable | Check service health |

### 7.2 Error Response Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Missing required field: tenant_id",
    "details": {
      "field": "tenant_id",
      "reason": "Field is required"
    }
  },
  "request_id": "req_error_001",
  "timestamp": "2026-06-11T12:00:00.000000+00:00"
}
```

---

## 8. Best Practices

### 8.1 Performance Optimization

1. **Reuse OCR Results**: Always provide `document_id` for images to leverage OCR caching
2. **Batch Operations**: Group related requests when possible
3. **Connection Pooling**: Use HTTP connection pooling in your client
4. **Async Processing**: Use async clients for high-throughput scenarios

### 8.2 Security Recommendations

1. **API Key Management**: Store API keys securely, never in source code
2. **HTTPS Only**: Always use HTTPS in production
3. **Tenant Isolation**: Ensure proper `tenant_id` segregation
4. **PHI Handling**: Encrypt sensitive data in transit and at rest

### 8.3 Rate Limiting

Implement exponential backoff for retries:

```python
import asyncio
from httpx import RequestError

async def retry_with_backoff(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except RequestError as e:
            if attempt == max_retries - 1:
                raise
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait_time)
```

---

## 9. Monitoring & Observability

### 9.1 Health Endpoints

```bash
# Basic health check
curl http://localhost/api/v1/health

# Detailed readiness (for load balancers)
curl http://localhost/api/v1/readiness

# Prometheus metrics
curl http://localhost/api/v1/metrics
```

### 9.2 Key Metrics

- **Request Latency**: Track `latency_ms` in responses
- **OCR Cache Hit Rate**: Monitor `ocr_reused` field
- **Error Rates**: Track HTTP 4xx/5xx responses
- **Token Usage**: Available in detailed logging

---

## 10. Support & Resources

| Resource | Location |
|----------|----------|
| Interactive API Docs | `http://<server>/docs` (Swagger UI) |
| OpenAPI Schema | `http://<server>/openapi.json` |
| GitHub Repository | `/workspace` |
| Architecture Docs | `README.md`, `DEPLOYMENT-OCI-MVP.md` |

---

## 11. Quick Reference Card

```bash
# Health Check
curl http://localhost/api/v1/health

# Generate SOAP Note
curl -X POST http://localhost/api/v1/soap \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"t1","encounter_id":"e1","text":"Patient has fever"}'

# Extract Entities
curl -X POST http://localhost/api/v1/entities \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"t1","encounter_id":"e1","text":"Diabetes, hypertension"}'

# Check Readiness
curl http://localhost/api/v1/readiness

# View Swagger UI
# Open browser: http://<server-ip>/docs
```

---

**Document Version:** 1.0  
**Last Updated:** June 11, 2026  
**Maintained By:** Platform Engineering Team
