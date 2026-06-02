"""
Clinova Penthus AI Engine - FHIR Validator
Validates generated FHIR resources against R4 schema constraints.
"""

from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)


class FHIRValidator:
    """
    Validates FHIR R4 resources.

    Performs structural validation without requiring the fhir.resources library.
    Full profile validation should be done by a FHIR server.
    """

    VALID_RESOURCE_TYPES = {
        "Patient", "Encounter", "Observation", "Condition",
        "MedicationRequest", "AllergyIntolerance", "DiagnosticReport",
        "Composition", "Bundle", "Practitioner", "Organization",
        "Procedure", "Immunization", "DocumentReference",
    }

    REQUIRED_FIELDS = {
        "Patient": ["resourceType"],
        "Encounter": ["resourceType", "status", "class", "subject"],
        "Observation": ["resourceType", "status", "code", "subject"],
        "Condition": ["resourceType", "clinicalStatus", "verificationStatus", "code", "subject"],
        "MedicationRequest": ["resourceType", "status", "intent", "medicationCodeableConcept", "subject"],
        "AllergyIntolerance": ["resourceType", "clinicalStatus", "code", "patient"],
        "DiagnosticReport": ["resourceType", "status", "code", "subject"],
        "Composition": ["resourceType", "status", "type", "subject", "date", "author", "title"],
    }

    @classmethod
    def validate_resource(cls, resource: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate a single FHIR resource.

        Args:
            resource: FHIR resource dict

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        if not isinstance(resource, dict):
            return False, ["Resource must be a JSON object"]

        # Check resourceType
        resource_type = resource.get("resourceType")
        if not resource_type:
            return False, ["Missing required field: resourceType"]

        if resource_type not in cls.VALID_RESOURCE_TYPES:
            errors.append(f"Unknown or unsupported resource type: {resource_type}")

        # Check required fields
        required = cls.REQUIRED_FIELDS.get(resource_type, ["resourceType"])
        for field in required:
            if field not in resource:
                errors.append(f"Missing required field: {field}")

        # Validate references
        errors.extend(cls._validate_references(resource))

        return len(errors) == 0, errors

    @classmethod
    def validate_resources(cls, resources: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, List[str]]]:
        """
        Validate multiple FHIR resources.

        Args:
            resources: List of FHIR resource dicts

        Returns:
            Tuple of (all_valid, dict of resource_index -> errors)
        """
        all_errors = {}
        all_valid = True

        for i, resource in enumerate(resources):
            is_valid, errors = cls.validate_resource(resource)
            if not is_valid:
                all_valid = False
                all_errors[str(i)] = errors

        return all_valid, all_errors

    @classmethod
    def validate_bundle(cls, bundle: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate a FHIR Bundle.

        Args:
            bundle: FHIR Bundle dict

        Returns:
            Tuple of (is_valid, list of errors)
        """
        errors = []

        if bundle.get("resourceType") != "Bundle":
            return False, ["Not a Bundle resource"]

        if "type" not in bundle:
            errors.append("Bundle missing 'type' field")

        if "entry" not in bundle or not bundle["entry"]:
            errors.append("Bundle has no entries")

        if "entry" in bundle:
            for i, entry in enumerate(bundle["entry"]):
                resource = entry.get("resource", {})
                is_valid, res_errors = cls.validate_resource(resource)
                if not is_valid:
                    errors.extend([f"Entry {i}: {e}" for e in res_errors])

        return len(errors) == 0, errors

    @classmethod
    def _validate_references(cls, resource: Dict[str, Any], path: str = "") -> List[str]:
        """Recursively validate reference fields."""
        errors = []

        if isinstance(resource, dict):
            for key, value in resource.items():
                current_path = f"{path}.{key}" if path else key

                if key == "reference" and isinstance(value, str):
                    # Basic reference format check
                    if "/" not in value and not value.startswith("urn:uuid:"):
                        errors.append(f"Invalid reference format at {current_path}: {value}")

                elif isinstance(value, dict):
                    errors.extend(cls._validate_references(value, current_path))
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            errors.extend(cls._validate_references(item, f"{current_path}[{i}]"))

        return errors

    @classmethod
    def sanitize_resource(cls, resource: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize a FHIR resource by removing null values and fixing common issues.

        Args:
            resource: FHIR resource dict

        Returns:
            Sanitized resource dict
        """
        if not isinstance(resource, dict):
            return resource

        sanitized = {}
        for key, value in resource.items():
            if value is None:
                continue
            elif isinstance(value, dict):
                cleaned = cls.sanitize_resource(value)
                if cleaned:  # Only include non-empty dicts
                    sanitized[key] = cleaned
            elif isinstance(value, list):
                cleaned_list = [
                    cls.sanitize_resource(item) if isinstance(item, dict) else item
                    for item in value
                    if item is not None
                ]
                if cleaned_list:
                    sanitized[key] = cleaned_list
            else:
                sanitized[key] = value

        return sanitized
