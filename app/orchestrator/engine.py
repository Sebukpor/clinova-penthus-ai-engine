"""
Clinova Penthus AI Engine - Clinical AI Orchestrator
Main orchestration engine for all clinical AI workflows.

Supports:
- Single image OCR (backward compatible)
- PDF documents (multi-page)
- TXT files
- Multiple documents in one request
"""
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.errors import UnsupportedWorkflowError, ValidationError
from app.core.logging import get_logger
from app.core.observability import (
    async_workflow_span,
    record_inference_log,
    record_tenant_request,
    record_validation_failure,
    record_workflow_error,
)
# Import the robust JSON repair functions
from app.llm.json_repair import parse_model_output, safe_json_loads, strip_thinking_tags
from app.llm.messages import build_messages
from app.llm.vllm_client import VLLMClient
from app.orchestrator.ocr_dependency import OCRDependencyResolver
from app.orchestrator.workflow_types import WorkflowType, get_workflow_config
from app.prompts.manager import PromptManager
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse, ModelInfo
from app.services.document_processor import (
    DocumentProcessor,
    DocumentProcessingError,
    get_document_processor,
)

logger = get_logger(__name__)


class ClinicalAIOrchestrator:
    """
    Main Clinical AI Orchestrator.
    """

    def __init__(
        self,
        vllm_client: VLLMClient,
        prompt_manager: PromptManager,
        ocr_resolver: OCRDependencyResolver,
        context_store=None,
        terminology_client=None,
        audit_service=None,
        inference_service=None,
        document_service=None,
        document_processor: Optional[DocumentProcessor] = None,
    ):
        self.vllm = vllm_client
        self.prompts = prompt_manager
        self.ocr = ocr_resolver
        self.context = context_store
        self.terminology = terminology_client
        self.audit = audit_service
        self.inference = inference_service
        self.document = document_service
        self.doc_processor = document_processor or get_document_processor()
        self.settings = get_settings()

    async def run(
        self,
        workflow: str,
        request: ClinicalRequest,
        request_id: str,
    ) -> ClinicalResponse:
        start_time = time.time()

        if workflow not in WorkflowType.all():
            raise UnsupportedWorkflowError(workflow, request_id=request_id)

        workflow_type = WorkflowType(workflow)
        config = get_workflow_config(workflow_type)

        logger.info(
            "workflow_start",
            workflow=workflow,
            request_id=request_id,
            tenant_id=request.tenant_id,
            encounter_id=request.encounter_id,
        )
        record_tenant_request(request.tenant_id, workflow)

        async with async_workflow_span(
            workflow=workflow,
            request_id=request_id,
            tenant_id=request.tenant_id,
            encounter_id=request.encounter_id,
        ) as span:
            # Step 1: Process input documents (PDF, TXT, multi-document)
            # This extends the existing image-based flow to support new document types
            processed_documents = await self._process_input_documents(request, request_id)
            
            # Step 2: Resolve OCR dependency if needed
            ocr_result = None
            ocr_reused = False
            raw_text = request.text
            
            # Check if we have processed documents that need OCR
            has_documents_for_ocr = bool(processed_documents and processed_documents.get("pages"))
            has_direct_text = bool(processed_documents and processed_documents.get("raw_text"))
            
            # Use processed text directly if available (TXT files)
            if has_direct_text:
                raw_text = processed_documents["raw_text"]
                logger.info(
                    "direct_text_used",
                    document_id=request.document_id,
                    text_length=len(raw_text),
                )
            
            # Run OCR for images or PDF pages
            elif config.requires_ocr and (request.image or has_documents_for_ocr):
                # Multi-page/document OCR processing
                if has_documents_for_ocr:
                    ocr_result, ocr_reused = await self._process_multi_page_ocr(
                        request=request,
                        pages=processed_documents["pages"],
                        request_id=request_id,
                        language=request.language,
                    )
                else:
                    # Legacy single-image flow (backward compatible)
                    content_hash = await self._get_or_compute_hash(request)
                    ocr_result, ocr_reused = await self.ocr.resolve(
                        tenant_id=request.tenant_id,
                        encounter_id=request.encounter_id,
                        document_id=request.document_id or request.encounter_id,
                        content_hash=content_hash,
                        image=request.image,
                        text=request.text,
                        language=request.language,
                        force_rerun=request.force_rerun_ocr,
                        request_id=request_id,
                        mime_type=request.mime_type,
                    )
                
                raw_text = ocr_result.get("raw_text", "") if ocr_result else request.text

            # Step 3: Build context state
            ctx = await self._load_context(request)
            if raw_text:
                ctx["raw_text"] = raw_text
            if ocr_result:
                ctx["ocr"] = ocr_result

            # Step 3: Execute workflow-specific logic
            result, warnings = await self._execute_workflow(
                workflow_type=workflow_type,
                config=config,
                request=request,
                ctx=ctx,
                raw_text=raw_text or "",
                ocr_result=ocr_result,
                request_id=request_id,
            )

            # Step 4: Update context
            await self._update_context(request, workflow, result)

            # Step 5: Log inference
            latency_ms = int((time.time() - start_time) * 1000)
            await self._log_inference(
                request=request,
                workflow=workflow,
                request_id=request_id,
                latency_ms=latency_ms,
            )

            # Step 6: Audit log
            await self._audit_log(
                request=request,
                workflow=workflow,
                request_id=request_id,
            )

            # Build response
            model_info = ModelInfo(
                repo_id="Sebukpor/medical-document-understanding-v2-fixed",
                prompt_version=f"{config.prompt_capability}.v1",
                model_version="penthus-1.2-alpha-4b",
            )

            return ClinicalResponse(
                request_id=request_id,
                tenant_id=request.tenant_id,
                encounter_id=request.encounter_id,
                document_id=request.document_id,
                workflow=workflow,
                model=model_info,
                result=result if isinstance(result, dict) else {"data": result},
                warnings=warnings,
                latency_ms=latency_ms,
                ocr_reused=ocr_reused,
            )

    async def _execute_workflow(
        self,
        workflow_type: WorkflowType,
        config,
        request: ClinicalRequest,
        ctx: Dict[str, Any],
        raw_text: str,
        ocr_result: Optional[Dict],
        request_id: str,
    ) -> tuple[Dict[str, Any], List[str]]:
        """Execute the specific workflow logic."""
        warnings: List[str] = []

        if workflow_type == WorkflowType.OCR:
            if not ocr_result and request.image:
                content_hash = await self._get_or_compute_hash(request)
                # FIX: Removed 'specialty' argument to match OCRDependencyResolver.resolve() signature
                ocr_result, _ = await self.ocr.resolve(
                    tenant_id=request.tenant_id,
                    encounter_id=request.encounter_id,
                    document_id=request.document_id or request.encounter_id,
                    content_hash=content_hash,
                    image=request.image,
                    text=request.text,
                    language=request.language,
                    force_rerun=request.force_rerun_ocr,
                    request_id=request_id,
                    mime_type=request.mime_type,
                )
            return (ocr_result or {"raw_text": raw_text or ""}, warnings)

        elif workflow_type == WorkflowType.SOAP:
            return await self._run_ai_workflow(
                "soap",
                {
                    "raw_text": raw_text,
                    "language": request.language,
                    "document_id": request.document_id,
                    "specialty": getattr(request.metadata, "specialty", "general") if request.metadata else "general",
                },
                request_id,
                request,
            )

        elif workflow_type == WorkflowType.ENTITIES:
            return await self._run_ai_workflow("entities", {"raw_text": raw_text, "language": request.language or "en"}, request_id, request)

        elif workflow_type == WorkflowType.NORMALIZATION:
            entities = ctx.get("entities", [])
            variables = {"entities": entities, "raw_text": raw_text}
            return await self._run_ai_workflow("normalization", variables, request_id, request)

        elif workflow_type == WorkflowType.SUMMARY:
            soap = ctx.get("soap", {})
            entities = ctx.get("entities", [])
            variables = {"soap": soap, "entities": entities, "raw_text": raw_text}
            return await self._run_ai_workflow("summary", variables, request_id, request)

        elif workflow_type == WorkflowType.GAPS:
            soap = ctx.get("soap", {})
            entities = ctx.get("entities", [])
            variables = {"soap": soap, "entities": entities, "raw_text": raw_text}
            return await self._run_ai_workflow("gaps", variables, request_id, request)

        elif workflow_type == WorkflowType.TRANSLATION:
            target = request.target_language or "en"
            variables = {
                "raw_text": raw_text,
                "source_language": request.language,
                "target_language": target,
            }
            return await self._run_ai_workflow("translation", variables, request_id, request)

        elif workflow_type == WorkflowType.SNOMED:
            return await self._run_terminology_workflow("SNOMED_CT", ctx, raw_text, request, request_id)

        elif workflow_type == WorkflowType.ICD:
            return await self._run_terminology_workflow("ICD11", ctx, raw_text, request, request_id)

        elif workflow_type == WorkflowType.FHIR:
            return await self._run_fhir_workflow(ctx, raw_text, request, request_id)

        else:
            raise UnsupportedWorkflowError(workflow_type.value, request_id=request_id)

    async def _run_ai_workflow(
        self,
        capability: str,
        variables: Dict[str, Any],
        request_id: str,
        request: ClinicalRequest,
    ) -> tuple[Dict[str, Any], List[str]]:
        """Run a direct AI model workflow."""
        warnings: List[str] = []

        prompt_data = self.prompts.render_prompt(
            capability=capability,
            variables=variables,
            version=request.prompt_override,
        )

        temperature = request.model_params.get("temperature", prompt_data["temperature"])
        max_tokens = request.model_params.get("max_tokens", prompt_data["max_tokens"])

        messages = build_messages(
            system=prompt_data["system"],
            user=prompt_data["user"],
        )

        response = await self.vllm.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            workflow=capability,
            request_id=request_id,
        )

        try:
            raw = response.content
            
            # FIX: Use the robust strip_thinking_tags function to handle unclosed tags, etc.
            raw = strip_thinking_tags(raw).strip()
            
            # Extract JSON from markdown fences if present
            fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
            if fence:
                raw = fence.group(1).strip()
                
            # FIX: Use robust JSON parsing (handles unescaped newlines, unbalanced braces, etc.)
            result = safe_json_loads(raw)
            
            if result is None:
                logger.warning(
                    f"{capability}_parse_fallback",
                    request_id=request_id,
                    raw_preview=raw[:500],
                )
                result = {"raw_text": response.content, "data": raw}
                
            return result, warnings

        except Exception as e:
            logger.error(
                f"{capability}_parse_error",
                error=str(e),
                request_id=request_id,
                exc_info=True,
            )
            record_validation_failure(capability)
            raise

    async def _run_terminology_workflow(
        self,
        system: str,
        ctx: Dict[str, Any],
        raw_text: str,
        request: ClinicalRequest,
        request_id: str,
    ) -> tuple[Dict[str, Any], List[str]]:
        """Run terminology mapping workflow (SNOMED CT or ICD-11)."""
        warnings: List[str] = []

        normalized_terms = ctx.get("normalized_terms", [])
        if not normalized_terms:
            norm_result, _ = await self._run_ai_workflow(
                "normalization",
                {"raw_text": raw_text, "entities": ctx.get("entities", [])},
                request_id,
                request,
            )
            normalized_terms = norm_result.get("normalized_terms", [])

        # FIX: Handle cases where normalized_terms might contain strings instead of dicts
        terms = [
            t.get("normalized_text", t.get("source_text", t)) if isinstance(t, dict) else str(t) 
            for t in normalized_terms if t
        ]

        candidates = []
        if self.terminology and terms:
            try:
                if system == "SNOMED_CT":
                    candidates = await self.terminology.search_snomed(terms)
                elif system == "ICD11":
                    soap = ctx.get("soap", {})
                    entities = ctx.get("entities", [])
                    candidates = await self.terminology.search_icd(terms, soap=soap, entities=entities)
            except Exception as e:
                logger.warning(
                    "terminology_gateway_error",
                    system=system,
                    error=str(e),
                    request_id=request_id,
                )
                warnings.append(f"Terminology gateway unavailable: {str(e)}. Returning normalized terms only.")

        result = {
            "query_terms": terms,
            "system": system,
            "normalized_terms": normalized_terms,
            "candidates": candidates,
            "ai_normalized": True,
            "terminology_service_available": len(candidates) > 0,
            "warning": warnings[0] if warnings else None,
        }
        
        if system == "SNOMED_CT":
            result["snomed_candidates"] = candidates
        elif system == "ICD11":
            result["icd_candidates"] = candidates

        return result, warnings

    async def _run_fhir_workflow(
        self,
        ctx: Dict[str, Any],
        raw_text: str,
        request: ClinicalRequest,
        request_id: str,
    ) -> tuple[Dict[str, Any], List[str]]:
        """Run FHIR resource generation workflow."""
        warnings: List[str] = []

        soap_raw = ctx.get("soap", {})
        if isinstance(soap_raw, str):
            soap = {}
        elif isinstance(soap_raw, dict):
            soap = soap_raw.get("data", soap_raw)
        else:
            soap = {}
            
        entities = ctx.get("entities", [])
        if isinstance(entities, dict):
            entities = entities.get("entities", [])
            
        normalized_terms = ctx.get("normalized_terms", [])
        if isinstance(normalized_terms, dict):
            normalized_terms = normalized_terms.get("normalized_terms", [])

        variables = {
            "soap": soap,
            "entities": entities,
            "normalized_terms": normalized_terms,
            "snomed_candidates": ctx.get("snomed_candidates", []),
            "icd_candidates": ctx.get("icd_candidates", []),
            "patient_id": getattr(request, "patient_id", None),
            "encounter_id": request.encounter_id,
        }

        result, ai_warnings = await self._run_ai_workflow("fhir", variables, request_id, request)
        warnings.extend(ai_warnings)

        if self.settings.fhir.validation_enabled:
            resources = result.get("resources", [])
            validated = []
            for res in resources:
                resource_type = res.get("resourceType", "")
                resource_data = res.get("resource", res)
                validated.append({
                    "resourceType": resource_type or resource_data.get("resourceType", "Unknown"),
                    "resource": resource_data,
                })
            result["resources"] = validated

        return result, warnings

    async def _load_context(self, request: ClinicalRequest) -> Dict[str, Any]:
        if not self.context:
            return {}
        return await self.context.get(
            tenant_id=request.tenant_id,
            encounter_id=request.encounter_id,
            document_id=request.document_id,
        )

    async def _update_context(self, request: ClinicalRequest, workflow: str, result: Dict[str, Any]) -> None:
        if not self.context:
            return
        try:
            await self.context.update(
                tenant_id=request.tenant_id,
                encounter_id=request.encounter_id,
                document_id=request.document_id,
                workflow=workflow,
                result=result,
            )
        except Exception as e:
            logger.warning("context_update_failed", error=str(e), workflow=workflow)

    async def _log_inference(self, request: ClinicalRequest, workflow: str,
                             request_id: str, latency_ms: int) -> None:
        if self.inference:
            try:
                await self.inference.log(
                    tenant_id=request.tenant_id,
                    request_id=request_id,
                    workflow=workflow,
                    model_repo="Sebukpor/medical-document-understanding-v2-fixed",
                    model_version="penthus-1.2-alpha-4b",
                    prompt_version=f"{workflow}.v1",
                    latency_ms=latency_ms,
                )
            except Exception as e:
                logger.warning("inference_log_failed", error=str(e))

    async def _audit_log(self, request: ClinicalRequest, workflow: str, request_id: str) -> None:
        if self.audit:
            try:
                await self.audit.log(
                    tenant_id=request.tenant_id,
                    action=f"workflow.{workflow}",
                    resource_type="clinical_workflow",
                    resource_id=request.encounter_id,
                    request_id=request_id,
                )
            except Exception as e:
                logger.warning("audit_log_failed", error=str(e))

    async def _get_or_compute_hash(self, request: ClinicalRequest) -> str:
        if request.document_id:
            return request.document_id
        if request.image:
            import hashlib
            data = request.image.encode() if isinstance(request.image, str) else request.image
            return hashlib.sha256(data).hexdigest()
        return hashlib.sha256(request.encounter_id.encode()).hexdigest()

    async def _process_input_documents(
        self,
        request: ClinicalRequest,
        request_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Process input documents (PDF, TXT, multi-document) into a unified format.
        
        This method handles:
        - Single file (file + file_type)
        - Multiple files (files + file_types)
        - Legacy image field (backward compatible)
        
        Returns:
            Dictionary with:
            - pages: List of page dictionaries with base64 images
            - raw_text: Extracted text (for TXT files)
            - document_count: Number of documents processed
            - page_count: Total number of pages
        """
        # Check for multi-document input first
        if request.files and len(request.files) > 0:
            return await self._process_multiple_documents(
                files=request.files,
                file_types=request.file_types or [],
                request_id=request_id,
                language=request.language,
            )
        
        # Check for single file input
        if request.file:
            return await self._process_single_document(
                content=request.file,
                mime_type=request.file_type,
                request_id=request_id,
                language=request.language,
            )
        
        # Legacy image field - return None to use existing flow
        # The existing image handling logic will process this
        return None

    async def _process_single_document(
        self,
        content: str,
        mime_type: Optional[str],
        request_id: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Process a single document (PDF, TXT, or image).
        
        Args:
            content: Base64-encoded content with data URI prefix
            mime_type: MIME type of the document
            request_id: Request correlation ID
            language: Document language
            
        Returns:
            Processed document dictionary
        """
        try:
            # Decode base64 content
            if ";base64," in content:
                mime_from_uri = content.split(";")[0].split(":")[1]
                base64_data = content.split(";base64,")[1]
            else:
                mime_from_uri = None
                base64_data = content
            
            import base64
            decoded_bytes = base64.b64decode(base64_data)
            
            # Use provided mime_type or extract from URI
            actual_mime = mime_type or mime_from_uri or "application/octet-stream"
            
            # Process using document processor
            result = await self.doc_processor.process_document(
                content=decoded_bytes,
                mime_type=actual_mime,
                document_id=request_id,
                language=language,
            )
            
            return {
                "pages": result.get("pages", []),
                "raw_text": result.get("raw_text", ""),
                "document_count": 1,
                "page_count": result.get("page_count", 0),
            }
            
        except DocumentProcessingError as e:
            logger.error(
                "single_document_processing_failed",
                error=e.message,
                document_type=e.document_type,
                request_id=request_id,
            )
            raise
        except Exception as e:
            logger.error(
                "single_document_processing_error",
                error=str(e),
                request_id=request_id,
            )
            raise DocumentProcessingError(
                f"Failed to process document: {str(e)}",
                document_type="unknown",
            )

    async def _process_multiple_documents(
        self,
        files: List[str],
        file_types: List[str],
        request_id: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Process multiple documents and merge results.
        
        Args:
            files: List of base64-encoded files
            file_types: List of MIME types
            request_id: Request correlation ID
            language: Document language
            
        Returns:
            Merged processed documents dictionary
        """
        all_pages = []
        all_texts = []
        total_pages = 0
        
        for idx, (file_content, file_type) in enumerate(zip(files, file_types or [None] * len(files))):
            try:
                doc_result = await self._process_single_document(
                    content=file_content,
                    mime_type=file_type,
                    request_id=f"{request_id}_doc{idx}",
                    language=language,
                )
                
                # Add pages with document index for tracking
                for page in doc_result.get("pages", []):
                    page["document_index"] = idx
                    all_pages.append(page)
                
                # Collect text from TXT files
                if doc_result.get("raw_text"):
                    all_texts.append(doc_result["raw_text"])
                
                total_pages += doc_result.get("page_count", 0)
                
            except DocumentProcessingError as e:
                logger.error(
                    "multi_document_page_failed",
                    document_index=idx,
                    error=e.message,
                    request_id=request_id,
                )
                # Continue processing other documents - don't fail entire request
        
        merged_text = "\n\n".join(all_texts) if all_texts else ""
        
        logger.info(
            "multiple_documents_processed",
            document_count=len(files),
            total_pages=total_pages,
            has_text=bool(merged_text),
            request_id=request_id,
        )
        
        return {
            "pages": all_pages,
            "raw_text": merged_text,
            "document_count": len(files),
            "page_count": total_pages,
        }

    async def _process_multi_page_ocr(
        self,
        request: ClinicalRequest,
        pages: List[Dict[str, Any]],
        request_id: str,
        language: str = "en",
    ) -> tuple[Optional[Dict[str, Any]], bool]:
        """
        Process OCR for multiple pages (from PDF or multi-document).
        
        Each page is processed independently through the existing OCR engine,
        then results are merged while preserving page order and document boundaries.
        
        Args:
            request: Clinical request
            pages: List of page dictionaries with base64 images
            request_id: Request correlation ID
            language: Document language
            
        Returns:
            Tuple of (merged OCR result, was_reused)
        """
        if not pages:
            return None, False
        
        ocr_reused = False
        page_texts = []
        all_entities = []
        
        logger.info(
            "multi_page_ocr_start",
            page_count=len(pages),
            request_id=request_id,
        )
        
        # Process each page through the existing OCR engine
        for page_idx, page_data in enumerate(pages):
            try:
                page_image = page_data.get("image")
                page_number = page_data.get("page_number", page_idx + 1)
                doc_index = page_data.get("document_index", 0)
                
                if not page_image:
                    logger.warning(
                        "page_missing_image",
                        page_idx=page_idx,
                        request_id=request_id,
                    )
                    continue
                
                # Create temporary document ID for caching per page
                temp_doc_id = f"{request.document_id or request.encounter_id}_page{page_number}_doc{doc_index}"
                
                # Compute hash for this specific page
                import hashlib
                content_hash = hashlib.sha256(page_image.encode()).hexdigest()
                
                # Call existing OCR resolver for this page
                page_ocr, page_reused = await self.ocr.resolve(
                    tenant_id=request.tenant_id,
                    encounter_id=request.encounter_id,
                    document_id=temp_doc_id,
                    content_hash=content_hash,
                    image=page_image,
                    text=None,
                    language=language,
                    force_rerun=request.force_rerun_ocr,
                    request_id=f"{request_id}_page{page_idx}",
                    mime_type=page_data.get("mime_type", "image/png"),
                )
                
                # Track if any page was reused from cache
                if page_reused:
                    ocr_reused = True
                
                # Extract text from this page
                if page_ocr:
                    page_text = page_ocr.get("raw_text", "")
                    if page_text:
                        # Add page header for structure preservation
                        header = f"=== DOCUMENT {doc_index + 1} : PAGE {page_number} ===\n"
                        page_texts.append(header + page_text)
                    
                    # Collect entities
                    page_entities = page_ocr.get("entities", [])
                    if page_entities:
                        all_entities.extend(page_entities)
                
            except Exception as page_error:
                logger.error(
                    "multi_page_ocr_page_failed",
                    page_idx=page_idx,
                    error=str(page_error),
                    request_id=request_id,
                )
                # Continue with next page - don't fail entire document
        
        # Merge all page texts while preserving structure
        merged_text = "\n\n".join(page_texts)
        
        logger.info(
            "multi_page_ocr_completed",
            pages_processed=len(page_texts),
            total_pages=len(pages),
            text_length=len(merged_text),
            ocr_reused=ocr_reused,
            request_id=request_id,
        )
        
        # Build merged OCR result
        ocr_result = {
            "document_id": request.document_id or request.encounter_id,
            "raw_text": merged_text,
            "entities": all_entities,
            "layout": {
                "pages": len(pages),
                "blocks": [],
            },
            "language": language,
            "multi_page": True,
            "page_count": len(pages),
        }
        
        return ocr_result, ocr_reused
