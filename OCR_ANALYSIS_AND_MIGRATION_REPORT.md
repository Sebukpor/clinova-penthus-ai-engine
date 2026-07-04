# OCR Service Analysis and Migration Report

## Executive Summary

This report provides a comprehensive technical analysis of the Clinova Penthus AI Engine OCR service, identifies root causes of response inconsistencies, and proposes a migration to a stateless architecture with normalized schemas suitable for production healthcare deployment.

---

## 1. Root Cause Analysis

### 1.1 Primary Causes of Response Inconsistencies

#### A. Stateful Caching Architecture (CRITICAL)

The current system implements a **three-tier caching strategy** that returns cached responses when the same `document_id` or content hash is encountered:

**Cache Hierarchy:**
1. **Local Memory Cache** (`_local_cache` dict in `OCRDependencyResolver`)
   - Key format: `ocr:{tenant_id}:{content_hash}`
   - Lifetime: Process lifetime (no TTL)
   - Location: `app/orchestrator/ocr_dependency.py:46, 98-101`

2. **Database Cache** (`OCRResult` table)
   - Lookup: By `tenant_id` + `document_id` (unique constraint)
   - Location: `app/orchestrator/ocr_dependency.py:103-108`, `app/db/models.py:130-156`
   - Returns identical results indefinitely unless `force_rerun=True`

3. **Redis Cache** 
   - Key format: `ocr:{tenant_id}:{content_hash}`
   - TTL: 30 days (configurable via `OCR_CACHE_TTL_SECONDS`)
   - Location: `app/orchestrator/ocr_dependency.py:110-118`, `app/context/cache.py`

**Impact:** When the same `document_id` is submitted twice, the system returns the **exact same cached response** without re-processing. This explains "reused responses for the same document_id."

#### B. Non-Deterministic Model Generation

The OCR model (`Sebukpor/medical-document-understanding-v2-fixed`) generates structured outputs with:

- **Open-ended entity types**: The prompt explicitly states `"type" is not a fixed enum -- use whatever label best fits` (prompts/ocr.v1.yaml:67-73)
- **Flexible layout block types**: Similarly open-ended with examples like `heading, paragraph, table, table_row, form_field, signature, stamp, checkbox_section, vitals_chart, prescription_line` (prompts/ocr.v1.yaml:76-78)
- **Temperature = 0.0** but still subject to model variance due to floating-point operations and batch effects

**Impact:** Even with temperature=0, similar documents may produce:
- Different entity type labels (e.g., `symptom` vs `finding` vs `clinical_finding`)
- Different layout block classifications (e.g., `paragraph` vs `text_block`)
- Varying levels of granularity in entity extraction

#### C. Weak Schema Enforcement

While Pydantic models exist (`app/schemas/ocr.py`), the validation is **permissive**:

```python
# app/schemas/ocr.py
class OCREntity(BaseModel):
    text: str = Field(..., description="Extracted text")
    type: str = Field(..., description="Entity type (symptom, duration, medication, etc.)")  # No enum!

class OCRLayoutBlock(BaseModel):
    type: str = Field(..., description="Block type (paragraph, heading, table, etc.)")  # No enum!
```

**Impact:** Any string value is accepted for `type` fields, allowing model drift over time.

#### D. Partial Extraction Results

Partial results occur when:
1. JSON parsing fails and fallback is triggered (`app/orchestrator/ocr_dependency.py:248-266`)
2. The `_parse_error` field indicates parsing failure
3. Model output is truncated or malformed

**Code Path:**
```python
# app/orchestrator/ocr_dependency.py:248-266
except Exception as e:
    logger.error("ocr_parse_failed", error=str(e), ...)
    return {
        "document_id": document_id,
        "raw_text": fallback_text,  # Extracted from raw output
        "entities": [],              # EMPTY!
        "layout": {"pages": 1, "blocks": []},  # EMPTY!
        "language": language,
        "_parse_error": str(e),
    }
```

---

## 2. Current Architecture Findings

### 2.1 Request Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    OCR Request Flow                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Client POST /api/v1/ocr                                      │
│     └─> ClinicalRequest {tenant_id, encounter_id, document_id,   │
│                          image/file, language}                   │
│                                                                  │
│  2. ClinicalAIOrchestrator.run()                                 │
│     └─> Process input documents (PDF/TXT/Image)                  │
│                                                                  │
│  3. OCRDependencyResolver.resolve()                              │
│     ├─> Check local cache (memory)                               │
│     ├─> Check database (OCRResult by document_id)                │
│     ├─> Check Redis cache (by content_hash)                      │
│     └─> If miss: Execute OCR model                               │
│                                                                  │
│  4. _execute_ocr()                                               │
│     ├─> Image preprocessing (optional)                           │
│     ├─> Prompt rendering (ocr.v1.yaml)                           │
│     ├─> VLLM chat completion                                     │
│     ├─> JSON repair & parsing                                    │
│     └─> Pydantic validation                                      │
│                                                                  │
│  5. _persist_ocr()                                               │
│     └─> Store in DB + Redis + local cache                        │
│                                                                  │
│  6. Return ClinicalResponse                                      │
│     └─> {request_id, result{raw_text, entities, layout},         │
│          ocr_reused: bool}                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `OCRDependencyResolver` | `app/orchestrator/ocr_dependency.py` | Cache resolution + OCR execution |
| `ClinicalAIOrchestrator` | `app/orchestrator/engine.py` | Workflow orchestration |
| `OCRResult` (model) | `app/db/models.py` | Database persistence |
| `OCRResult` (schema) | `app/schemas/ocr.py` | API response schema |
| `PromptManager` | `app/prompts/manager.py` | Prompt template management |
| `VLLMClient` | `app/llm/vllm_client.py` | Model inference |
| `CacheClient` | `app/context/cache.py` | Redis caching |

### 2.3 Database Schema

```sql
-- OCR Results Table (app/db/models.py:130-156)
CREATE TABLE ocr_results (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    document_id UUID NOT NULL REFERENCES documents(id),
    raw_text TEXT NOT NULL,                    -- Full OCR extraction
    entities JSONB DEFAULT [],                 -- Structured entities
    layout JSONB DEFAULT {},                   -- Layout blocks
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    model_version VARCHAR(100) NOT NULL,       -- e.g., "penthus-1.2-alpha-4b"
    prompt_version VARCHAR(50) NOT NULL,       -- e.g., "ocr.v1"
    processing_time_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(tenant_id, document_id)             -- Enforces single result per doc
);
```

