"""
Clinova Penthus AI Engine - Clinical AI Orchestrator
Main orchestration engine for all clinical AI workflows.
"""

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
from app.llm.json_repair import parse_model_output
from app.llm.messages import build_messages
from app.llm.vllm_client import VLLMClient
from app.orchestrator.ocr_dependency import OCRDependencyResolver
from app.orchestrator.workflow_types import WorkflowType, get_workflow_config
from app.prompts.manager import PromptManager
from app.schemas.requests import ClinicalRequest
from app.schemas.responses import ClinicalResponse, ModelInfo

logger = get_logger(__name__)


class ClinicalAIOrchestrator:
    """
    Main Clinical AI Orchestrator.

    Coordinates all clinical AI workflows through a single vLLM model:
    - OCR (shared foundational layer)
    - SOAP generation
    - Entity extraction
    - Term normalization
    - Summary generation
    - Gap detection
    - Translation
    - SNOMED CT mapping (via terminology client)
    - ICD-11 coding (via terminology client)
    - FHIR resource generation
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
    ):
        self.vllm = vllm_client
        self.prompts = prompt_manager
        self.ocr = ocr_resolver
        self.context = context_store
        self.terminology = terminology_client
        self.audit = audit_service
        self.inference = inference_service
        self.document = document_service
        self.settings = get_settings()

    async def run(
        self,
        workflow: str,
        request: ClinicalRequest,
        request_id: str,
    ) -> ClinicalResponse:
        """
        Execute a clinical AI workflow.

        Args:
            workflow: Workflow type (ocr, soap, entities, etc.)
            request: Clinical request envelope
            request_id: Unique request identifier

        Returns:
            ClinicalResponse with results
        """
        start_time = time.time()

        # Validate workflow
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
        ):
            # Step 1: Resolve OCR dependency if needed
            ocr_result = None
            ocr_reused = False
            raw_text = request.text

            logger.info("DEBUG_OCR_CHECK", requires_ocr=config.requires_ocr, has_image=bool(request.image), image_len=len(request.image) if request.image else 0)
            if config.requires_ocr and request.image:
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

            # Step 2: Build context state
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
            return await self._run_ai_workflow("soap", {"raw_text": raw_text, "language": request.language, "document_id": request.document_id, "specialty": getattr(request, "specialty", "general")}, request_id, request)

        elif workflow_type == WorkflowType.ENTITIES:
            return await self._run_ai_workflow("entities", {"raw_text": raw_text, "language": request.language or "en"}, request_id, request)

        elif workflow_type == WorkflowType.NORMALIZATION:
            # Get entities first if available
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

        # Get prompt
        prompt_data = self.prompts.render_prompt(
            capability=capability,
            variables=variables,
            version=request.prompt_override,
        )

        # Override model params if provided
        temperature = request.model_params.get("temperature", prompt_data["temperature"])
        max_tokens = request.model_params.get("max_tokens", prompt_data["max_tokens"])

        # Build messages
        messages = build_messages(
            system=prompt_data["system"],
            user=prompt_data["user"],
        )

        # Call vLLM
        response = await self.vllm.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            workflow=capability,
            request_id=request_id,
        )

        # Parse result
        try:
            # Determine schema based on capability
            schema_map = {
                "soap": "SOAPResult",
                "entities": "EntityResult",
                "normalization": "NormalizationResult",
                "summary": "SummaryResult",
                "gaps": "GapResult",
                "translation": "TranslationResult",
            }
            schema_name = schema_map.get(capability, "dict")

            # Parse as generic dict for flexibility
            from app.llm.json_repair import safe_json_loads
            import re
            raw = response.content
            # Strip reasoning tags e.g. <think>...</think>
            raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
            # Extract JSON from markdown fences if present
            fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
            if fence:
                raw = fence.group(1).strip()
            result = safe_json_loads(raw)
            if result is None:
                # Last resort: return raw text as data
                result = {"raw_text": response.content, "data": raw}
            return result, warnings

        except Exception as e:
            logger.error(
                f"{capability}_parse_error",
                error=str(e),
                request_id=request_id,
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

        # Step 1: Normalize terms via AI
        normalized_terms = ctx.get("normalized_terms", [])
        if not normalized_terms:
            # Run normalization first
            norm_result, _ = await self._run_ai_workflow(
                "normalization",
                {"raw_text": raw_text, "entities": ctx.get("entities", [])},
                request_id,
                request,
            )
            normalized_terms = norm_result.get("normalized_terms", [])

        # Step 2: Call terminology gateway
        terms = [t.get("normalized_text", t.get("source_text", "")) for t in normalized_terms if t]

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
        # Store candidates by system key for FHIR to pick up from context
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

        # Get prerequisite data - normalize soap to dict
        soap_raw = ctx.get("soap", {})
        if isinstance(soap_raw, str):
            soap = {}
        elif isinstance(soap_raw, dict):
            # soap may be nested under "data" key
            soap = soap_raw.get("data", soap_raw)
        else:
            soap = {}
        entities = ctx.get("entities", [])
        if isinstance(entities, dict):
            entities = entities.get("entities", [])
        normalized_terms = ctx.get("normalized_terms", [])
        if isinstance(normalized_terms, dict):
            normalized_terms = normalized_terms.get("normalized_terms", [])

        # Build variables
        variables = {
            "soap": soap,
            "entities": entities,
            "normalized_terms": normalized_terms,
            "snomed_candidates": ctx.get("snomed_candidates", []),
            "icd_candidates": ctx.get("icd_candidates", []),
            "patient_id": request.patient_id,
            "encounter_id": request.encounter_id,
        }

        # Run AI workflow
        result, ai_warnings = await self._run_ai_workflow("fhir", variables, request_id, request)
        warnings.extend(ai_warnings)

        # Validate FHIR resources if enabled
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
        """Load clinical context for encounter."""
        if not self.context:
            return {}
        return await self.context.get(
            tenant_id=request.tenant_id,
            encounter_id=request.encounter_id,
            document_id=request.document_id,
        )

    async def _update_context(self, request: ClinicalRequest, workflow: str, result: Dict[str, Any]) -> None:
        """Update clinical context with workflow results."""
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
        """Log inference to audit trail."""
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
        """Write audit log entry."""
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
        """Get or compute content hash for a document."""
        if request.document_id:
            return request.document_id  # Use document_id as proxy for hash
        # Compute hash from image data
        if request.image:
            import hashlib
            data = request.image.encode() if isinstance(request.image, str) else request.image
            return hashlib.sha256(data).hexdigest()
        return hashlib.sha256(request.encounter_id.encode()).hexdigest()
