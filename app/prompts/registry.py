"""
Clinova Penthus AI Engine - Prompt Registry
YAML prompt file loading and validation.
"""

import os
from typing import Any, Dict

import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)


class PromptRegistry:
    """Registry for loading and validating prompt YAML files."""

    REQUIRED_FIELDS = ["id", "name", "capability", "model_repo", "schema_ref", "system", "template"]

    def load_prompt_file(self, filepath: str) -> Dict[str, Any]:
        """
        Load and validate a prompt YAML file.

        Args:
            filepath: Path to YAML file

        Returns:
            Validated prompt data dict

        Raises:
            ValueError: If file is invalid or missing required fields
        """
        if not os.path.exists(filepath):
            raise ValueError(f"Prompt file not found: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid prompt file format: {filepath}")

        # Validate required fields
        missing = [f for f in self.REQUIRED_FIELDS if f not in data]
        if missing:
            raise ValueError(f"Missing required fields in {filepath}: {missing}")

        # Set defaults
        data.setdefault("status", "active")
        data.setdefault("environment", "production")
        data.setdefault("response_format", "json")
        data.setdefault("temperature", 0.1)
        data.setdefault("max_tokens", 4096)
        data.setdefault("variables", [])
        data.setdefault("is_ocr_breaking", False)
        data.setdefault("created_by", "system")
        data.setdefault("metadata", {})

        # Extract version from id
        if "version" not in data and "." in data["id"]:
            parts = data["id"].rsplit(".", 1)
            if len(parts) == 2:
                data["version"] = parts[1]

        logger.debug("prompt_file_loaded", filepath=filepath, id=data["id"])
        return data

    def validate_prompt_schema(self, data: Dict[str, Any]) -> list[str]:
        """
        Validate prompt data and return list of issues.

        Args:
            data: Prompt data dict

        Returns:
            List of validation issue strings
        """
        issues = []

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in data:
                issues.append(f"Missing required field: {field}")

        # Check temperature range
        temp = data.get("temperature")
        if temp is not None and not (0 <= float(temp) <= 2):
            issues.append(f"Temperature {temp} out of range [0, 2]")

        # Check max_tokens
        max_tokens = data.get("max_tokens")
        if max_tokens is not None and int(max_tokens) < 1:
            issues.append(f"Invalid max_tokens: {max_tokens}")

        # Check template variables
        template = data.get("template", "")
        variables = data.get("variables", [])

        # Simple extraction of {{ var }} patterns
        import re
        used_vars = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", template))
        declared_vars = set(variables)

        undeclared = used_vars - declared_vars
        if undeclared:
            issues.append(f"Template uses undeclared variables: {undeclared}")

        return issues

    def list_prompt_files(self, directory: str) -> list[str]:
        """List all prompt YAML files in directory."""
        if not os.path.exists(directory):
            return []
        return [
            os.path.join(directory, f)
            for f in sorted(os.listdir(directory))
            if f.endswith((".yaml", ".yml"))
        ]