### 2.4 Prompt Configuration

From `prompts/ocr.v1.yaml`:
- **Model**: `Sebukpor/medical-document-understanding-v2-fixed`
- **Temperature**: 0.0 (deterministic intent)
- **Max Tokens**: 8192
- **Response Format**: JSON
- **Schema Reference**: `OCRResult`

**Critical Prompt Design Issues:**
1. Explicitly allows open-ended entity types: `"type" is not a fixed enum`
2. Explicitly allows open-ended layout types: `"type" is likewise open-ended`
3. Encourages completeness over consistency: `When in doubt... include it rather than omit it`

---

## 3. Stateful Behavior Explanation

### 3.1 How Document ID Reuse Impacts Outputs

**Scenario:** Client submits the same document twice with identical `document_id`.

**First Request:**
```
POST /api/v1/ocr
{
  "document_id": "doc_123",
  "image": "data:image/jpeg;base64,/9j/..."
}

→ Cache MISS
→ Model executes
→ Result stored in DB + Redis + local cache
→ Response: {raw_text: "...", entities: [...], ...}
```

**Second Request (identical):**
```
POST /api/v1/ocr
{
  "document_id": "doc_123",
  "image": "data:image/jpeg;base64,/9j/..."  # Same image
}

→ Cache HIT (DB lookup by tenant_id + document_id)
→ Returns CACHED result WITHOUT re-executing model
→ Response: {raw_text: "...", entities: [...], ...}  # IDENTICAL
```

**Code Reference:**
```python
# app/orchestrator/ocr_dependency.py:103-108
if not force_rerun and self.db:
    existing = await self._get_ocr_repo().get_by_document(tenant_uuid, doc_uuid)
    if existing:
        logger.info("ocr_db_hit", document_id=document_id, request_id=request_id)
        record_ocr_cache_hit("db_hit")
        return self._db_to_schema(existing), True  # ← Returns cached data
```

### 3.2 Why Cached Responses Are Returned

**Design Intent:**
- Reduce latency for repeated requests
- Reduce model inference costs
- Ensure consistency for downstream workflows (SOAP, entities, etc.)

**Unintended Consequences:**
1. **Stale Results**: If the model is updated, old cached results remain unchanged
2. **No Idempotency Guarantee**: Same input should produce same output naturally, not via caching
3. **Debugging Difficulty**: Hard to distinguish between "model produced this" vs "cache returned this"
4. **Schema Drift Hidden**: Cached responses may use outdated entity/layout taxonomies

### 3.3 Risks of Stateful OCR Pipelines

| Risk | Severity | Impact |
|------|----------|--------|
| **Non-reproducibility** | HIGH | Cannot reproduce results without exact cache state |
| **Schema instability** | HIGH | Cached responses may not match current schema expectations |
| **Migration complexity** | MEDIUM | Cache invalidation required for schema changes |
| **Testing difficulty** | MEDIUM | Tests must manage cache state |
| **Memory leaks** | MEDIUM | Local cache grows unbounded |
| **Tenant isolation bugs** | CRITICAL | Cache key collisions could leak data across tenants |

### 3.4 Why Deterministic Integrations Become Difficult

**Integration Challenge:** Backend systems expect consistent field values for mapping.

**Example Problem:**
```
Request 1 (Monday):
  entities: [{text: "fever", type: "symptom"}]
  → Backend maps "symptom" → SNOMED: 386661006

Request 2 (Tuesday, same document):
  entities: [{text: "fever", type: "clinical_finding"}]  # From cache? Or model variance?
  → Backend has no mapping for "clinical_finding" → FAILS
```

**Root Cause:** Without enforced enums, the model (or different model versions) can produce semantically equivalent but syntactically different outputs.

---

## 4. Recommended Stateless Design

### 4.1 Stateless Architecture Principles

1. **No Persistent State**: Each request is processed independently
2. **Idempotent by Design**: Same input → same output (via deterministic model params)
3. **Explicit Caching**: Cache is opt-in, transparent, and invalidatable
4. **Schema Contracts**: Strict enum enforcement at API boundary

### 4.2 Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Stateless OCR Flow                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Client POST /api/v1/ocr                                      │
│     └─> ClinicalRequest {idempotency_key?, document_id, ...}     │
│                                                                  │
│  2. Idempotency Check (optional)                                 │
│     └─> If idempotency_key seen within TTL, return cached result │
│        (explicit client opt-in, not automatic)                   │
│                                                                  │
│  3. Execute OCR (always)                                         │
│     ├─> Image preprocessing                                      │
│     ├─> Prompt rendering (with schema enforcement hints)         │
│     ├─> VLLM chat completion (temperature=0, seed=fixed?)        │
│     ├─> JSON repair & parsing                                    │
│     ├─> Pydantic validation WITH ENUM ENFORCEMENT                │
│     └─> Post-processing normalization                            │
│                                                                  │
│  4. Optional Persistence                                         │
│     └─> Store result (async, non-blocking)                       │
│        - For audit trail                                          │
│        - Not used for request deduplication                       │
│                                                                  │
│  5. Return ClinicalResponse                                      │
│     └─> {request_id, result{normalized...}, warnings, ...}       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Idempotency Strategy

**Option A: Client-Managed Idempotency (Recommended)**
```python
# Client includes explicit idempotency key
POST /api/v1/ocr
Headers:
  Idempotency-Key: req_abc123
Body:
  {document_id: "doc_123", ...}

# Server behavior:
# - If key seen within 24h TTL, return cached response
# - Include header: X-Idempotency-Cache-Hit: true
```

**Option B: Content-Based Deduplication**
```python
# Hash of (tenant_id, content_hash, prompt_version, model_version)
# Only deduplicate if ALL parameters match
cache_key = sha256(f"{tenant_id}:{content_hash}:{prompt_version}:{model_version}")
```

### 4.4 Cache Strategy

| Cache Type | Purpose | TTL | Invalidation |
|------------|---------|-----|--------------|
| **Idempotency Cache** | Explicit replay protection | 24 hours | Automatic expiry |
| **CDN/Edge Cache** | Static asset caching | 1 hour | Cache-Control headers |
| **Result Cache** | Optional performance optimization | 1 hour | Manual purge API |
| **NO Default Cache** | Remove automatic caching | N/A | N/A |

**Removed:**
- Local memory cache (`_local_cache` dict)
- Automatic DB lookup by `document_id`
- Long-lived Redis cache (30 days)

### 4.5 Request Isolation Strategy

