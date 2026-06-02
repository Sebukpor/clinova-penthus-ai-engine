"""
Clinova Penthus AI Engine - Prompt Manager
Loads, manages, and selects prompt versions from YAML files and database.
"""

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.errors import PromptNotFoundError
from app.core.logging import get_logger
from app.prompts.registry import PromptRegistry
from app.prompts.renderer import PromptRenderer

logger = get_logger(__name__)


class PromptVersion:
    """Represents a loaded prompt version."""

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id", "")
        self.name = data.get("name", "")
        self.capability = data.get("capability", "")
        self.model_repo = data.get("model_repo", "")
        self.status = data.get("status", "draft")
        self.environment = data.get("environment", "development")
        self.response_format = data.get("response_format", "json")
        self.schema_ref = data.get("schema_ref", "")
        self.temperature = float(data.get("temperature", 0.1))
        self.max_tokens = int(data.get("max_tokens", 1200))
        self.system_message = data.get("system", "")
        self.template = data.get("template", "")
        self.variables = data.get("variables", [])
        self.is_ocr_breaking = data.get("is_ocr_breaking", False)
        self.created_by = data.get("created_by", "system")
        self.metadata = data.get("metadata", {})
        self._content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute hash of prompt content for cache invalidation."""
        content = f"{self.system_message}:{self.template}:{self.temperature}:{self.max_tokens}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @property
    def content_hash(self) -> str:
        """Return content hash for cache tracking."""
        return self._content_hash

    @property
    def prompt_key(self) -> str:
        """Return the prompt key (e.g., 'soap.v1')."""
        return self.id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "capability": self.capability,
            "model_repo": self.model_repo,
            "status": self.status,
            "environment": self.environment,
            "response_format": self.response_format,
            "schema_ref": self.schema_ref,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "system_message": self.system_message,
            "template": self.template,
            "variables": self.variables,
            "is_ocr_breaking": self.is_ocr_breaking,
            "content_hash": self.content_hash,
        }


class PromptManager:
    """
    Manages prompt versions from YAML files and database.
    Supports file-based bootstrapping and database-managed active versions.
    """

    def __init__(self, prompts_dir: Optional[str] = None):
        self.settings = get_settings()
        self.prompts_dir = prompts_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "..", "prompts"
        )
        self.prompts_dir = os.path.abspath(self.prompts_dir)
        self._registry = PromptRegistry()
        self._renderer = PromptRenderer()
        self._prompts: Dict[str, PromptVersion] = {}
        self._capability_map: Dict[str, str] = {}

    async def initialize(self) -> None:
        """Load prompts from YAML files."""
        logger.info("initializing_prompt_manager", prompts_dir=self.prompts_dir)

        if not os.path.exists(self.prompts_dir):
            logger.warning("prompts_directory_not_found", path=self.prompts_dir)
            return

        loaded = 0
        for filename in sorted(os.listdir(self.prompts_dir)):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                filepath = os.path.join(self.prompts_dir, filename)
                try:
                    prompt_data = self._registry.load_prompt_file(filepath)
                    prompt = PromptVersion(prompt_data)
                    self._prompts[prompt.id] = prompt
                    self._capability_map[prompt.capability] = prompt.id
                    loaded += 1
                    logger.debug("prompt_loaded", id=prompt.id, capability=prompt.capability)
                except Exception as e:
                    logger.error("prompt_load_failed", file=filename, error=str(e))

        logger.info("prompt_manager_initialized", loaded=loaded, total=len(self._prompts))

    def get_prompt(
        self,
        capability: str,
        version: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> PromptVersion:
        """
        Get prompt for a capability.

        Args:
            capability: Workflow capability (ocr, soap, entities, etc.)
            version: Specific version override (e.g., "v1")
            environment: Target environment (production, staging, development)

        Returns:
            PromptVersion instance

        Raises:
            PromptNotFoundError: If prompt not found
        """
        env = environment or self.settings.environment

        # Direct lookup by full key
        if version:
            prompt_key = f"{capability}.{version}"
            if prompt_key in self._prompts:
                prompt = self._prompts[prompt_key]
                if prompt.environment == env or prompt.status == "active":
                    logger.debug("prompt_found_by_key", key=prompt_key)
                    return prompt

        # Lookup by capability map
        if capability in self._capability_map:
            prompt_id = self._capability_map[capability]
            prompt = self._prompts.get(prompt_id)
            if prompt and (prompt.environment == env or prompt.status == "active"):
                logger.debug("prompt_found_by_capability", capability=capability, id=prompt_id)
                return prompt

        # Search for any active prompt for this capability
        for prompt in self._prompts.values():
            if prompt.capability == capability and prompt.status == "active":
                logger.debug("prompt_found_active", capability=capability, id=prompt.id)
                return prompt

        raise PromptNotFoundError(
            message=f"No prompt found for capability '{capability}' in environment '{env}'",
            details={"capability": capability, "version": version, "environment": env},
        )

    def render_prompt(
        self,
        capability: str,
        variables: Dict[str, Any],
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get and render a prompt template.

        Args:
            capability: Workflow capability
            variables: Template variables
            version: Optional version override

        Returns:
            Dict with 'system', 'user', 'temperature', 'max_tokens', 'schema_ref'
        """
        prompt = self.get_prompt(capability, version=version)
        user_content = self._renderer.render(prompt.template, variables)

        return {
            "system": prompt.system_message,
            "user": user_content,
            "temperature": prompt.temperature,
            "max_tokens": prompt.max_tokens,
            "schema_ref": prompt.schema_ref,
            "prompt_version": prompt.prompt_key,
            "prompt_hash": prompt.content_hash,
        }

    def list_prompts(self, capability: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available prompts."""
        prompts = []
        for prompt in self._prompts.values():
            if capability is None or prompt.capability == capability:
                prompts.append(prompt.to_dict())
        return prompts

    def get_prompt_info(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get prompt metadata."""
        prompt = self._prompts.get(prompt_id)
        return prompt.to_dict() if prompt else None

    def is_ocr_breaking_change(self, current_version: str, new_version: str) -> bool:
        """Check if version change is OCR-breaking."""
        current = self._prompts.get(current_version)
        new = self._prompts.get(new_version)
        if not current or not new:
            return True
        return new.is_ocr_breaking

    async def reload_prompts(self) -> None:
        """Reload all prompts from disk."""
        self._prompts.clear()
        self._capability_map.clear()
        await self.initialize()
