"""
Tests for Clinical AI Workflows
Verifies workflow orchestration, dependency resolution, and endpoint routing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.orchestrator.engine import ClinicalAIOrchestrator
from app.orchestrator.workflow_types import WorkflowType


@pytest.fixture
def mock_orchestrator():
    """Create a mocked orchestrator."""
    vllm = AsyncMock()
    vllm.chat_completion.return_value.content = '{"subjective": "test", "objective": "test", "assessment": "test", "plan": "test"}'

    prompts = MagicMock()
    prompts.render_prompt.return_value = {
        "system": "test system",
        "user": "test user",
        "temperature": 0.1,
        "max_tokens": 1200,
        "schema_ref": "TestResult",
        "prompt_version": "test.v1",
    }

    ocr = AsyncMock()
    ocr.resolve.return_value = (
        {"raw_text": "Patient has fever.", "entities": []},
        False,
    )

    return ClinicalAIOrchestrator(
        vllm_client=vllm,
        prompt_manager=prompts,
        ocr_resolver=ocr,
    ), vllm, prompts, ocr


class TestWorkflowExecution:
    """Test workflow execution patterns."""

    @pytest.mark.asyncio
    async def test_soap_resolves_ocr_first(self, mock_orchestrator):
        """SOAP endpoint resolves OCR before generating SOAP note."""
        orchestrator, vllm, prompts, ocr = mock_orchestrator

        from app.schemas.requests import ClinicalRequest
        request = ClinicalRequest(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            image="base64_image_data",
            language="en",
        )

        response = await orchestrator.run("soap", request, "req_001")

        # OCR should be called first
        ocr.resolve.assert_called_once()
        # Then vLLM for SOAP
        vllm.chat_completion.assert_called()
        assert response.workflow == "soap"

    @pytest.mark.asyncio
    async def test_entities_resolves_ocr_first(self, mock_orchestrator):
        """Entities endpoint resolves OCR before entity extraction."""
        orchestrator, vllm, prompts, ocr = mock_orchestrator
        vllm.chat_completion.return_value.content = '{"entities": [{"text": "fever", "type": "symptom"}]}'

        from app.schemas.requests import ClinicalRequest
        request = ClinicalRequest(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            image="base64_image_data",
            language="en",
        )

        response = await orchestrator.run("entities", request, "req_002")

        ocr.resolve.assert_called_once()
        vllm.chat_completion.assert_called()
        assert response.workflow == "entities"

    @pytest.mark.asyncio
    async def test_snomed_resolves_ocr_entities_normalization(self, mock_orchestrator):
        """SNOMED endpoint resolves OCR, entities, normalization, then calls terminology."""
        orchestrator, vllm, prompts, ocr = mock_orchestrator

        vllm.chat_completion.return_value.content = '{"normalized_terms": [{"source_text": "HTN", "normalized_text": "hypertension", "category": "diagnosis"}]}'

        # Add terminology client
        terminology = AsyncMock()
        terminology.search_snomed.return_value = [
            {"code": "38341003", "display": "Hypertensive disorder", "score": 0.94, "source": "snowstorm"}
        ]
        orchestrator.terminology = terminology

        from app.schemas.requests import ClinicalRequest
        request = ClinicalRequest(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            image="base64_image_data",
            language="en",
        )

        response = await orchestrator.run("snomed", request, "req_003")

        # OCR should be resolved
        ocr.resolve.assert_called_once()
        # Terminology should be called
        terminology.search_snomed.assert_called_once()
        assert response.workflow == "snomed"

    @pytest.mark.asyncio
    async def test_icd_resolves_dependencies(self, mock_orchestrator):
        """ICD endpoint resolves OCR, SOAP, entities, normalization, then calls terminology."""
        orchestrator, vllm, prompts, ocr = mock_orchestrator
        ocr.resolve.return_value = (
            {"raw_text": "Patient has hypertension.", "entities": [{"text": "hypertension", "type": "diagnosis"}]},
            True,
        )
        vllm.chat_completion.return_value.content = '{"normalized_terms": [{"source_text": "HTN", "normalized_text": "hypertension", "category": "diagnosis"}]}'

        terminology = AsyncMock()
        terminology.search_icd.return_value = [
            {"code": "BA00", "display": "Essential hypertension", "score": 0.92, "source": "icd11-api"}
        ]
        orchestrator.terminology = terminology

        from app.schemas.requests import ClinicalRequest
        request = ClinicalRequest(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            image="base64_image_data",
            language="en",
        )

        response = await orchestrator.run("icd", request, "req_004")

        ocr.resolve.assert_called_once()
        terminology.search_icd.assert_called_once()
        assert response.workflow == "icd"

    @pytest.mark.asyncio
    async def test_same_vllm_client_for_all_workflows(self, mock_orchestrator):
        """The same vLLM client is used for all AI workflows."""
        orchestrator, vllm, prompts, ocr = mock_orchestrator

        from app.schemas.requests import ClinicalRequest
        request = ClinicalRequest(
            tenant_id="tenant_001",
            encounter_id="enc_001",
            text="Patient has fever for 3 days.",
            language="en",
        )

        # Run multiple workflows
        await orchestrator.run("soap", request, "req_005")
        await orchestrator.run("entities", request, "req_006")
        await orchestrator.run("summary", request, "req_007")

        # All should use the same vLLM client instance
        assert vllm.chat_completion.call_count == 3

    def test_model_does_not_assign_final_codes(self):
        """The AI model normalizes terms but does not assign final clinical codes."""
        # This is an architecture rule - the model prompt explicitly instructs
        # not to assign codes. We verify through prompt content.
        from app.llm.messages import PenthusSystemPrompts

        snomed_prompt = PenthusSystemPrompts.get("snomed")
        icd_prompt = PenthusSystemPrompts.get("icd")
        normalization_prompt = PenthusSystemPrompts.get("normalization")

        assert "must NOT assign final" in normalization_prompt
        assert "does NOT assign" in snomed_prompt or "must NOT assign" in snomed_prompt
        assert "does NOT assign" in icd_prompt or "must NOT assign" in icd_prompt


class TestWorkflowTypes:
    """Test workflow type definitions."""

    def test_all_workflows_defined(self):
        """All required workflows are defined."""
        workflows = WorkflowType.all()
        required = ["ocr", "soap", "entities", "normalization", "summary",
                    "gaps", "translation", "snomed", "icd", "fhir"]
        for w in required:
            assert w in workflows

    def test_workflow_requires_ocr(self):
        """Correct workflows require OCR input."""
        assert WorkflowType.requires_ocr("soap")
        assert WorkflowType.requires_ocr("entities")
        assert WorkflowType.requires_ocr("fhir")
        assert WorkflowType.requires_ocr("snomed")
        assert WorkflowType.requires_ocr("icd")
        assert not WorkflowType.requires_ocr("translation")  # translation can work on text

    def test_terminology_workflows(self):
        """SNOMED and ICD are terminology workflows."""
        terminology_workflows = WorkflowType.terminology()
        assert "snomed" in terminology_workflows
        assert "icd" in terminology_workflows