```python
class StatelessOCRProcessor:
    def __init__(self, vllm_client, prompt_manager):
        self.vllm = vllm_client
        self.prompts = prompt_manager
        # NO cache references
    
    async def process(self, request: OCRRequest) -> OCRResponse:
        # Always execute fresh
        result = await self._execute_ocr(request)
        
        # Normalize output
        normalized = self._normalize(result)
        
        # Validate against strict schema
        validated = self._validate(normalized)
        
        return validated
```

### 4.6 Reproducibility Strategy

1. **Fixed Random Seed**: Pass `seed=42` to vLLM (if supported)
2. **Deterministic Sampling**: Use `temperature=0.0`, `top_p=1.0`, `top_k=1`
3. **Version Pinning**: Include `model_version` and `prompt_version` in response
4. **Audit Logging**: Log all inputs and outputs for traceability

### 4.7 Benefits of Stateless Processing

| Benefit | Description |
|---------|-------------|
| **Consistency** | Same input always produces same output (modulo model nondeterminism) |
| **Debugging** | Easier to reproduce issues without cache state |
| **Schema Stability** | All responses pass through same normalization pipeline |
| **Scalability** | No shared state means horizontal scaling is trivial |
| **Testing** | Unit tests don't need cache setup/teardown |
| **Compliance** | Audit trail shows actual processing, not cache hits |

---

## 5. Final Recommended OCR Schema

### 5.1 Top-Level Response Structure

```python
from typing import Literal, List, Optional
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class OCRResponse(BaseModel):
    """Production-ready OCR response schema."""
    
    # Metadata
    request_id: str = Field(..., description="Unique request identifier")
    document_id: str = Field(..., description="Client-provided document ID")
    processed_at: datetime = Field(..., description="ISO 8601 timestamp")
    
    # Versioning
    model_version: str = Field(..., description="Model checkpoint version")
    prompt_version: str = Field(..., description="Prompt template version")
    schema_version: str = Field(default="2.0", description="Response schema version")
    
    # Core OCR Output
    raw_text: str = Field(..., description="Complete verbatim transcription")
    pages: int = Field(..., description="Number of pages processed")
    
    # Structured Layers (normalized)
    entities: List[OCREntity] = Field(default_factory=list)
    layout_blocks: List[OCRLayoutBlock] = Field(default_factory=list)
    
    # Quality Indicators
    confidence_score: Optional[float] = Field(
        default=None, 
        ge=0.0, le=1.0,
        description="Overall OCR confidence (0-1)"
    )
    quality_warnings: List[str] = Field(default_factory=list)
    
    # Language
    detected_language: str = Field(default="en", description="ISO 639-1 code")
    
    # Errors (if partial failure)
    processing_errors: List[ProcessingError] = Field(default_factory=list)
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "req_abc123",
                "document_id": "doc_123",
                "processed_at": "2025-01-15T10:30:00Z",
                "model_version": "penthus-1.2-alpha-4b",
                "prompt_version": "ocr.v2",
                "schema_version": "2.0",
                "raw_text": "Patient presents with fever...",
                "pages": 1,
                "entities": [
                    {"text": "fever", "type": "SYMPTOM", "normalized_type": "SYMPTOM"}
                ],
                "layout_blocks": [
                    {"type": "HEADING", "text": "CLINICAL NOTES", "page": 1}
                ],
                "confidence_score": 0.95,
                "quality_warnings": [],
                "detected_language": "en",
                "processing_errors": []
            }
        }
    }
```

### 5.2 Required vs Optional Fields

| Field | Required | Description |
|-------|----------|-------------|
| `request_id` | YES | Unique identifier |
| `document_id` | YES | Client reference |
| `processed_at` | YES | Timestamp |
| `model_version` | YES | Traceability |
| `prompt_version` | YES | Traceability |
| `schema_version` | YES | Schema evolution |
| `raw_text` | YES | Source of truth |
| `pages` | YES | Page count |
| `entities` | NO (default []) | Structured entities |
| `layout_blocks` | NO (default []) | Layout structure |
| `confidence_score` | NO | Quality metric |
| `quality_warnings` | NO (default []) | Warnings |
| `detected_language` | NO (default "en") | Language |
| `processing_errors` | NO (default []) | Errors |

### 5.3 Entity Taxonomy

See Section 6 for full canonical taxonomy.

### 5.4 Layout Block Taxonomy

See Section 7 for full canonical taxonomy.

### 5.5 Metadata Standards

```python
class ProcessingError(BaseModel):
    """Structured error information."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable description")
    severity: Literal["ERROR", "WARNING", "INFO"] = Field(...)
    field: Optional[str] = Field(default=None, description="Affected field")
```

### 5.6 Warnings/Errors Structure

```python
class QualityWarning(BaseModel):
    """Quality indicator warning."""
    code: Literal[
        "LOW_CONFIDENCE",
        "PARTIAL_EXTRACTION",
        "ILLEGIBLE_SECTION",
        "UNUSUAL_LAYOUT",
        "LANGUAGE_MIXED"
    ]
    message: str
    page: Optional[int] = None
    location: Optional[str] = None  # e.g., "block[3].text"
```

### 5.7 OCR Reuse Semantics

**In Stateless Design:**
- `ocr_reused` field REMOVED from response
- Optional `X-Idempotency-Cache-Hit` header for explicit idempotency
- No implicit caching

### 5.8 Confidence Handling

```python
class ConfidenceMetrics(BaseModel):
    """Granular confidence scores."""
    overall: float = Field(ge=0.0, le=1.0)
    by_section: Dict[str, float] = Field(default_factory=dict)
    low_confidence_regions: List[Dict] = Field(default_factory=list)
```

### 5.9 Page/Block Hierarchy

```python
class PageLayout(BaseModel):
    """Page-level layout information."""
    page_number: int
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    blocks: List[OCRLayoutBlock]
    reading_order: List[int] = Field(default_factory=list)  # Block indices
```

### 5.10 Normalization Rules

1. **Entity Types**: UPPERCASE enum values only
2. **Layout Types**: UPPERCASE enum values only
3. **Text Fields**: Preserve original whitespace/casing
4. **Dates**: ISO 8601 format in normalized fields
5. **Measurements**: Include units, normalize to standard format

---

## 6. Canonical Entity Taxonomy

### 6.1 Primary Entity Types (ENUM)

