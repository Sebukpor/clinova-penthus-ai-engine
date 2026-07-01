"""
Clinova Penthus AI Engine - JSON Repair
Utilities for parsing and repairing model JSON output with fallback strategies.
"""

import json
import re
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.errors import JSONRepairError, ModelOutputError
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


def extract_json_from_markdown(text: str) -> Optional[str]:
    """Extract JSON from markdown code blocks."""
    # Try fenced code block
    patterns = [
        r"```(?:json)?\s*\n?(.*?)\n?```",
        r"`\s*(\{.*?)\s*`",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
    return None


def extract_json_object(text: str) -> Optional[str]:
    """Extract the first JSON object from text."""
    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return None


def repair_json_common_issues(text: str) -> str:
    """Apply common JSON repair fixes."""
    repairs = [
        # Remove trailing commas
        (r",(\s*[}\]])", r"\1"),
        # Fix single quotes
        (r"(?<![\\])'", '"'),
        # Fix unquoted keys (simple cases)
        (r"(\w+):\s*", r'"\1": '),
        # Fix None/null
        (r":\s*None\s*([,}\]])", r': null\1'),
        # Fix True/true
        (r":\s*True\s*([,}\]])", r': true\1'),
        # Fix False/false
        (r":\s*False\s*([,}\]])", r': false\1'),
        # Remove Python-style comments
        (r"#.*$", "", re.MULTILINE),
        # Fix escaped newlines in strings
        (r"\\n", r"\n"),
    ]

    result = text
    for pattern, replacement, *flags in repairs:
        flag = flags[0] if flags else 0
        result = re.sub(pattern, replacement, result, flags=flag)

    return result


def safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    """Safely parse JSON with multiple fallback strategies."""
    if not text or not text.strip():
        return None

    text = text.strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from markdown
    extracted = extract_json_from_markdown(text)
    if extracted:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Extract JSON object
    obj_text = extract_json_object(text)
    if obj_text:
        try:
            return json.loads(obj_text)
        except json.JSONDecodeError:
            pass

        # Strategy 4: Repair common issues
        repaired = repair_json_common_issues(obj_text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    return None


def _strip_thinking(text: str) -> str:
    """Strip <think>...</think> block, return only JSON portion."""
    import re as _re
    close = _re.search(r"</think>", text, _re.IGNORECASE)
    if close:
        return text[close.end():].strip()
    if _re.search(r"<think>", text, _re.IGNORECASE):
        return ""
    return text


def parse_model_output(
    raw_output: str,
    schema_class: Type[T],
    request_id: Optional[str] = None,
    allow_repair: bool = True,
) -> T:
    """
    Parse model output into a validated Pydantic schema.

    Args:
        raw_output: Raw text output from the model
        schema_class: Pydantic model class to validate against
        request_id: Request ID for error context
        allow_repair: Whether to attempt JSON repair

    Returns:
        Validated schema instance

    Raises:
        ModelOutputError: If output cannot be parsed
        JSONRepairError: If repair is attempted but fails
    """
    # Strip thinking block before parsing
    raw_output = _strip_thinking(raw_output)
    # Try direct parsing
    parsed = safe_json_loads(raw_output)

    if parsed is not None:
        try:
            return schema_class(**parsed)
        except ValidationError as e:
            logger.warning(
                "schema_validation_failed_first_attempt",
                request_id=request_id,
                errors=e.errors(),
            )
            # Try to coerce types
            try:
                return _coerce_and_validate(parsed, schema_class)
            except ValidationError:
                pass

    # Repair fallback
    if allow_repair:
        logger.info("attempting_json_repair", request_id=request_id)
        repaired = repair_json_output(raw_output)
        if repaired:
            try:
                return schema_class(**repaired)
            except ValidationError as e:
                raise JSONRepairError(
                    message=f"JSON repair produced invalid output: {str(e)}",
                    details={"original": raw_output[:500], "repaired": str(repaired)[:500]},
                    request_id=request_id,
                )
        else:
            raise JSONRepairError(
                message="Could not extract or repair JSON from model output",
                details={"raw_preview": raw_output[:1000]},
                request_id=request_id,
            )

    raise ModelOutputError(
        message="Invalid model output: not valid JSON",
        details={"raw_preview": raw_output[:500]},
        request_id=request_id,
    )


def repair_json_output(raw_output: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to repair malformed JSON output from the model.
    Uses multiple strategies including LLM-based repair.
    """
    # Strategy 1: Extract and fix common issues
    cleaned = raw_output.strip()

    # Remove markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # Try to find JSON object boundaries
    json_text = extract_json_object(cleaned)
    if not json_text:
        return None

    # Apply repairs
    json_text = repair_json_common_issues(json_text)

    # Try parsing
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Line-by-line repair for truncated output
    try:
        return _repair_truncated_json(json_text)
    except json.JSONDecodeError:
        pass

    return None


def _repair_truncated_json(json_text: str) -> Dict[str, Any]:
    """Attempt to repair truncated JSON by closing open structures."""
    # Count open brackets/braces
    open_braces = json_text.count("{") - json_text.count("}")
    open_brackets = json_text.count("[") - json_text.count("]")

    repaired = json_text

    # Remove trailing comma if present
    repaired = re.sub(r",\s*$", "", repaired)

    # Close strings that are unterminated
    if repaired.count('"') % 2 != 0:
        # Find last unterminated string and close it
        repaired += '"'

    # Close open structures
    for _ in range(open_brackets):
        repaired += "]"
    for _ in range(open_braces):
        repaired += "}"

    return json.loads(repaired)


def _coerce_and_validate(data: Dict[str, Any], schema_class: Type[T]) -> T:
    """Attempt to coerce types to match schema."""
    # Get schema fields
    schema_fields = schema_class.model_fields

    coerced = {}
    for key, value in data.items():
        if key in schema_fields:
            field_info = schema_fields[key]
            annotation = field_info.annotation

            # Handle list fields that come as single values
            if hasattr(annotation, "__origin__") and annotation.__origin__ is list:
                if not isinstance(value, list):
                    value = [value] if value else []

            coerced[key] = value
        else:
            coerced[key] = value

    return schema_class(**coerced)
