# Penthus Clinical AI Engine — PostgreSQL Database Schema

## Entity Relationship Overview

```
tenants (1) ──────────────────────────────────────────────────────────────────┐
   │                                                                           │
   ├──< encounters (M)                                                         │
   │        │                                                                  │
   │        ├──< documents (M)                                                 │
   │        │        │                                                         │
   │        │        └──< ocr_results (1)  [unique per tenant+document]       │
   │        │                                                                  │
   │        ├──< clinical_contexts (M)  [accumulates all workflow state]      │
   │        │                                                                  │
   │        ├──< soap_results (M)                                             │
   │        ├──< entity_results (M)                                           │
   │        ├──< normalization_results (M)                                    │
   │        ├──< summary_results (M)                                          │
   │        ├──< gap_results (M)                                              │
   │        ├──< translation_results (M)                                      │
   │        ├──< fhir_resources (M)                                           │
   │        └──< terminology_results (M)                                      │
   │                                                                           │
   ├──< audit_logs (M)                                                        │
   ├──< inference_logs (M)                                                    │
   └──< api_keys (M)  ─────────────────────────────────────────────────────── ┘
```

---

## Table Definitions

### 1. tenants
**Purpose:** Top-level multi-tenant isolation. Every record in the system belongs to a tenant.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `name` | TEXT | NOT NULL | — | Organization name |
| `status` | VARCHAR(20) | NOT NULL | 'active' | 'active' or 'inactive' |
| `settings` | JSONB | NULL | '{}' | Tenant config overrides |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation timestamp |

**Relationships:** Referenced by ALL other tables via `tenant_id` foreign key.

---

### 2. encounters
**Purpose:** Represents a clinical encounter (patient visit, consultation, etc.). Groups all documents and AI results for one visit.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `patient_id` | VARCHAR | NULL | — | External EMR patient ID |
| `encounter_type` | VARCHAR | NULL | — | 'inpatient', 'outpatient', 'emergency' |
| `started_at` | TIMESTAMPTZ | NULL | — | Encounter start time |
| `department` | VARCHAR | NULL | — | Clinical department |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Record creation |

**Relationships:**
- belongs to → `tenants`
- has many → `documents`, `clinical_contexts`, `soap_results`, `entity_results`, etc.

---

### 3. documents
**Purpose:** Uploaded medical documents (images, PDFs). Enables OCR caching via content hash.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `encounter_id` | UUID | NOT NULL | — | **FK → encounters.id** |
| `content_hash` | VARCHAR(64) | NOT NULL | — | SHA-256 hash for deduplication |
| `object_uri` | TEXT | NULL | — | Object storage URI (OCI/S3) |
| `mime_type` | VARCHAR(100) | NULL | — | e.g. 'image/jpeg', 'application/pdf' |
| `language` | VARCHAR(10) | NULL | — | ISO 639-1 language code |
| `file_size_bytes` | INTEGER | NULL | — | File size in bytes |
| `metadata` | JSONB | NULL | '{}' | Additional metadata |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Upload timestamp |

**Relationships:**
- belongs to → `tenants`, `encounters`
- has one → `ocr_results`

---

### 4. ocr_results
**Purpose:** Stores OCR extraction output. One result per tenant+document combination (upserted on conflict).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `document_id` | UUID | NOT NULL | — | **FK → documents.id** |
| `raw_text` | TEXT | NOT NULL | — | Extracted clinical text |
| `entities` | JSONB | NOT NULL | '[]' | Detected clinical entities |
| `layout` | JSONB | NOT NULL | '{}' | Page/block layout info |
| `language` | VARCHAR(10) | NOT NULL | 'en' | Document language |
| `confidence` | FLOAT | NULL | — | Extraction confidence (0.0–1.0) |
| `model_version` | VARCHAR | NOT NULL | — | Model checkpoint used |
| `prompt_version` | VARCHAR | NOT NULL | — | Prompt version used |
| `processing_time_ms` | INTEGER | NULL | — | Processing duration |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation timestamp |

**Unique Constraint:** `uq_ocr_tenant_document` on `(tenant_id, document_id)`
**Also cached in:** Redis key `ocr:{tenant_id}:{content_hash}` (30 day TTL)

---

### 5. clinical_contexts
**Purpose:** Accumulates the full workflow state for an encounter. Updated after each workflow step runs. Used by subsequent steps to build on prior results.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `encounter_id` | UUID | NOT NULL | — | **FK → encounters.id** |
| `document_id` | UUID | NULL | — | Optional document reference |
| `state` | JSONB | NOT NULL | '{}' | Full accumulated context (see structure below) |
| `version` | INTEGER | NOT NULL | 1 | Optimistic concurrency version |
| `updated_at` | TIMESTAMPTZ | NOT NULL | now() | Last update |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation |

