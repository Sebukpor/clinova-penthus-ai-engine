"""
Clinova Penthus AI Engine - JSON Repair
Utilities for parsing and repairing model JSON output with fallback strategies.
"""
import json
import re
from typing import Any, Dict, Optional, Type, TypeVar

# Third-party deep-structural JSON repair library (aliased to avoid any
# confusion with this module's own name — this is NOT a self-import).
# Handles mid-document bracket/array mismatches that our own regex-based
# strategies below can't fix (e.g. an array closed early, causing
# subsequent object siblings to land illegally inside array context).
import json_repair as json_repair_lib

from pydantic import BaseModel, ValidationError
from app.core.errors import JSONRepairError, ModelOutputError
from app.core.logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)

def strip_thinking_tags(raw_output: str) -> str:
    """
    Removes  blocks and any preamble before the JSON.
    Since the model reliably ends thinking with , we split on that tag 
    and take everything after it. This prevents thinking text containing 
    literal '{' characters from being mistakenly parsed as JSON.
    """
    # 1. Find the closing  tag (case-insensitive, allows whitespace)
    close_match = re.search(r'</\s*think\s*>', raw_output, flags=re.IGNORECASE)
    
    if close_match:
        # Take everything AFTER the closing tag
        cleaned = raw_output[close_match.end():].strip()
    else:
        # Fallback: If no closing tag exists, remove the opening tag and everything before the first '{'
        cleaned = re.sub(r'<\s*think[^>]*>[\s\S]*', '', raw_output, flags=re.IGNORECASE)
        start_idx = cleaned.find('{')
        if start_idx != -1:
            cleaned = cleaned[start_idx:]
            
    # 2. Remove any markdown code fences that might wrap the JSON
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()

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

def fix_unbalanced_braces(text: str) -> str:
    """
    Remove extra closing braces/brackets that appear outside of any open structure.
    This fixes cases where the LLM outputs extra '}' or ']' by mistake.
    """
    result = []
    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape_next = False
    
    for char in text:
        if escape_next:
            result.append(char)
            escape_next = False
            continue
            
        if char == '\\':
            result.append(char)
            escape_next = True
            continue
            
        if char == '"':
            in_string = not in_string
            result.append(char)
            continue
            
        if in_string:
            result.append(char)
            continue
            
        if char == '{':
            depth_brace += 1
            result.append(char)
        elif char == '}':
            if depth_brace > 0:
                depth_brace -= 1
                result.append(char)
            # else: extra brace, drop it
        elif char == '[':
            depth_bracket += 1
            result.append(char)
        elif char == ']':
            if depth_bracket > 0:
                depth_bracket -= 1
                result.append(char)
            # else: extra bracket, drop it
        else:
            result.append(char)
            
    return "".join(result)

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

def repair_with_library(text: str, request_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Deep structural repair via the third-party json_repair library.

    Use this as a fallback of last resort AFTER the cheap regex-based
    strategies below. It is much more capable than our own bracket-counting
    logic at fixing mid-document structural errors — e.g. an array closed
    early, causing subsequent object key/value pairs to land illegally
    inside array context (as opposed to simple trailing-comma or
    unclosed-structure-at-EOF issues, which the cheaper strategies already
    handle fine on their own).
    """
    try:
        result = json_repair_lib.loads(text)
    except Exception as e:
        logger.warning(
            "json_repair_library_failed",
            request_id=request_id,
            error=str(e),
        )
        return None

    if isinstance(result, dict):
        logger.info("json_repair_library_recovered", request_id=request_id)
        return result

    # json_repair.loads can return non-dict types (list, str, etc.) if the
    # text wasn't really a JSON object at all -- treat that as a failure
    # for our purposes rather than silently returning something the caller
    # doesn't expect.
    logger.warning(
        "json_repair_library_non_dict_result",
        request_id=request_id,
        result_type=type(result).__name__,
    )
    return None

def safe_json_loads(text: str, request_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
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

    # Strategy 2: Extract JSON object boundaries
    obj_text = extract_json_object(text)
    if obj_text:
        try:
            return json.loads(obj_text)
        except json.JSONDecodeError:
            pass
        
        # Strategy 3: Repair common issues
        repaired = repair_json_common_issues(obj_text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass
        
        # Strategy 4: Repair truncated JSON (close unclosed braces/brackets)
        try:
            return _repair_truncated_json(repaired)
        except json.JSONDecodeError:
            pass
            
        # Strategy 5: Fix unbalanced braces/brackets (extra closing braces)
        try:
            fixed_braces = fix_unbalanced_braces(repaired)
            return json.loads(fixed_braces)
        except json.JSONDecodeError:
            pass

        # Strategy 6: Deep structural repair via json_repair library.
        # Catches mid-document bracket/array mismatches (e.g. an array
        # closed early with sibling key/value pairs left dangling outside
        # any object) that the strategies above cannot fix, since they only
        # operate on trailing/edge issues or global open/close counts.
        lib_repaired = repair_with_library(obj_text, request_id=request_id)
        if lib_repaired is not None:
            return lib_repaired

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
    parsed = safe_json_loads(raw_output, request_id=request_id)
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
        repaired = repair_json_output(raw_output, request_id=request_id)
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

def repair_json_output(raw_output: str, request_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
    try:
        fixed_braces = fix_unbalanced_braces(json_text)
        return json.loads(fixed_braces)
    except json.JSONDecodeError:
        pass

    # Deep structural repair via json_repair library -- last resort before
    # giving up entirely and raising JSONRepairError upstream.
    lib_repaired = repair_with_library(json_text, request_id=request_id)
    if lib_repaired is not None:
        return lib_repaired

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