```python
class EntityType(str, Enum):
    """Canonical entity types - exhaustive list."""
    
    # Clinical Findings
    SYMPTOM = "SYMPTOM"                    # Patient-reported symptoms
    SIGN = "SIGN"                          # Clinician-observed findings
    DIAGNOSIS = "DIAGNOSIS"                # Diagnoses/conditions
    DIFFERENTIAL_DIAGNOSIS = "DIFFERENTIAL_DIAGNOSIS"
    
    # Treatments
    MEDICATION = "MEDICATION"              # Drugs/medications
    DOSAGE = "DOSAGE"                      # Dosage information
    ROUTE = "ROUTE"                        # Administration route
    FREQUENCY = "FREQUENCY"                # Dosing frequency
    DURATION = "DURATION"                  # Treatment duration
    PROCEDURE = "PROCEDURE"                # Medical procedures
    SURGERY = "SURGERY"                    # Surgical procedures
    THERAPY = "THERAPY"                    # Physical/occupational therapy
    
    # Patient Data
    PATIENT_NAME = "PATIENT_NAME"
    PATIENT_ID = "PATIENT_ID"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    AGE = "AGE"
    SEX = "SEX"
    GENDER = "GENDER"
    
    # Vital Signs
    VITAL_SIGN = "VITAL_SIGN"              # Generic vital
    BLOOD_PRESSURE = "BLOOD_PRESSURE"
    HEART_RATE = "HEART_RATE"
    RESPIRATORY_RATE = "RESPIRATORY_RATE"
    TEMPERATURE = "TEMPERATURE"
    OXYGEN_SATURATION = "OXYGEN_SATURATION"
    WEIGHT = "WEIGHT"
    HEIGHT = "HEIGHT"
    BMI = "BMI"
    
    # Laboratory
    LAB_TEST = "LAB_TEST"                  # Lab test name
    LAB_VALUE = "LAB_VALUE"                # Lab result value
    LAB_UNIT = "LAB_UNIT"                  # Lab result unit
    LAB_REFERENCE_RANGE = "LAB_REFERENCE_RANGE"
    
    # Allergies
    ALLERGY = "ALLERGY"                    # Allergen
    ALLERGY_REACTION = "ALLERGY_REACTION"
    
    # Administrative
    DATE = "DATE"                          # Generic date
    TIME = "TIME"
    DATETIME = "DATETIME"
    PROVIDER_NAME = "PROVIDER_NAME"
    PROVIDER_ROLE = "PROVIDER_ROLE"
    FACILITY_NAME = "FACILITY_NAME"
    DEPARTMENT = "DEPARTMENT"
    PHONE_NUMBER = "PHONE_NUMBER"
    ADDRESS = "ADDRESS"
    EMAIL = "EMAIL"
    INSURANCE_ID = "INSURANCE_ID"
    MRN = "MRN"                            # Medical Record Number
    
    # Document Structure
    SECTION_HEADING = "SECTION_HEADING"
    TABLE_HEADER = "TABLE_HEADER"
    FOOTNOTE = "FOOTNOTE"
    SIGNATURE = "SIGNATURE"
    STAMP = "STAMP"
    
    # Other
    MEASUREMENT = "MEASUREMENT"            # Generic measurement
    IDENTIFIER = "IDENTIFIER"              # Generic identifier
    FOLLOW_UP_INSTRUCTION = "FOLLOW_UP_INSTRUCTION"
    CHIEF_COMPLAINT = "CHIEF_COMPLAINT"
    HISTORY_OF_PRESENT_ILLNESS = "HISTORY_OF_PRESENT_ILLNESS"
    PAST_MEDICAL_HISTORY = "PAST_MEDICAL_HISTORY"
    FAMILY_HISTORY = "FAMILY_HISTORY"
    SOCIAL_HISTORY = "SOCIAL_HISTORY"
    REVIEW_OF_SYSTEMS = "REVIEW_OF_SYSTEMS"
    PHYSICAL_EXAMINATION = "PHYSICAL_EXAMINATION"
    ASSESSMENT = "ASSESSMENT"
    PLAN = "PLAN"
```

### 6.2 Deprecated Aliases (Mapping)

| Deprecated | Canonical |
|------------|-----------|
| `finding` | `SIGN` |
| `clinical_finding` | `SIGN` |
| `medication_name` | `MEDICATION` |
| `drug` | `MEDICATION` |
| `dose` | `DOSAGE` |
| `vital` | `VITAL_SIGN` |
| `lab` | `LAB_VALUE` |
| `doctor_name` | `PROVIDER_NAME` |
| `physician_name` | `PROVIDER_NAME` |
| `patient_name` | `PATIENT_NAME` |
| `measurement` | `MEASUREMENT` (generic) or specific type |

### 6.3 Naming Conventions

- **Format**: `UPPER_SNAKE_CASE`
- **Prefixes**: Avoid generic prefixes; be specific
- **Hierarchy**: Use specific types over generic (e.g., `BLOOD_PRESSURE` over `VITAL_SIGN`)

---

## 7. Canonical Layout Block Taxonomy

### 7.1 Primary Layout Types (ENUM)

```python
class LayoutBlockType(str, Enum):
    """Canonical layout block types."""
    
    # Text Blocks
    HEADING = "HEADING"                    # Section titles
    SUBHEADING = "SUBHEADING"              # Subsection titles
    PARAGRAPH = "PARAGRAPH"                # Prose text
    LIST_ITEM = "LIST_ITEM"                # Bulleted/numbered items
    CAPTION = "CAPTION"                    # Figure/table captions
    
    # Structured Content
    TABLE = "TABLE"                        # Entire table
    TABLE_ROW = "TABLE_ROW"                # Table row
    TABLE_CELL = "TABLE_CELL"              # Table cell
    FORM_FIELD = "FORM_FIELD"              # Form input field
    FORM_LABEL = "FORM_LABEL"              # Form field label
    CHECKBOX = "CHECKBOX"                  # Checkbox (checked/unchecked)
    RADIO_BUTTON = "RADIO_BUTTON"          # Radio selection
    
    # Clinical Specific
    VITALS_CHART = "VITALS_CHART"          # Vital signs table
    MEDICATION_LIST = "MEDICATION_LIST"    # Medication table/list
    PROBLEM_LIST = "PROBLEM_LIST"          # Problem list
    LAB_RESULTS_TABLE = "LAB_RESULTS_TABLE"  # Lab results
    
    # Document Elements
    HEADER = "HEADER"                      # Page header
    FOOTER = "FOOTER"                      # Page footer
    PAGE_NUMBER = "PAGE_NUMBER"
    WATERMARK = "WATERMARK"
    
    # Signatures/Stamps
    SIGNATURE = "SIGNATURE"                # Handwritten signature
    SIGNATURE_LINE = "SIGNATURE_LINE"      # Printed name line
    STAMP = "STAMP"                        # Rubber stamp
    SEAL = "SEAL"                          # Official seal
    
    # Images/Diagrams
    IMAGE = "IMAGE"                        # Embedded image
    DIAGRAM = "DIAGRAM"                    # Medical diagram
    GRAPH = "GRAPH"                        # Chart/graph
    ECG_WAVEFORM = "ECG_WAVEFORM"          # ECG strip
    
    # Annotations
    HANDWRITTEN_NOTE = "HANDWRITTEN_NOTE"  # Handwritten annotation
    HIGHLIGHT = "HIGHLIGHT"                # Highlighted text
    UNDERLINE = "UNDERLINE"                # Underlined text
    
    # Special
    ILLEGIBLE = "ILLEGIBLE"                # Unreadable section
    REDACTED = "REDACTED"                  # Redacted content
    BARCODE = "BARCODE"                    # Barcode/QR code
```

