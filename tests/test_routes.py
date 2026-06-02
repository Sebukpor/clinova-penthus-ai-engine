"""
Tests for API Routes
Verifies endpoint routing, request validation, and response formats.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_application


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


class TestHealthEndpoints:
    """Test health and readiness endpoints."""

    def test_health_endpoint(self, client):
        """Health endpoint returns healthy status."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_root_endpoint(self, client):
        """Root endpoint returns app info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data


class TestRequestValidation:
    """Test request payload validation."""

    def test_missing_tenant_id(self, client):
        """Request without tenant_id is rejected."""
        response = client.post("/api/v1/soap", json={
            "encounter_id": "enc_001",
            "text": "Patient has fever.",
        })
        assert response.status_code == 422  # Validation error

    def test_missing_encounter_id(self, client):
        """Request without encounter_id is rejected."""
        response = client.post("/api/v1/soap", json={
            "tenant_id": "tenant_001",
            "text": "Patient has fever.",
        })
        assert response.status_code == 422

    def test_invalid_language_code(self, client):
        """Invalid language code is rejected."""
        response = client.post("/api/v1/soap", json={
            "tenant_id": "tenant_001",
            "encounter_id": "enc_001",
            "text": "Patient has fever.",
            "language": "invalid_language_code_that_is_way_too_long",
        })
        assert response.status_code == 422

    def test_empty_text_rejected(self, client):
        """Empty text field is rejected."""
        response = client.post("/api/v1/soap", json={
            "tenant_id": "tenant_001",
            "encounter_id": "enc_001",
            "text": "   ",
        })
        assert response.status_code == 422


class TestResponseFormat:
    """Test response envelope format."""

    @pytest.mark.asyncio
    async def test_response_includes_required_fields(self):
        """Response includes all required envelope fields."""
        from app.schemas.responses import ClinicalResponse, ModelInfo

        response = ClinicalResponse(
            request_id="req_001",
            tenant_id="tenant_001",
            encounter_id="enc_001",
            workflow="soap",
            model=ModelInfo(
                repo_id="Sebukpor/medical-document-understanding-v2-fixed",
                prompt_version="soap.v1",
                model_version="penthus-1.2-alpha-4b",
            ),
            result={"subjective": "test"},
            warnings=[],
            latency_ms=1200,
        )

        data = response.model_dump()
        assert "request_id" in data
        assert "tenant_id" in data
        assert "encounter_id" in data
        assert "workflow" in data
        assert "model" in data
        assert "result" in data
        assert "warnings" in data
        assert "latency_ms" in data
        assert "ocr_reused" in data
        assert data["model"]["repo_id"] == "Sebukpor/medical-document-understanding-v2-fixed"


class TestAllEndpointsExist:
    """Verify all required endpoints are registered."""

    def test_all_post_endpoints(self, client):
        """All POST endpoints return non-404 (may be 401/422 but not 404)."""
        endpoints = [
            "/api/v1/ocr",
            "/api/v1/soap",
            "/api/v1/entities",
            "/api/v1/normalization",
            "/api/v1/summary",
            "/api/v1/gaps",
            "/api/v1/translation",
            "/api/v1/snomed",
            "/api/v1/icd",
            "/api/v1/fhir",
        ]

        for endpoint in endpoints:
            # Empty body should get 422 (validation error), not 404
            response = client.post(endpoint, json={})
            assert response.status_code != 404, f"Endpoint {endpoint} not found"

    def test_all_get_endpoints(self, client):
        """All GET endpoints exist."""
        get_endpoints = [
            "/api/v1/health",
            "/api/v1/readiness",
            "/api/v1/metrics",
        ]

        for endpoint in get_endpoints:
            response = client.get(endpoint)
            assert response.status_code != 404, f"GET endpoint {endpoint} not found"
