"""
Clinova Penthus AI Engine - Prompt Renderer
Jinja2-based prompt template rendering with PHI-safe variable handling.
"""

from typing import Any, Dict

from jinja2 import BaseLoader, Environment, StrictUndefined

from app.core.logging import get_logger

logger = get_logger(__name__)


class PromptRenderer:
    """Renders prompt templates with variable substitution."""

    def __init__(self):
        # Use StrictUndefined to catch missing variables early
        self.env = Environment(
            loader=BaseLoader(),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )

        # Add custom filters
        self.env.filters["truncate"] = self._truncate_filter
        self.env.filters["bullet_list"] = self._bullet_list_filter
        self.env.filters["json"] = self._json_filter

    def render(self, template_str: str, variables: Dict[str, Any]) -> str:
        """
        Render a template with variables.

        Args:
            template_str: Jinja2 template string
            variables: Variables to substitute

        Returns:
            Rendered string
        """
        try:
            template = self.env.from_string(template_str)
            return template.render(**variables)
        except Exception as e:
            logger.error(
                "prompt_render_error",
                error=str(e),
                missing_vars=getattr(e, "name", "unknown"),
            )
            raise

    @staticmethod
    def _truncate_filter(value: str, length: int = 500) -> str:
        """Truncate text to specified length."""
        if not value:
            return ""
        if len(value) <= length:
            return value
        return value[:length] + "..."

    @staticmethod
    def _bullet_list_filter(value: list) -> str:
        """Convert list to bullet list string."""
        if not value:
            return ""
        return "\n".join(f"- {item}" for item in value)

    @staticmethod
    def _json_filter(value: Any) -> str:
        """Convert value to JSON string."""
        import json
        return json.dumps(value, indent=2)


class SafeVariableExtractor:
    """Extracts and validates prompt variables without exposing PHI."""

    SAFE_VARIABLES = {
        "language", "specialty", "source", "workflow", "prompt_version",
        "model_version", "schema_ref", "target_language", "source_language",
    }

    @classmethod
    def extract_audit_vars(cls, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Extract only non-PHI variables for audit logging."""
        return {
            k: v for k, v in variables.items()
            if k in cls.SAFE_VARIABLES or not cls._contains_phi(k)
        }

    @staticmethod
    def _contains_phi(key: str) -> bool:
        """Check if a variable key might contain PHI."""
        phi_indicators = [
            "text", "raw", "note", "content", "patient", "name",
            "mrn", "ssn", "dob", "address", "phone",
        ]
        key_lower = key.lower()
        return any(indicator in key_lower for indicator in phi_indicators)
