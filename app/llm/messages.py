"""
Clinova Penthus AI Engine - Message Formatting
OpenAI-compatible message formatting for vLLM chat completions.
"""

from typing import Any, Dict, List, Optional


def system_message(content: str) -> Dict[str, str]:
    """Create a system message."""
    return {"role": "system", "content": content}


def user_message(content: str) -> Dict[str, str]:
    """Create a user message."""
    return {"role": "user", "content": content}


def assistant_message(content: str) -> Dict[str, str]:
    """Create an assistant message."""
    return {"role": "assistant", "content": content}


def build_messages(
    system: Optional[str] = None,
    user: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    few_shot: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """
    Build a message list for chat completion.

    Args:
        system: System prompt content
        user: User message content
        history: Previous conversation history
        few_shot: Few-shot examples as list of message dicts

    Returns:
        List of OpenAI-compatible message dicts
    """
    messages: List[Dict[str, str]] = []

    if system:
        messages.append(system_message(system))

    if few_shot:
        messages.extend(few_shot)

    if history:
        messages.extend(history)

    if user:
        messages.append(user_message(user))

    return messages


def add_image_to_message(
    message: Dict[str, Any],
    image_base64: str,
    detail: str = "auto",
) -> Dict[str, Any]:
    """
    Add an image to a user message for multimodal models.

    Args:
        message: Existing message dict
        image_base64: Base64-encoded image string
        detail: Image detail level (auto, low, high)

    Returns:
        Message dict with image content
    """
    if message.get("role") != "user":
        raise ValueError("Images can only be added to user messages")

    # Convert to multimodal content format
    text_content = message.get("content", "")
    message["content"] = [
        {"type": "text", "text": text_content},
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}",
                "detail": detail,
            },
        },
    ]

    return message


class PenthusSystemPrompts:
    """Standard system prompts for Penthus model."""

    DEFAULT = (
        "You are Penthus, the Clinova clinical documentation AI model. "
        "You process clinical documents, images, and text with high accuracy. "
        "Return only valid JSON matching the requested schema. "
        "Do not include explanations, markdown, or extra text outside the JSON."
    )

    OCR = (
        "You are Penthus, the Clinova clinical OCR and document understanding model. "
        "Extract all text from the provided clinical document image precisely. "
        "Preserve the document structure and identify clinical entities. "
        "Return only valid JSON. Do not include markdown formatting."
    )

    SOAP = (
        "You are Penthus, the Clinova clinical documentation model. "
        "Generate structured SOAP notes from clinical text. "
        "Be thorough, accurate, and follow clinical documentation standards. "
        "Return only valid JSON matching the SOAP schema."
    )

    ENTITIES = (
        "You are Penthus, the Clinova clinical entity extraction model. "
        "Identify and extract all clinical entities from the provided text. "
        "Classify each entity by type and provide confidence scores. "
        "Return only valid JSON."
    )

    NORMALIZATION = (
        "You are Penthus, the Clinova clinical normalization model. "
        "Normalize clinical terms to their standard canonical forms. "
        "You may normalize terms but must NOT assign final SNOMED CT, ICD-11, RxNorm, or LOINC codes. "
        "Code assignment is handled by external terminology services. "
        "Return only valid JSON."
    )

    SUMMARY = (
        "You are Penthus, the Clinova clinical summarization model. "
        "Generate concise, accurate clinical summaries from encounter data. "
        "Highlight key findings and recommend follow-up actions. "
        "Return only valid JSON."
    )

    GAPS = (
        "You are Penthus, the Clinova clinical documentation quality model. "
        "Analyze clinical documentation for missing information and quality issues. "
        "Suggest improvements to meet documentation standards. "
        "Return only valid JSON."
    )

    TRANSLATION = (
        "You are Penthus, the Clinova clinical translation model. "
        "Translate clinical text accurately while preserving medical terminology. "
        "Maintain the clinical meaning and context precisely. "
        "Return only valid JSON."
    )

    FHIR = (
        "You are Penthus, the Clinova FHIR generation model. "
        "Generate FHIR R4 resources from clinical encounter data. "
        "Follow HL7 FHIR specifications accurately. "
        "Return only valid JSON with FHIR resources."
    )

    SNOMED = (
        "You are Penthus, the Clinova clinical normalization model. "
        "Normalize clinical terms for SNOMED CT lookup. "
        "You normalize terms only - does NOT assign final SNOMED CT codes; final codes are assigned by external terminology services. "
        "Return only valid JSON with normalized terms."
    )

    ICD = (
        "You are Penthus, the Clinova clinical normalization model. "
        "Normalize clinical terms for ICD-11 coding. "
        "You normalize terms only - does NOT assign final ICD-11 codes; final codes are assigned by external terminology services. "
        "Return only valid JSON with normalized terms."
    )

    @classmethod
    def get(cls, capability: str) -> str:
        """Get system prompt for a capability."""
        prompts = {
            "ocr": cls.OCR,
            "soap": cls.SOAP,
            "entities": cls.ENTITIES,
            "normalization": cls.NORMALIZATION,
            "summary": cls.SUMMARY,
            "gaps": cls.GAPS,
            "translation": cls.TRANSLATION,
            "fhir": cls.FHIR,
            "snomed": cls.SNOMED,
            "icd": cls.ICD,
        }
        return prompts.get(capability, cls.DEFAULT)