**State JSONB Structure:**
```json
{
  "ocr": {
    "raw_text": "--- PATIENT DEMOGRAPHICS ---\nDept: Ophthalmology..."
  },
  "soap": {
    "subjective": "Patient presented for routine exam...",
    "objective": "VA: 6/12P bilaterally. IOP: 21/23 mmHg...",
    "assessment": "Mild refractive error. Presbyopia...",
    "plan": "E19 eye drops 6TID x 1 month. Follow up 1 month."
  },
  "entities": [
    { "type": "CONDITION", "text": "refractive error", "confidence": 0.95 }
  ],
  "normalized_terms": [
    { "source_text": "IOP", "normalized_text": "Intraocular Pressure" }
  ],
  "snomed_candidates": [
    { "code": "386661006", "display": "Fever", "source": "SNOMED_CT" }
  ],
  "icd_candidates": [
    { "code": "9D00", "display": "Refractive error of eye", "source": "ICD11" }
  ],
  "fhir_resources": [
    { "resourceType": "Encounter", "resource": { ... } }
  ],
  "workflow_state": {
    "ocr": { "completed": true, "timestamp": "2026-06-19T11:00:00Z" },
    "soap": { "completed": true, "timestamp": "2026-06-19T11:01:00Z" },
    "snomed": { "completed": true, "timestamp": "2026-06-19T11:02:00Z" },
    "icd": { "completed": true, "timestamp": "2026-06-19T11:02:30Z" },
    "fhir": { "completed": true, "timestamp": "2026-06-19T11:03:00Z" }
  }
}
```

---

### 6. soap_results
**Purpose:** Stores generated SOAP notes per encounter.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `encounter_id` | UUID | NOT NULL | — | **FK → encounters.id** |
| `subjective` | TEXT | NOT NULL | — | Patient-reported symptoms |
| `objective` | TEXT | NOT NULL | — | Exam findings and measurements |
| `assessment` | TEXT | NOT NULL | — | Clinical assessment |
| `plan` | TEXT | NOT NULL | — | Treatment plan |
| `model_version` | VARCHAR | NOT NULL | — | Model used |
| `prompt_version` | VARCHAR | NOT NULL | — | Prompt version |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation timestamp |

---

### 7. entity_results
**Purpose:** Stores extracted clinical entities per encounter.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `encounter_id` | UUID | NOT NULL | — | **FK → encounters.id** |
| `entities` | JSONB | NOT NULL | '[]' | Array of typed entities |
| `model_version` | VARCHAR | NOT NULL | — | Model used |
| `prompt_version` | VARCHAR | NOT NULL | — | Prompt version |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation timestamp |

---

### 8. normalization_results
**Purpose:** Stores normalized clinical terms per encounter.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `encounter_id` | UUID | NOT NULL | — | **FK → encounters.id** |
| `normalized_terms` | JSONB | NOT NULL | '[]' | Array of normalized terms |
| `model_version` | VARCHAR | NOT NULL | — | Model used |
| `prompt_version` | VARCHAR | NOT NULL | — | Prompt version |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation timestamp |

---

### 9. terminology_results
**Purpose:** Stores SNOMED CT and ICD-11 terminology mapping results.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `encounter_id` | UUID | NOT NULL | — | **FK → encounters.id** |
| `system` | VARCHAR | NOT NULL | — | 'SNOMED_CT' or 'ICD11' |
| `query_terms` | JSONB | NOT NULL | '[]' | Input terms searched |
| `normalized_terms` | JSONB | NOT NULL | '[]' | AI-normalized terms |
| `candidates` | JSONB | NOT NULL | '[]' | Code candidates from external service |
| `terminology_service_available` | BOOLEAN | NOT NULL | false | Whether external service responded |
| `model_version` | VARCHAR | NOT NULL | — | Model used for normalization |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation timestamp |

---

### 10. fhir_resources
**Purpose:** Stores generated FHIR R4 resource bundles per encounter.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `encounter_id` | UUID | NOT NULL | — | **FK → encounters.id** |
| `resources` | JSONB | NOT NULL | '[]' | Array of FHIR R4 resources |
| `resource_types` | JSONB | NOT NULL | '[]' | List of resource types generated |
| `model_version` | VARCHAR | NOT NULL | — | Model used |
| `prompt_version` | VARCHAR | NOT NULL | — | Prompt version |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation timestamp |