### 7.2 Layout Block Schema

```python
class OCRLayoutBlock(BaseModel):
    """Normalized layout block."""
    
    type: LayoutBlockType = Field(..., description="Block type (enum)")
    text: str = Field(..., description="Block text content")
    page: int = Field(..., ge=1, description="Page number (1-indexed)")
    
    # Optional spatial info
    bounding_box: Optional[Dict[str, int]] = Field(
        default=None,
        description={"x": int, "y": int, "width": int, "height": int}
    )
    
    # Confidence
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    
    # Parent-child relationships
    parent_block_id: Optional[str] = Field(default=None)
    child_block_ids: List[str] = Field(default_factory=list)
    
    # Reading order
    reading_order: int = Field(default=0, description="Order within page")
```

---

## 8. Deterministic Output Recommendations

### 8.1 Model Parameters

```yaml
# Recommended vLLM parameters for determinism
temperature: 0.0
top_p: 1.0
top_k: 1
presence_penalty: 0.0
frequency_penalty: 0.0
seed: 42  # If supported by vLLM
```

### 8.2 Prompt Engineering

**Add to System Prompt:**
```
You MUST use ONLY the following entity types (exact spelling, UPPERCASE):
{ENTITY_ENUM_LIST}

You MUST use ONLY the following layout block types (exact spelling, UPPERCASE):
{LAYOUT_ENUM_LIST}

If you encounter content that doesn't fit any type, use the closest matching
type rather than inventing new types.
```

### 8.3 Post-Processing Normalization

```python
class EntityNormalizer:
    """Normalize entity types to canonical forms."""
    
    ALIAS_MAP = {
        "symptom": "SYMPTOM",
        "SYMPTOMS": "SYMPTOM",
        "finding": "SIGN",
        "findings": "SIGN",
        "clinical_finding": "SIGN",
        "medication": "MEDICATION",
        "medications": "MEDICATION",
        "drug": "MEDICATION",
        "drugs": "MEDICATION",
        # ... full mapping
    }
    
    def normalize_type(self, raw_type: str) -> str:
        """Map raw type to canonical enum."""
        normalized = raw_type.upper().replace(" ", "_").replace("-", "_")
        return self.ALIAS_MAP.get(normalized, normalized)
```

### 8.4 Schema Validation Middleware

```python
class OCRValidationMiddleware:
    """Validate and normalize OCR responses."""
    
    def __init__(self, entity_enum, layout_enum):
        self.entity_enum = entity_enum
        self.layout_enum = layout_enum
        self.normalizer = EntityNormalizer()
    
    async def __call__(self, request, call_next):
        response = await call_next(request)
        
        if response.workflow == "ocr":
            # Validate entities
            for entity in response.result.get("entities", []):
                entity["type"] = self.normalizer.normalize_type(entity["type"])
                if entity["type"] not in self.entity_enum.__members__:
                    response.warnings.append(
                        f"Unknown entity type normalized: {entity['type']}"
                    )
            
            # Validate layout blocks
            for block in response.result.get("layout_blocks", []):
                block["type"] = self.normalizer.normalize_type(block["type"])
        
        return response
```

---

## 9. Client-Facing Explanation

---

**Subject: OCR Service Schema Stabilization and Architecture Update**

Dear Integration Partners,

We are writing to inform you of important improvements to our OCR service that will enhance consistency, reliability, and integration stability for all clients.

### Background

Our OCR service extracts text and structured data from medical documents. Recently, we identified inconsistencies in response formats that affected backend integrations:

1. **Entity type variations**: Similar clinical concepts were labeled differently (e.g., "symptom" vs "finding")
2. **Layout block variations**: Document sections were classified inconsistently
3. **Partial extraction results**: Some responses had incomplete structured data
4. **Repeated outputs**: Identical documents sometimes returned cached results

### Root Cause

These inconsistencies stemmed from two architectural decisions:

1. **Stateful Processing**: The service automatically cached and reused results for previously processed documents. While intended to improve performance, this made it difficult to ensure all clients received outputs using the latest schema standards.

2. **Flexible Schema Design**: To accommodate diverse medical document formats, we allowed the AI model to choose entity and layout type labels dynamically. This flexibility, while powerful, led to inconsistent labeling across similar documents.

### What's Changing

**1. Stateless Architecture (Effective: [Date])**

We are transitioning to a stateless processing model where each request is processed independently. Benefits include:

- **Consistent outputs**: Same document always produces same result format
- **Immediate schema updates**: All clients benefit from improvements immediately
- **Transparent processing**: Clear visibility into actual processing vs. cached results
- **Better debugging**: Easier to reproduce and resolve issues

**2. Canonical Entity and Layout Taxonomies (Effective: [Date])**

We are introducing standardized enumerations for all entity and layout types:

- **Entity types**: Fixed set including `SYMPTOM`, `SIGN`, `DIAGNOSIS`, `MEDICATION`, `DOSAGE`, `VITAL_SIGN`, `LAB_VALUE`, etc.
- **Layout types**: Fixed set including `HEADING`, `PARAGRAPH`, `TABLE`, `FORM_FIELD`, `SIGNATURE`, etc.

All type values will be UPPERCASE enum strings.

**3. Raw Text Clarification**

