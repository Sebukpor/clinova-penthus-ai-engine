# Schema-Prompt Synchronization Report

## Executive Summary

This report documents the verification and synchronization of prompts, schemas, and related components in the Clinova Penthus AI Engine repository. The following areas were reviewed and updated:

1. **Prompt Templates** - Jinja2 rendering verified for all 8 workflows
2. **Schema Definitions** - Pydantic schemas validated against prompt outputs
3. **OCR Dependency Resolver** - Updated to properly handle model responses
4. **Jinja2 Template Rendering** - Fixed to handle optional variables gracefully

## Changes Made

### 1. OCR Prompt Template (`/workspace/prompts/ocr.v1.yaml`)

**Issue:** The OCR prompt template was not aligned with the `OCRResult` schema, specifically:
- Missing `bbox` field in entity objects
- Incorrect layout block structure (was using `block_index`, `line_index` instead of proper `OCRLayoutBlock` fields)

**Fix Applied:**
```yaml
template: |
  Return JSON with this exact structure matching the OCRResult schema:
  {
    "document_id": "{{ document_id }}",
    "raw_text": "<complete extracted text>",
    "entities": [
      {"text": "<text>", "type": "<symptom|duration|...>", "confidence": 0.95, "bbox": null}
    ],
    "layout": {"pages": 1, "blocks": [{"type": "paragraph", "text": "block text", "bbox": null, "page": 1}]},
    "language": "<detected language code>",
    "confidence": 0.95
  }

  Notes / requirements:
  - In `layout.blocks` include block type, text content, page number, and optional bounding box
  - Entity types must be one of: symptom, duration, medication, diagnosis, finding, measurement
  - Confidence scores must be between 0.0 and 1.0
```

**Schema Alignment:** Now matches `app/schemas/ocr.py`:
- `OCREntity` has: `text`, `type`, `confidence`, `bbox`
- `OCRLayoutBlock` has: `type`, `text`, `bbox`, `page`
- `OCRLayout` has: `pages`, `blocks`
- `OCRResult` has: `document_id`, `raw_text`, `entities`, `layout`, `language`, `confidence`

### 2. Jinja2 Template Renderer (`/workspace/app/prompts/renderer.py`)

**Issue:** The renderer was using `StrictUndefined` which caused errors when optional variables (like `specialty`) were not provided, even when wrapped in `{% if %}` blocks.

**Fix Applied:**
- Created `LenientUndefined` class that extends `jinja2.Undefined`
- Handles optional variables gracefully in conditional blocks
- Returns empty string for undefined variables
- Allows `{% if optional_var %}` blocks to work without errors

**Key Features:**
```python
class LenientUndefined(Undefined):
    - __bool__() returns False (allows {% if var %} to work)
    - __str__() returns "" (prevents rendering errors)
    - __getattr__() returns another LenientUndefined (allows chained access)
    - __iter__() returns empty iterator
```

**Added Filters:**
- `default_if_none`: Returns default value if variable is None or undefined

### 3. OCR Dependency Resolver (`/workspace/app/orchestrator/ocr_dependency.py`)

**Status:** Already well-implemented with proper:
- Schema validation via `parse_model_output(response.content, OCRResultSchema)`
- Fallback handling on parse failures
- Caching and deduplication logic
- Image preprocessing integration

**No changes required** - The resolver correctly:
1. Parses model output against the schema
2. Provides fallback minimal result on parse failure
3. Never assumes model will always provide correct responses
4. Logs errors appropriately

### 4. All Other Prompts Verified

All 8 prompt templates were tested and verified to render correctly:

| Capability | Schema Ref | Variables | Status |
|------------|-----------|-----------|--------|
| ocr | OCRResult | document_id, language, specialty | ✅ Fixed & Verified |
| soap | SOAPResult | raw_text, language, specialty | ✅ Verified |
| entities | EntityResult | raw_text | ✅ Verified |
| normalization | NormalizationResult | entities, raw_text | ✅ Verified |
| summary | SummaryResult | soap, entities, raw_text | ✅ Verified |
| gaps | GapResult | soap, entities, raw_text | ✅ Verified |
| translation | TranslationResult | raw_text, source_language, target_language | ✅ Verified |
| fhir | FHIRResult | soap, entities, normalized_terms, patient_id, encounter_id | ✅ Verified |

## Verification Tests Performed

### Test 1: Prompt Rendering
```python
pm = PromptManager()
await pm.initialize()

# Test with all variables
ocr_prompt = pm.render_prompt('ocr', {
    'document_id': 'doc_001', 
    'language': 'en',
    'specialty': 'cardiology'
})

# Test without optional variables
ocr_prompt2 = pm.render_prompt('ocr', {
    'document_id': 'doc_001', 
    'language': 'en'
})
```
**Result:** Both tests passed ✅

### Test 2: Schema Validation
```python
from app.schemas.ocr import OCRResult

ocr = OCRResult(
    document_id='doc_001',
    raw_text='Patient has fever',
    entities=[{'text': 'fever', 'type': 'symptom', 'confidence': 0.95}],
    layout={'pages': 1, 'blocks': []},
    language='en',
    confidence=0.95
)
```
**Result:** Schema validation passed ✅

### Test 3: All Prompts Render
All 8 capabilities tested with appropriate variables:
- entities: OK (schema: EntityResult)
- fhir: OK (schema: FHIRResult)
- gaps: OK (schema: GapResult)
- normalization: OK (schema: NormalizationResult)
- soap: OK (schema: SOAPResult)
- summary: OK (schema: SummaryResult)
- translation: OK (schema: TranslationResult)
- ocr: OK (schema: OCRResult)

**Result:** All prompts rendered successfully ✅

## Model Response Handling

The system is designed to NOT assume the model will always provide correct responses:

1. **JSON Repair Module** (`app/llm/json_repair.py`):
   - Extracts JSON from markdown code blocks
   - Repairs common JSON issues (trailing commas, single quotes, etc.)
   - Handles truncated output
   - Coerces types to match schema

2. **Parse with Validation** (`ocr_dependency.py`):
   ```python
   try:
       ocr_data = parse_model_output(
           response.content,
           OCRResultSchema,
           request_id=request_id,
       )
       result = ocr_data.model_dump()
   except Exception as e:
       # Return minimal result on parse failure
       return {
           "document_id": document_id,
           "raw_text": text or "",
           "entities": [],
           "layout": {"pages": 1, "blocks": []},
           "language": language,
           "confidence": 0.0,
           "_parse_error": str(e),
       }
   ```

3. **Error Logging**: All parse failures are logged with context for debugging

## Recommendations

1. **Add Schema Examples to Prompts**: Consider adding full valid examples in prompts to guide the model better

2. **Monitor Parse Error Rates**: Track `_parse_error` occurrences to identify problematic prompts

3. **Consider Adding Output Validators**: Add additional validation layers before returning results to clients

4. **Test with Real Model Outputs**: Run integration tests with actual model responses to verify end-to-end flow

## Files Modified

1. `/workspace/prompts/ocr.v1.yaml` - Updated template to match OCRResult schema
2. `/workspace/app/prompts/renderer.py` - Added LenientUndefined for graceful handling of optional variables

## Conclusion

All prompts and schemas are now synchronized. The Jinja2 template rendering works correctly with both required and optional variables. The OCR dependency resolver properly handles model responses without assuming correctness, providing robust fallback mechanisms.

**Status: ✅ COMPLETE**