---

### 11. summary_results
**Purpose:** Stores clinical summaries per encounter.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `encounter_id` | UUID | NOT NULL | — | **FK → encounters.id** |
| `summary` | TEXT | NOT NULL | — | Generated clinical summary |
| `key_findings` | JSONB | NULL | '[]' | Extracted key findings |
| `model_version` | VARCHAR | NOT NULL | — | Model used |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation timestamp |

---

### 12. gap_results
**Purpose:** Stores documentation gap detection results.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `encounter_id` | UUID | NOT NULL | — | **FK → encounters.id** |
| `gaps` | JSONB | NOT NULL | '[]' | Array of detected gaps |
| `completeness_score` | FLOAT | NULL | — | Documentation completeness (0.0–1.0) |
| `recommendations` | JSONB | NULL | '[]' | Improvement recommendations |
| `model_version` | VARCHAR | NOT NULL | — | Model used |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation timestamp |

---

### 13. translation_results
**Purpose:** Stores clinical translation results.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `encounter_id` | UUID | NOT NULL | — | **FK → encounters.id** |
| `source_language` | VARCHAR(10) | NOT NULL | — | ISO source language |
| `target_language` | VARCHAR(10) | NOT NULL | — | ISO target language |
| `original_text` | TEXT | NOT NULL | — | Input clinical text |
| `translated_text` | TEXT | NOT NULL | — | Translated output |
| `confidence` | FLOAT | NULL | — | Translation confidence |
| `model_version` | VARCHAR | NOT NULL | — | Model used |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Creation timestamp |

---

### 14. inference_logs
**Purpose:** Audit trail for all model inference calls. Every API request is logged.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `request_id` | VARCHAR | NOT NULL | — | Unique request correlation ID |
| `workflow` | VARCHAR | NOT NULL | — | 'ocr', 'soap', 'entities', etc. |
| `model_repo` | VARCHAR | NOT NULL | — | HuggingFace model repo ID |
| `model_version` | VARCHAR | NOT NULL | — | Model checkpoint |
| `prompt_version` | VARCHAR | NOT NULL | — | Prompt version |
| `latency_ms` | INTEGER | NOT NULL | — | Total processing time |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Request timestamp |

---

### 15. audit_logs
**Purpose:** PHI-masked audit trail for compliance and security monitoring.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | gen_random_uuid() | **Primary Key** |
| `tenant_id` | UUID | NOT NULL | — | **FK → tenants.id** |
| `action` | VARCHAR | NOT NULL | — | Action performed |
| `resource_type` | VARCHAR | NOT NULL | — | Resource type affected |
| `resource_id` | VARCHAR | NULL | — | Resource identifier |
| `user_id` | VARCHAR | NULL | — | User or service account |
| `ip_address` | VARCHAR | NULL | — | Client IP address |
| `details` | JSONB | NULL | '{}' | PHI-masked action details |
| `created_at` | TIMESTAMPTZ | NOT NULL | now() | Event timestamp |

---

## Key Relationships Summary

```
tenants.id
  └─ FK ← encounters.tenant_id
  └─ FK ← documents.tenant_id
  └─ FK ← ocr_results.tenant_id
  └─ FK ← clinical_contexts.tenant_id
  └─ FK ← soap_results.tenant_id
  └─ FK ← entity_results.tenant_id
  └─ FK ← normalization_results.tenant_id
  └─ FK ← terminology_results.tenant_id
  └─ FK ← fhir_resources.tenant_id
  └─ FK ← summary_results.tenant_id
  └─ FK ← gap_results.tenant_id
  └─ FK ← translation_results.tenant_id
  └─ FK ← inference_logs.tenant_id
  └─ FK ← audit_logs.tenant_id

encounters.id
  └─ FK ← documents.encounter_id
  └─ FK ← clinical_contexts.encounter_id
  └─ FK ← soap_results.encounter_id
  └─ FK ← entity_results.encounter_id
  └─ FK ← normalization_results.encounter_id
  └─ FK ← terminology_results.encounter_id
  └─ FK ← fhir_resources.encounter_id
  └─ FK ← summary_results.encounter_id
  └─ FK ← gap_results.encounter_id
  └─ FK ← translation_results.encounter_id

documents.id
  └─ FK ← ocr_results.document_id (unique per tenant+document)
  └─ FK ← clinical_contexts.document_id (optional)
```

---



