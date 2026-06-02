"""
Tests for vLLM Client
Verifies retry logic, timeout handling, and response parsing.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.vllm_client import VLLMClient
from app.core.errors import VLLMTimeoutError, VLLMError


class TestVLLMClient:
    """Test vLLM client functionality."""

    @pytest.fixture
    def client(self):
        with patch.dict("os.environ", {
            "VLLM_BASE_URL": "http://test-vllm:8000/v1",
            "VLLM_MODEL": "penthus-test",
            "VLLM_TIMEOUT_SECONDS": "10",
            "VLLM_MAX_RETRIES": "2",
        }):
            return VLLMClient()

    @pytest.mark.asyncio
    async def test_chat_completion_success(self, client):
        """Successful chat completion returns parsed response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"result": "test"}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "model": "penthus-test",
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        client.client = AsyncMock()
        client.client.post.return_value = mock_response

        response = await client.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            workflow="test",
        )

        assert response.content == '{"result": "test"}'
        assert response.input_tokens == 100
        assert response.output_tokens == 50

    @pytest.mark.asyncio
    async def test_chat_completion_timeout(self, client):
        """Timeout raises VLLMTimeoutError."""
        client.client = AsyncMock()
        client.client.post.side_effect = httpx.TimeoutException("Connection timed out")

        with pytest.raises(VLLMTimeoutError):
            await client.chat_completion(
                messages=[{"role": "user", "content": "test"}],
                workflow="test",
                request_id="req_001",
            )

    @pytest.mark.asyncio
    async def test_chat_completion_http_error(self, client):
        """HTTP error raises VLLMError."""
        client.client = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )
        client.client.post.return_value = mock_response

        with pytest.raises(VLLMError):
            await client.chat_completion(
                messages=[{"role": "user", "content": "test"}],
                workflow="test",
            )

    @pytest.mark.asyncio
    async def test_health_check_success(self, client):
        """Health check returns True when service is up."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"object": "list"}

        client.client = AsyncMock()
        client.client.get.return_value = mock_response

        healthy = await client.health_check()
        assert healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, client):
        """Health check returns False when service is down."""
        client.client = AsyncMock()
        client.client.get.side_effect = httpx.ConnectError("Connection refused")

        healthy = await client.health_check()
        assert healthy is False

    @pytest.mark.asyncio
    async def test_client_close(self, client):
        """Client can be closed."""
        client.client = AsyncMock()
        await client.close()
        client.client.aclose.assert_called_once()

    def test_vllm_response_creation(self):
        """VLLMResponse object stores values correctly."""
        from app.llm.vllm_client import VLLMResponse
        response = VLLMResponse(
            content='{"test": true}',
            model="penthus-1.2-alpha-4b",
            input_tokens=100,
            output_tokens=50,
            finish_reason="stop",
            latency_ms=1200.0,
        )
        assert response.content == '{"test": true}'
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.latency_ms == 1200.0
