"""
Clinova Penthus AI Engine - FHIR Mapper
Maps clinical context to FHIR R4 resources.
"""

from typing import Any, Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class FHIRMapper:
    """
    Maps clinical context (SOAP, entities, normalized terms) to FHIR R4 resources.

    Supported resources:
    - Patient
    - Encounter
    - Observation
    - Condition
    - MedicationRequest
    - AllergyIntolerance
    - DiagnosticReport
    - Composition
    """

    FHIR_VERSION = "4.0.1"

    @classmethod
    def map_condition(
        cls,
        text: str,
        patient_ref: str,
        encounter_ref: str,
        codes: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Map to FHIR Condition resource."""
        resource = {
            "resourceType": "Condition",
            "id": cls._generate_id("cond"),
            "clinicalStatus": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }]
            },
            "verificationStatus": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": "confirmed",
                }]
            },
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                    "code": "encounter-diagnosis",
                }]
            }],
            "code": {
                "text": text,
            },
            "subject": {"reference": f"Patient/{patient_ref}"},
            "encounter": {"reference": f"Encounter/{encounter_ref}"},
        }

        if codes:
            resource["code"]["coding"] = codes

        return resource

    @classmethod
    def map_observation(
        cls,
        text: str,
        patient_ref: str,
        encounter_ref: str,
        category: str = "exam",
        value: Optional[str] = None,
        codes: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Map to FHIR Observation resource."""
        resource = {
            "resourceType": "Observation",
            "id": cls._generate_id("obs"),
            "status": "final",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": category,
                }]
            }],
            "code": {
                "text": text,
            },
            "subject": {"reference": f"Patient/{patient_ref}"},
            "encounter": {"reference": f"Encounter/{encounter_ref}"},
        }

        if codes:
            resource["code"]["coding"] = codes

        if value:
            resource["valueString"] = value

        return resource

    @classmethod
    def map_medication_request(
        cls,
        text: str,
        patient_ref: str,
        encounter_ref: str,
        dosage: Optional[str] = None,
        codes: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Map to FHIR MedicationRequest resource."""
        resource = {
            "resourceType": "MedicationRequest",
            "id": cls._generate_id("med"),
            "status": "active",
            "intent": "order",
            "medicationCodeableConcept": {
                "text": text,
            },
            "subject": {"reference": f"Patient/{patient_ref}"},
            "encounter": {"reference": f"Encounter/{encounter_ref}"},
        }

        if codes:
            resource["medicationCodeableConcept"]["coding"] = codes

        if dosage:
            resource["dosageInstruction"] = [{"text": dosage}]

        return resource

    @classmethod
    def map_encounter(
        cls,
        patient_ref: str,
        encounter_ref: str,
        status: str = "in-progress",
        encounter_class: str = "ambulatory",
    ) -> Dict[str, Any]:
        """Map to FHIR Encounter resource."""
        return {
            "resourceType": "Encounter",
            "id": encounter_ref,
            "status": status,
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": encounter_class,
            },
            "subject": {"reference": f"Patient/{patient_ref}"},
        }

    @classmethod
    def map_composition(
        cls,
        patient_ref: str,
        encounter_ref: str,
        sections: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Map to FHIR Composition resource for clinical notes."""
        composition_sections = []
        for section in sections:
            composition_sections.append({
                "title": section.get("title", "Section"),
                "code": {
                    "text": section.get("code", "section"),
                },
                "text": {
                    "status": "generated",
                    "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">{section.get('text', '')}</div>",
                },
            })

        return {
            "resourceType": "Composition",
            "id": cls._generate_id("comp"),
            "status": "final",
            "type": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "11506-3",
                    "display": "Progress note",
                }],
            },
            "subject": {"reference": f"Patient/{patient_ref}"},
            "encounter": {"reference": f"Encounter/{encounter_ref}"},
            "date": "__datetime__",
            "author": [{"reference": f"Practitioner/__author__"}],
            "title": "Clinical Note",
            "section": composition_sections,
        }

    @classmethod
    def map_allergy_intolerance(
        cls,
        text: str,
        patient_ref: str,
        criticality: str = "low",
    ) -> Dict[str, Any]:
        """Map to FHIR AllergyIntolerance resource."""
        return {
            "resourceType": "AllergyIntolerance",
            "id": cls._generate_id("all"),
            "clinicalStatus": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                    "code": "active",
                }]
            },
            "verificationStatus": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                    "code": "confirmed",
                }]
            },
            "type": "allergy",
            "criticality": criticality,
            "code": {"text": text},
            "patient": {"reference": f"Patient/{patient_ref}"},
        }

    @classmethod
    def _generate_id(cls, prefix: str) -> str:
        """Generate a FHIR resource ID."""
        import uuid
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    @classmethod
    def build_bundle(
        cls,
        resources: List[Dict[str, Any]],
        bundle_type: str = "transaction",
    ) -> Dict[str, Any]:
        """Build a FHIR Bundle from resources."""
        entries = []
        for resource in resources:
            entry = {
                "resource": resource,
                "request": {
                    "method": "POST",
                    "url": resource.get("resourceType", ""),
                },
            }
            if "id" in resource:
                entry["fullUrl"] = f"urn:uuid:{resource['id']}"
            entries.append(entry)

        return {
            "resourceType": "Bundle",
            "id": cls._generate_id("bundle"),
            "type": bundle_type,
            "entry": entries,
        }