Important: The `raw_text` field contains the **complete verbatim transcription** of the document. It is NOT a fallback field—it is the primary OCR output. Structured fields (`entities`, `layout_blocks`) are secondary interpretations built on top of `raw_text`.

### Migration Timeline

| Date | Milestone |
|------|-----------|
| [Date + 2 weeks] | Deprecation notices in API responses |
| [Date + 4 weeks] | New schema available alongside legacy |
| [Date + 8 weeks] | Legacy schema deprecated (warnings only) |
| [Date + 12 weeks] | Legacy schema removed |

### Backward Compatibility

During the transition period:

- Existing integrations will continue to work
- We provide a type mapping table for deprecated aliases
- Our team is available to assist with migration

### Benefits for Your Integration

1. **Reliable backend mapping**: Consistent type values enable stable database schemas
2. **Predictable behavior**: No more surprise variations in response structure
3. **Better error handling**: Clear distinction between processing errors and data quality issues
4. **Improved audit trail**: Each response includes model/prompt versions for traceability

### Support

Our engineering team is available to assist with migration:

- Email: api-support@clinova.com
- Documentation: https://docs.clinova.com/ocr/v2
- Slack channel: #clinova-api-integrations

We appreciate your partnership as we improve the platform.

Best regards,  
Clinova AI Platform Team

---

## 10. Migration Recommendations

### 10.1 Phase 1: Preparation (Weeks 1-2)

**Tasks:**
1. Add `schema_version` field to all responses
2. Implement logging for entity/layout type distribution
3. Create alias mapping tables
4. Deploy monitoring dashboards

**Code Changes:**
```python
# Add schema version tracking
class OCRResult(BaseModel):
    schema_version: str = Field(default="1.0")  # Start with 1.0
    # ... existing fields
```

### 10.2 Phase 2: Dual-Write (Weeks 3-6)

**Tasks:**
1. Add normalization middleware
2. Return both legacy and canonical types during transition
3. Add deprecation warnings to response headers

**Implementation:**
```python
class OCRR esponseWithAliases(BaseModel):
    entities: List[OCREntityWithAlias]
    
class OCREntityWithAlias(BaseModel):
    text: str
    type: str  # Canonical (UPPERCASE)
    type_alias: Optional[str] = None  # Legacy (for backward compat)
```

### 10.3 Phase 3: Enforcement (Weeks 7-10)

**Tasks:**
1. Enable strict enum validation
2. Reject requests with invalid types (with clear error messages)
3. Remove legacy alias support

**Validation:**
```python
class StrictOCREntity(BaseModel):
    type: EntityType  # Enum, not str
    
    @field_validator('type')
    @classmethod
    def validate_type(cls, v):
        if isinstance(v, str):
            v = v.upper()
        if v not in EntityType.__members__:
            raise ValueError(f"Invalid entity type: {v}")
        return getattr(EntityType, v)
```

### 10.4 Phase 4: Stateless Migration (Weeks 11-14)

**Tasks:**
1. Disable automatic caching
2. Implement optional idempotency keys
3. Remove `ocr_reused` field
4. Update documentation

**Configuration:**
```python
# Disable caching in OCRDependencyResolver
class StatelessOCRResolver:
    def __init__(self, vllm_client, prompt_manager):
        self.vllm = vllm_client
        self.prompts = prompt_manager
        # NO cache initialization
    
    async def resolve(self, ...):
        # Always execute fresh
        return await self._execute_ocr(...)
```

### 10.5 Pydantic Models / JSON Schema

```python
# Complete production schema
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from enum import Enum
from datetime import datetime

class EntityType(str, Enum):
    SYMPTOM = "SYMPTOM"
    # ... full enum

class LayoutBlockType(str, Enum):
    HEADING = "HEADING"
    # ... full enum

class OCREntity(BaseModel):
    text: str
    type: EntityType
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    
class OCRLayoutBlock(BaseModel):
    type: LayoutBlockType
    text: str
    page: int = Field(ge=1)
    bounding_box: Optional[dict] = None
    
class OCRResponse(BaseModel):
    request_id: str
    document_id: str
    processed_at: datetime
    model_version: str
    prompt_version: str
    schema_version: Literal["2.0"]
    raw_text: str
    pages: int
    entities: List[OCREntity] = []
    layout_blocks: List[OCRLayoutBlock] = []
    confidence_score: Optional[float] = None
    quality_warnings: List[str] = []
    detected_language: str = "en"
    processing_errors: List[dict] = []
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{...}]  # Full example
        }
    )
```

### 10.6 OpenAPI Schema Improvements

```yaml
components:
  schemas:
    OCRResponse:
      type: object
      required:
        - request_id
        - document_id
        - processed_at
        - raw_text
        - pages
        - schema_version
      properties:
        schema_version:
          type: string
          enum: ["2.0"]
        entities:
          type: array
          items:
            $ref: '#/components/schemas/OCREntity'
    OCREntity:
      type: object
      required:
        - text
        - type
      properties:
        type:
          type: string
          enum:
            - SYMPTOM
            - SIGN
            - DIAGNOSIS
            # ... full list
```

### 10.7 Response Versioning Strategy

**URL Versioning:**
```
/api/v1/ocr  → Legacy (deprecated)
/api/v2/ocr  → New schema
```

**Header Versioning:**
```
Accept: application/vnd.clinova.ocr.v2+json
```

**Recommended:** URL versioning for clarity.

---

## 11. Risks & Edge Cases

### 11.1 Identified Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Breaking existing integrations** | HIGH | HIGH | Phased rollout with dual-write period |
| **Model cannot conform to enums** | MEDIUM | HIGH | Post-processing normalization layer |
| **Performance degradation (no cache)** | MEDIUM | MEDIUM | Optional idempotency cache, CDN caching |
| **Enum exhaustiveness gaps** | HIGH | MEDIUM | Regular review, add "OTHER" catch-all |
| **Legacy data migration** | MEDIUM | LOW | Provide transformation scripts |

### 11.2 Edge Cases

**Case 1: Unknown Entity Type**
```python
# Solution: Normalize to closest match or use OTHER
if normalized_type not in EntityType.__members__:
    # Try fuzzy matching
    closest = fuzzy_match(raw_type, EntityType.__members__)
    if closest:
        entity["type"] = closest
        response.warnings.append(f"Type '{raw_type}' mapped to '{closest}'")
    else:
        entity["type"] = "OTHER"
        response.warnings.append(f"Unknown type '{raw_type}' mapped to OTHER")
```

