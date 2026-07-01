"""
Clinova Penthus AI Engine - Prompt Renderer
Jinja2-based prompt template rendering with PHI-safe variable handling.
"""

from typing import Any, Dict

from jinja2 import BaseLoader, Environment, Undefined

from app.core.logging import get_logger

logger = get_logger(__name__)


class LenientUndefined(Undefined):
    """Custom undefined that handles optional variables gracefully in conditional blocks."""
    
    def __init__(self, hint=None, obj=Undefined, name=None, exc=Undefined):
        super().__init__(hint, obj, name, exc)
    
    def __str__(self):
        return ""
    
    def __repr__(self):
        return f"LenientUndefined({self._undefined_name!r})"
    
    def __getattr__(self, name):
        # Allow attribute access on undefined objects (returns another undefined)
        return type(self)(hint=f"{self._undefined_hint}.{name}", name=name)
    
    def __getitem__(self, key):
        # Allow item access on undefined objects
        return self
    
    def __bool__(self):
        # Undefined is falsy - this allows {% if variable %} to work
        return False
    
    def __eq__(self, other):
        # Undefined equals only None or other Undefined
        return other is None or isinstance(other, LenientUndefined)
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __iter__(self):
        # Return empty iterator for undefined
        return iter([])
    
    def __len__(self):
        return 0


class PromptRenderer:
    """Renders prompt templates with variable substitution."""

    def __init__(self):
        # Use LenientUndefined to handle optional variables gracefully
        # This allows {% if optional_var %} blocks to work without errors
        self.env = Environment(
            loader=BaseLoader(),
            undefined=LenientUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )

        # Add custom filters
        self.env.filters["truncate"] = self._truncate_filter
        self.env.filters["bullet_list"] = self._bullet_list_filter
        self.env.filters["json"] = self._json_filter
        self.env.filters["default_if_none"] = self._default_filter

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

    @staticmethod
    def _default_filter(value: Any, default: Any = "") -> Any:
        """Return default if value is None or undefined."""
        return value if value is not None else default


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
