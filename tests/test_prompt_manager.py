"""
Tests for Prompt Manager
Verifies prompt loading, rendering, and version management.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.prompts.manager import PromptManager, PromptVersion
from app.prompts.registry import PromptRegistry
from app.prompts.renderer import PromptRenderer


class TestPromptRenderer:
    """Test prompt template rendering."""

    def test_basic_render(self):
        """Basic template rendering works."""
        renderer = PromptRenderer()
        result = renderer.render("Hello {{ name }}!", {"name": "Penthus"})
        assert result == "Hello Penthus!"

    def test_truncate_filter(self):
        """Truncate filter works on long text."""
        renderer = PromptRenderer()
        result = renderer.render(
            "{{ text | truncate(10) }}",
            {"text": "This is a very long text that should be truncated"}
        )
        assert len(result) <= 20  # "... [truncated]" added
        assert "..." in result

    def test_missing_variable_raises(self):
        """Missing required variable raises error."""
        renderer = PromptRenderer()
        with pytest.raises(Exception):
            renderer.render("Hello {{ missing }}!", {})


class TestPromptRegistry:
    """Test prompt file loading."""

    def test_validate_required_fields(self):
        """Validation catches missing required fields."""
        registry = PromptRegistry()

        incomplete = {"id": "test.v1", "name": "Test"}  # Missing many fields
        issues = registry.validate_prompt_schema(incomplete)
        assert len(issues) > 0
        assert any("Missing required field" in i for i in issues)

    def test_validate_valid_prompt(self):
        """Valid prompt passes validation."""
        registry = PromptRegistry()

        valid = {
            "id": "test.v1",
            "name": "Test Prompt",
            "capability": "test",
            "model_repo": "test/repo",
            "schema_ref": "TestResult",
            "system": "You are a test model",
            "template": "Test: {{ variable }}",
            "variables": ["variable"],
        }
        issues = registry.validate_prompt_schema(valid)
        assert len(issues) == 0


class TestPromptManager:
    """Test prompt manager functionality."""

    def test_prompt_version_creation(self):
        """PromptVersion object is created correctly."""
        data = {
            "id": "soap.v1",
            "name": "SOAP Generation",
            "capability": "soap",
            "model_repo": "test/repo",
            "status": "active",
            "environment": "production",
            "response_format": "json",
            "schema_ref": "SOAPResult",
            "temperature": 0.1,
            "max_tokens": 1200,
            "system": "You are a test",
            "template": "Generate SOAP: {{ raw_text }}",
            "variables": ["raw_text"],
            "created_by": "system",
        }
        pv = PromptVersion(data)
        assert pv.id == "soap.v1"
        assert pv.capability == "soap"
        assert pv.temperature == 0.1
        assert pv.content_hash is not None

    def test_prompt_hash_consistency(self):
        """Same content produces same hash."""
        data = {
            "id": "test.v1",
            "name": "Test",
            "capability": "test",
            "model_repo": "test/repo",
            "schema_ref": "TestResult",
            "system": "System prompt",
            "template": "Template {{ var }}",
            "created_by": "system",
        }
        pv1 = PromptVersion(data)
        pv2 = PromptVersion(data)
        assert pv1.content_hash == pv2.content_hash

    @pytest.mark.asyncio
    async def test_get_prompt_by_capability(self, tmp_path):
        """Prompt can be retrieved by capability."""
        # Create a test prompt file
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        prompt_file = prompts_dir / "test.v1.yaml"
        prompt_file.write_text("""
id: test.v1
name: Test Prompt
capability: test
capability: test
model_repo: test/repo
schema_ref: TestResult
system: You are a test model
template: "Test: {{ variable }}"
variables:
  - variable
status: active
environment: production
created_by: test
""")

        pm = PromptManager(prompts_dir=str(prompts_dir))
        await pm.initialize()

        prompt = pm.get_prompt("test")
        assert prompt is not None
        assert prompt.capability == "test"

    @pytest.mark.asyncio
    async def test_get_prompt_not_found(self, tmp_path):
        """Getting non-existent prompt raises error."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        pm = PromptManager(prompts_dir=str(prompts_dir))
        await pm.initialize()

        from app.core.errors import PromptNotFoundError
        with pytest.raises(PromptNotFoundError):
            pm.get_prompt("nonexistent")

    def test_is_ocr_breaking(self):
        """OCR-breaking change detection works."""
        data1 = {
            "id": "ocr.v1",
            "name": "OCR v1",
            "capability": "ocr",
            "model_repo": "test/repo",
            "schema_ref": "OCRResult",
            "system": "System",
            "template": "Template",
            "is_ocr_breaking": False,
            "created_by": "test",
        }
        data2 = dict(data1)
        data2["is_ocr_breaking"] = True

        pv1 = PromptVersion(data1)
        pv2 = PromptVersion(data2)

        assert not pv1.is_ocr_breaking
        assert pv2.is_ocr_breaking