**Case 2: Multi-page Document with Mixed Layouts**
```python
# Solution: Per-page layout blocks with page numbers
for page_num, page_content in enumerate(pages, start=1):
    blocks = extract_layout(page_content)
    for block in blocks:
        block.page = page_num
```

**Case 3: Partial OCR Failure**
```python
# Solution: Include partial results with error details
if parse_failed:
    response.processing_errors.append({
        "code": "JSON_PARSE_ERROR",
        "message": "Model output was not valid JSON",
        "severity": "ERROR",
        "field": "entities"
    })
    response.entities = []  # Empty but valid
    response.raw_text = extracted_text  # Still useful
```

**Case 4: Handwritten Text**
```python
# Solution: Mark low-confidence regions
if handwriting_detected:
    block.confidence = 0.5  # Lower confidence
    response.quality_warnings.append({
        "code": "HANDWRITTEN_CONTENT",
        "message": "Handwritten text may have lower accuracy",
        "location": f"block[{idx}]"
    })
```

### 11.3 Rollback Strategy

**If issues arise:**
1. Flip feature flag to re-enable caching temporarily
2. Relax enum validation to accept legacy types
3. Route traffic back to v1 endpoint
4. Investigate and fix before re-enabling

---

## 12. Final Engineering Recommendations

### 12.1 Immediate Actions (This Sprint)

1. **Add schema versioning** to all OCR responses
2. **Implement logging** for entity/layout type distribution analysis
3. **Create alias mapping** from observed types to canonical types
4. **Document current caching behavior** for internal teams

### 12.2 Short-Term (Next 4 Weeks)

1. **Deploy normalization middleware** in shadow mode
2. **Add deprecation warnings** to API responses
3. **Implement strict enum validation** behind feature flag
4. **Create migration guide** for internal consumers

### 12.3 Medium-Term (Next 8 Weeks)

1. **Disable automatic caching** for new deployments
2. **Enable strict validation** for all traffic
3. **Remove legacy type support**
4. **Publish v2 API documentation**

### 12.4 Long-Term (Next 12 Weeks)

1. **Deprecate v1 API endpoint**
2. **Remove stateful code paths** entirely
3. **Implement optional idempotency** with explicit client opt-in
4. **Add confidence scoring** to all entities and blocks

### 12.5 Code Quality Recommendations

1. **Add comprehensive tests** for normalization logic
2. **Implement property-based testing** for schema validation
3. **Add integration tests** with real document samples
4. **Create synthetic test dataset** covering all entity/layout types

### 12.6 Monitoring Recommendations

1. **Track entity type distribution** over time
2. **Alert on unknown type occurrences**
3. **Monitor parsing error rates**
4. **Track cache hit rates** (during transition)
5. **Measure latency impact** of stateless processing

### 12.7 Compliance Considerations

For healthcare deployment:

1. **Audit logging**: Log all inputs, outputs, and transformations
2. **Data retention**: Define retention policy for OCR results
3. **PHI handling**: Ensure no PHI in logs/metrics
4. **Validation**: Document validation procedures for schema changes
5. **Change management**: Follow formal change control process

---

## Appendix A: Complete Schema Definition

