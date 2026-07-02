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

def strip_thinking_tags(raw_output: str) -> str:
    """Removes  blocks and any preamble before the JSON."""
    # Remove closed  ...  blocks entirely
    cleaned = re.sub(r'<\s*think[^>]*>[\s\S]*?<\s*/\s*think\s*>', '', raw_output, flags=re.IGNORECASE)
    
    # If there's still an unclosed  tag, remove everything up to the first '{'
    if re.search(r'<\s*think[^>]*>', cleaned, flags=re.IGNORECASE):
        start_idx = cleaned.find('{')
        if start_idx != -1:
            cleaned = cleaned[start_idx:]
        else:
            # No JSON found, remove the unclosed  tag and everything after it
            cleaned = re.sub(r'<\s*think[^>]*>[\s\S]*', '', cleaned, flags=re.IGNORECASE)
            
    # Final check: find the first '{' to ensure we start with JSON
    start_idx = cleaned.find('{')
    if start_idx != -1:
        return cleaned[start_idx:]
        
    return cleaned

def fix_unescaped_newlines(text: str) -> str:
    """Replace literal newlines, tabs, and carriage returns inside JSON strings with their escaped equivalents."""
    def replacer(match):
        s = match.group(0)
        s = s.replace('\r', '\\r')
        s = s.replace('\n', '\\n')
        s = s.replace('\t', '\\t')
        return s
    
    # Match JSON string literals (handles escaped quotes inside)
    pattern = re.compile(r'"(?:\\.|[^"\\])*"', re.DOTALL)
    return pattern.sub(replacer, text)

def extract_json_from_markdown(text: str) -> Optional[str]:
    """Extract JSON from markdown code blocks."""
    patterns = [
        r"```(?:json)?\s*\n?(.*?)\n?```",
        r"`\s*(\{.*?)\s*`",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def extract_json_object(text: str) -> Optional[str]:
    """Extract the first JSON object from text."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return None

def repair_json_common_issues(text: str) -> str:
    """Apply common JSON repair fixes."""
    repairs = [
        (r",(\s*[}\]])", r"\1"),                     # Remove trailing commas
        (r"(?<!\\)'", '"'),                         # Fix single quotes
        (r'(\w+):\s*"', r'"\1": "'),                # Fix unquoted keys (naive)
        (r":\s*None(\s*[,}])", r': null\1'),        # Fix None → null
        (r":\s*True(\s*[,}])", r': true\1'),        # Fix True → true
        (r":\s*False(\s*[,}])", r': false\1'),      # Fix False → false
        (r"#.*$", "", re.MULTILINE),                # Remove Python comments
    ]
    result = text
    for item in repairs:
        if len(item) == 3:
            pattern, repl, flag = item
            result = re.sub(pattern, repl, result, flags=flag)
        else:
            pattern, repl = item
            result = re.sub(pattern, repl, result)
    return result

def _repair_truncated_json(json_text: str) -> Dict[str, Any]:
    """Attempt to repair truncated JSON by closing open structures."""
    open_braces = json_text.count("{") - json_text.count("}")
    open_brackets = json_text.count("[") - json_text.count("]")
    repaired = json_text
    repaired = re.sub(r",\s*$", "", repaired)
    if repaired.count('"') % 2 != 0:
        repaired += '"'
    for _ in range(open_brackets):
        repaired += "]"
    for _ in range(open_braces):
        repaired += "}"
    return json.loads(repaired)

def safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    """Safely parse JSON with multiple fallback strategies."""
    if not text or not text.strip():
        return None

    text = strip_thinking_tags(text).strip()
    if not text:
        return None

    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 1.5: Fix unescaped newlines inside strings (very common LLM issue)
    try:
        fixed_text = fix_unescaped_newlines(text)
        return json.loads(fixed_text)
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
        
        # Strategy 5: Repair truncated JSON (close unclosed braces/brackets)
        try:
            return _repair_truncated_json(repaired)
        except json.JSONDecodeError:
            pass

    return None

def _strip_thinking(text: str) -> str:
    """Strip  block, return only JSON portion."""
    return strip_thinking_tags(text)

def parse_model_output(
    raw_output: str,
    schema_class: Type[T],
    request_id: Optional[str] = None,
    allow_repair: bool = True,
) -> T:
    """
    Parse model output into a validated Pydantic schema.
    """
    raw_output = _strip_thinking(raw_output)
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
            try:
                return _coerce_and_validate(parsed, schema_class)
            except ValidationError:
                pass

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
    """Attempt to repair malformed JSON output from the model."""
    cleaned = raw_output.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)
    json_text = extract_json_object(cleaned)
    if not json_text:
        return None
    json_text = repair_json_common_issues(json_text)
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        pass
    try:
        return _repair_truncated_json(json_text)
    except json.JSONDecodeError:
        pass
    return None

def _coerce_and_validate(data: Dict[str, Any], schema_class: Type[T]) -> T:
    """Attempt to coerce types to match schema."""
    schema_fields = schema_class.model_fields
    coerced = {}
    for key, value in data.items():
        if key in schema_fields:
            field_info = schema_fields[key]
            annotation = field_info.annotation
            if hasattr(annotation, "__origin__") and annotation.__origin__ is list:
                if not isinstance(value, list):
                    value = [value] if value else []
        coerced[key] = value
    return schema_class(**coerced)