```python
"""
Clinova Penthus AI Engine - Production OCR Schemas v2.0
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class EntityType(str, Enum):
    """Canonical entity types - exhaustive enumeration."""
    # Clinical Findings
    SYMPTOM = "SYMPTOM"
    SIGN = "SIGN"
    DIAGNOSIS = "DIAGNOSIS"
    DIFFERENTIAL_DIAGNOSIS = "DIFFERENTIAL_DIAGNOSIS"
    
    # Treatments
    MEDICATION = "MEDICATION"
    DOSAGE = "DOSAGE"
    ROUTE = "ROUTE"
    FREQUENCY = "FREQUENCY"
    DURATION = "DURATION"
    PROCEDURE = "PROCEDURE"
    SURGERY = "SURGERY"
    THERAPY = "THERAPY"
    
    # Patient Demographics
    PATIENT_NAME = "PATIENT_NAME"
    PATIENT_ID = "PATIENT_ID"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    AGE = "AGE"
    SEX = "SEX"
    GENDER = "GENDER"
    
    # Vital Signs
    VITAL_SIGN = "VITAL_SIGN"
    BLOOD_PRESSURE = "BLOOD_PRESSURE"
    HEART_RATE = "HEART_RATE"
    RESPIRATORY_RATE = "RESPIRATORY_RATE"
    TEMPERATURE = "TEMPERATURE"
    OXYGEN_SATURATION = "OXYGEN_SATURATION"
    WEIGHT = "WEIGHT"
    HEIGHT = "HEIGHT"
    BMI = "BMI"
    
    # Laboratory
    LAB_TEST = "LAB_TEST"
    LAB_VALUE = "LAB_VALUE"
    LAB_UNIT = "LAB_UNIT"
    LAB_REFERENCE_RANGE = "LAB_REFERENCE_RANGE"
    
    # Allergies
    ALLERGY = "ALLERGY"
    ALLERGY_REACTION = "ALLERGY_REACTION"
    
    # Administrative
    DATE = "DATE"
    TIME = "TIME"
    DATETIME = "DATETIME"
    PROVIDER_NAME = "PROVIDER_NAME"
    PROVIDER_ROLE = "PROVIDER_ROLE"
    FACILITY_NAME = "FACILITY_NAME"
    DEPARTMENT = "DEPARTMENT"
    PHONE_NUMBER = "PHONE_NUMBER"
    ADDRESS = "ADDRESS"
    EMAIL = "EMAIL"
    INSURANCE_ID = "INSURANCE_ID"
    MRN = "MRN"
    
    # Document Structure
    SECTION_HEADING = "SECTION_HEADING"
    TABLE_HEADER = "TABLE_HEADER"
    FOOTNOTE = "FOOTNOTE"
    SIGNATURE = "SIGNATURE"
    STAMP = "STAMP"
    
    # Other
    MEASUREMENT = "MEASUREMENT"
    IDENTIFIER = "IDENTIFIER"
    FOLLOW_UP_INSTRUCTION = "FOLLOW_UP_INSTRUCTION"
    CHIEF_COMPLAINT = "CHIEF_COMPLAINT"
    HISTORY_OF_PRESENT_ILLNESS = "HISTORY_OF_PRESENT_ILLNESS"
    PAST_MEDICAL_HISTORY = "PAST_MEDICAL_HISTORY"
    FAMILY_HISTORY = "FAMILY_HISTORY"
    SOCIAL_HISTORY = "SOCIAL_HISTORY"
    REVIEW_OF_SYSTEMS = "REVIEW_OF_SYSTEMS"
    PHYSICAL_EXAMINATION = "PHYSICAL_EXAMINATION"
    ASSESSMENT = "ASSESSMENT"
    PLAN = "PLAN"
    OTHER = "OTHER"


class LayoutBlockType(str, Enum):
    """Canonical layout block types."""
    # Text
    HEADING = "HEADING"
    SUBHEADING = "SUBHEADING"
    PARAGRAPH = "PARAGRAPH"
    LIST_ITEM = "LIST_ITEM"
    CAPTION = "CAPTION"
    
    # Structured
    TABLE = "TABLE"
    TABLE_ROW = "TABLE_ROW"
    TABLE_CELL = "TABLE_CELL"
    FORM_FIELD = "FORM_FIELD"
    FORM_LABEL = "FORM_LABEL"
    CHECKBOX = "CHECKBOX"
    RADIO_BUTTON = "RADIO_BUTTON"
    
    # Clinical
    VITALS_CHART = "VITALS_CHART"
    MEDICATION_LIST = "MEDICATION_LIST"
    PROBLEM_LIST = "PROBLEM_LIST"
    LAB_RESULTS_TABLE = "LAB_RESULTS_TABLE"
    
    # Document
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    PAGE_NUMBER = "PAGE_NUMBER"
    WATERMARK = "WATERMARK"
    
    # Signatures
    SIGNATURE = "SIGNATURE"
    SIGNATURE_LINE = "SIGNATURE_LINE"
    STAMP = "STAMP"
    SEAL = "SEAL"
    
    # Images
    IMAGE = "IMAGE"
    DIAGRAM = "DIAGRAM"
    GRAPH = "GRAPH"
    ECG_WAVEFORM = "ECG_WAVEFORM"
    
    # Annotations
    HANDWRITTEN_NOTE = "HANDWRITTEN_NOTE"
    HIGHLIGHT = "HIGHLIGHT"
    UNDERLINE = "UNDERLINE"
    
    # Special
    ILLEGIBLE = "ILLEGIBLE"
    REDACTED = "REDACTED"
    BARCODE = "BARCODE"


class OCREntity(BaseModel):
    """Extracted clinical entity with canonical type."""
    text: str = Field(..., description="Original text span")
    type: EntityType = Field(..., description="Canonical entity type")
    confidence: Optional[float] = Field(
        default=None, 
        ge=0.0, le=1.0,
        description="Extraction confidence score"
    )
    normalized_text: Optional[str] = Field(
        default=None,
        description="Normalized/canonical form of the text"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "text": "fever for 3 days",
                "type": "SYMPTOM",
                "confidence": 0.95,
                "normalized_text": "fever"
            }
        }
    }


class OCRLayoutBlock(BaseModel):
    """Document layout block with canonical type."""
    type: LayoutBlockType = Field(..., description="Canonical block type")
    text: str = Field(..., description="Block text content")
    page: int = Field(..., ge=1, description="Page number (1-indexed)")
    bounding_box: Optional[Dict[str, int]] = Field(
        default=None,
        description="Bounding box: {x, y, width, height}"
    )
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reading_order: int = Field(default=0, description="Reading order index")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "HEADING",
                "text": "CLINICAL NOTES",
                "page": 1,
                "bounding_box": {"x": 100, "y": 200, "width": 400, "height": 30},
                "confidence": 0.98,
                "reading_order": 1
            }
        }
    }


class ProcessingError(BaseModel):
    """Structured processing error."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable description")
    severity: Literal["ERROR", "WARNING", "INFO"] = Field(...)
    field: Optional[str] = Field(default=None, description="Affected field")
    page: Optional[int] = Field(default=None, ge=1)


class QualityWarning(BaseModel):
    """Quality indicator warning."""
    code: str = Field(..., description="Warning code")
    message: str = Field(..., description="Description")
    page: Optional[int] = Field(default=None, ge=1)
    location: Optional[str] = Field(default=None, description="Field/block path")


class OCRResponse(BaseModel):
    """
    Production-ready OCR response schema v2.0.
    
    This schema is designed for:
    - Deterministic outputs
    - Strong typing
    - Backward compatibility
    - Healthcare compliance
    """
    # Metadata
    request_id: str = Field(..., description="Unique request identifier")
    document_id: str = Field(..., description="Client-provided document ID")
    processed_at: datetime = Field(..., description="ISO 8601 timestamp")
    
    # Versioning
    model_version: str = Field(..., description="Model checkpoint version")
    prompt_version: str = Field(..., description="Prompt template version")
    schema_version: Literal["2.0"] = Field(default="2.0", description="Schema version")
    
    # Core OCR Output (source of truth)
    raw_text: str = Field(
        ..., 
        description="Complete verbatim transcription of the document"
    )
    pages: int = Field(..., ge=1, description="Number of pages processed")
    
    # Structured Layers (interpretations)
    entities: List[OCREntity] = Field(
        default_factory=list,
        description="Extracted clinical entities with canonical types"
    )
    layout_blocks: List[OCRLayoutBlock] = Field(
        default_factory=list,
        description="Document layout blocks with canonical types"
    )
    
    # Quality Indicators
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0, le=1.0,
        description="Overall OCR confidence score"
    )
    quality_warnings: List[QualityWarning] = Field(default_factory=list)
    
    # Language
    detected_language: str = Field(default="en", description="ISO 639-1 language code")
    
    # Errors
    processing_errors: List[ProcessingError] = Field(default_factory=list)
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "req_abc123",
                "document_id": "doc_123",
                "processed_at": "2025-01-15T10:30:00Z",
                "model_version": "penthus-1.2-alpha-4b",
                "prompt_version": "ocr.v2",
                "schema_version": "2.0",
                "raw_text": "Patient presents with fever for 3 days...",
                "pages": 1,
                "entities": [
                    {
                        "text": "fever",
                        "type": "SYMPTOM",
                        "confidence": 0.95
                    }
                ],
                "layout_blocks": [
                    {
                        "type": "HEADING",
                        "text": "CLINICAL NOTES",
                        "page": 1,
                        "reading_order": 1
                    }
                ],
                "confidence_score": 0.95,
                "quality_warnings": [],
                "detected_language": "en",
                "processing_errors": []
            }
        }
    }
```

---

*Report generated for Clinova Penthus AI Engine OCR Service*  
*Date: January 2025*  
*Version: 1.0*
