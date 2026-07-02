"""
Clinova Penthus AI Engine - OCR Dependency Resolver
Resolves OCR for workflows that need it, with caching and deduplication.
"""
import hashlib
import uuid
import re
import json
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.errors import OCRDependencyError
from app.core.logging import get_logger
from app.core.observability import record_ocr_cache_hit
from app.db.models import Document, Tenant, Encounter
from app.db.repositories import DocumentRepository
from app.llm.json_repair import safe_json_loads, strip_thinking_tags
from app.llm.messages import build_messages
from app.llm.vllm_client import VLLMClient
from app.prompts.manager import PromptManager
from app.schemas.ocr import OCRResult as OCRResultSchema
from app.services.image_preprocessor import get_preprocessor, PreprocessingMetadata

logger = get_logger(__name__)


class OCRDependencyResolver:
    """
    OCR Dependency Resolver
    """

    def __init__(
        self,
        vllm_client: VLLMClient,
        prompt_manager: PromptManager,
        db_repository=None,
        cache_client=None,
    ):
        self.vllm = vllm_client
        self.prompts = prompt_manager
        self.db = db_repository
        self.cache = cache_client
        self.settings = get_settings()
        self._local_cache: dict[str, Dict[str, Any]] = {}

    def _get_ocr_repo(self):
        if isinstance(self.db, dict):
            return self.db.get("ocr_results")
        return getattr(self.db, "ocr_results", None)

    def _get_doc_repo(self):
        if isinstance(self.db, dict):
            return self.db.get("documents")
        return getattr(self.db, "documents", None)

    def _cache_key(self, tenant_id: str, content_hash: str) -> str:
        return f"ocr:{tenant_id}:{content_hash}"

    @staticmethod
    def compute_content_hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _db_to_schema(db_result) -> Dict[str, Any]:
        return {
            "document_id": str(db_result.document_id),
            "raw_text": db_result.raw_text,
            "entities": db_result.entities,
            "layout": db_result.layout,
            "language": db_result.language,
        }

    async def resolve(
        self,
        tenant_id: str,
        encounter_id: str,
        document_id: str,
        content_hash: str,
        image: Optional[str] = None,
        text: Optional[str] = None,
        language: str = "en",
        force_rerun: bool = False,
        request_id: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], bool]:
        try:
            tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        except Exception:
            tenant_uuid = tenant_id

        try:
            doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id
        except Exception:
            doc_uuid = document_id

        local_key = self._cache_key(tenant_id, content_hash)
        if not force_rerun and local_key in self._local_cache:
            logger.debug("ocr_local_cache_hit", document_id=document_id, request_id=request_id)
            return self._local_cache[local_key], True

        if not force_rerun and self.db:
            existing = await self._get_ocr_repo().get_by_document(tenant_uuid, doc_uuid)
            if existing:
                logger.info("ocr_db_hit", document_id=document_id, request_id=request_id)
                record_ocr_cache_hit("db_hit")
                return self._db_to_schema(existing), True

        cache_key = self._cache_key(tenant_id, content_hash)
        if not force_rerun and self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info("ocr_cache_hit", document_id=document_id, request_id=request_id)
                record_ocr_cache_hit("hit")
                if self.db:
                    await self._persist_ocr(tenant_id, encounter_id, document_id, cached, request_id)
                return cached, True

        if not image and not text:
            raise OCRDependencyError(message="No image or text provided for OCR", request_id=request_id)

        logger.info("ocr_executing", document_id=document_id, has_image=bool(image), has_text=bool(text), request_id=request_id)
        record_ocr_cache_hit("miss")

        ocr_result = await self._execute_ocr(
            document_id=document_id,
            image=image,
            text=text,
            language=language,
            request_id=request_id,
            mime_type=mime_type,
        )

        if self.db:
            await self._persist_ocr(tenant_id, encounter_id, document_id, ocr_result, request_id)

        try:
            self._local_cache[local_key] = ocr_result
        except Exception:
            pass

        if self.cache:
            await self.cache.set(cache_key, ocr_result, ttl=self.settings.ocr.cache_ttl_seconds)

        return ocr_result, False

    async def _execute_ocr(
        self,
        document_id: str,
        image: Optional[str] = None,
        text: Optional[str] = None,
        language: str = "en",
        request_id: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        preprocessed_image = image
        preprocessing_metadata = None
        
        if image and mime_type:
            try:
                preprocessor = get_preprocessor()
                image_bytes = preprocessor.decode_from_base64(image)
                result = await preprocessor.preprocess(image_data=image_bytes, mime_type=mime_type)
                
                if result.success:
                    preprocessed_image = preprocessor.encode_to_base64(result.image_bytes)
                    preprocessing_metadata = result.metadata.to_dict()
                    logger.info("image_preprocessing_completed", document_id=document_id, metadata=preprocessing_metadata, request_id=request_id)
                else:
                    logger.warning("image_preprocessing_failed_continuing_with_original", document_id=document_id, error=result.error_message, request_id=request_id)
            except Exception as e:
                logger.error("image_preprocessing_error", document_id=document_id, error=str(e), request_id=request_id)
        
        prompt_data = self.prompts.render_prompt(
            capability="ocr",
            variables={"document_id": document_id, "language": language},
        )

        messages = build_messages(system=prompt_data["system"], user=prompt_data["user"])

        if preprocessed_image:
            from app.llm.messages import add_image_to_message
            user_msg = messages[-1]
            b64_data = preprocessed_image
            if ";base64," in preprocessed_image:
                b64_data = preprocessed_image.split(";base64,")[1]
            elif "," in preprocessed_image:
                b64_data = preprocessed_image.split(",")[1]
            add_image_to_message(user_msg, b64_data)

        response = await self.vllm.chat_completion(
            messages=messages,
            temperature=prompt_data.get("temperature", 0.0),
            max_tokens=prompt_data.get("max_tokens", 6096),
            top_p=prompt_data.get("top_p", 0.80),
            top_k=prompt_data.get("top_k", 10),
            presence_penalty=prompt_data.get("presence_penalty", 0.0),
            repetition_penalty=prompt_data.get("repetition_penalty", 1.03),
            workflow="ocr",
            request_id=request_id,
        )

        try:
            # 1. Strip  tags aggressively (handles unclosed tags too)
            raw_content = response.content
            cleaned_content = strip_thinking_tags(raw_content).strip()
            
            # 2. Use robust JSON parsing (handles trailing commas, unclosed braces, unescaped newlines)
            parsed_dict = safe_json_loads(cleaned_content)
            
            if parsed_dict is None:
                # If JSON parsing fails completely, use the cleaned text as raw_text
                transformed_result = {
                    "document_id": document_id,
                    "raw_text": cleaned_content,
                    "entities": [],
                    "layout": {"pages": 1, "blocks": []},
                    "language": language,
                }
            else:
                # DIRECT VALIDATION: The model already outputs the exact API schema
                transformed_result = parsed_dict
                
                # Ensure required fields are present and correct
                transformed_result["document_id"] = document_id
                if "language" not in transformed_result or not transformed_result["language"]:
                    transformed_result["language"] = language
                
                # Ensure entities and layout exist to satisfy Pydantic schema
                if "entities" not in transformed_result:
                    transformed_result["entities"] = []
                if "layout" not in transformed_result:
                    transformed_result["layout"] = {"pages": 1, "blocks": []}
                if "raw_text" not in transformed_result:
                    transformed_result["raw_text"] = ""
            
            # Direct Pydantic validation
            ocr_data = OCRResultSchema.model_validate(transformed_result)
            result = ocr_data.model_dump()
            result["document_id"] = document_id
            
            if preprocessing_metadata:
                result["preprocessing_metadata"] = preprocessing_metadata
            
            return result

        except Exception as e:
            logger.error("ocr_parse_failed", error=str(e), document_id=document_id, request_id=request_id)
            raw_preview = response.content[:2000] if response and hasattr(response, "content") else "No content"
            logger.error("ocr_raw_output_debug", raw_preview=raw_preview, request_id=request_id)
            
            # Fallback: Extract readable text from raw output instead of returning empty string
            fallback_text = strip_thinking_tags(response.content).strip()
            fallback_text = re.sub(r'```json\s*', '', fallback_text, flags=re.IGNORECASE)
            fallback_text = re.sub(r'```\s*', '', fallback_text, flags=re.IGNORECASE).strip()
            
            return {
                "document_id": document_id,
                "raw_text": fallback_text,
                "entities": [],
                "layout": {"pages": 1, "blocks": []},
                "language": language,
                "_parse_error": str(e),
                "preprocessing_metadata": preprocessing_metadata,
            }

    async def _persist_ocr(
        self,
        tenant_id: str,
        encounter_id: str,
        document_id: str,
        ocr_result: Dict[str, Any],
        request_id: Optional[str] = None,
    ) -> None:
        if not self.db:
            return

        try:
            tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        except Exception:
            tenant_uuid = tenant_id

        try:
            doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id
        except Exception:
            doc_uuid = document_id

        try:
            enc_uuid = uuid.UUID(encounter_id) if isinstance(encounter_id, str) else encounter_id
        except Exception:
            enc_uuid = encounter_id

        doc_repo = self._get_doc_repo()
        ocr_repo = self._get_ocr_repo()
        if not ocr_repo:
            logger.error("ocr_persist_failed", document_id=document_id, error="ocr_results repository unavailable")
            return

        session = getattr(doc_repo, "session", None) if doc_repo else None
        if session is None:
            session = getattr(ocr_repo, "session", None)

        if session is None or not hasattr(session, "begin_nested"):
            await self._persist_ocr_unsafe(tenant_uuid, enc_uuid, doc_uuid, ocr_repo, doc_repo, ocr_result, document_id, request_id)
            return

        try:
            async with session.begin_nested():
                # 1. Ensure Tenant exists (satisfies FK for Encounter)
                tenant = await session.get(Tenant, tenant_uuid)
                if not tenant:
                    tenant = Tenant(id=tenant_uuid, name=f"auto_stub_{str(tenant_uuid)[:8]}", status="active")
                    session.add(tenant)
                    await session.flush()

                # 2. Ensure Encounter exists (satisfies FK for Document)
                encounter = await session.get(Encounter, enc_uuid)
                if not encounter:
                    encounter = Encounter(
                        id=enc_uuid,
                        tenant_id=tenant_uuid,
                        patient_ref="auto_stub",
                        status="active"
                    )
                    session.add(encounter)
                    await session.flush()

                # 3. Ensure Document exists (satisfies FK for OCRResult)
                if doc_repo:
                    doc = await doc_repo.get_by_id(tenant_uuid, doc_uuid)
                    if not doc:
                        doc = Document(
                            id=doc_uuid,
                            tenant_id=tenant_uuid,
                            encounter_id=enc_uuid,
                            content_hash="auto_stub",
                            mime_type="image/jpeg",
                            object_uri="auto_stub",
                        )
                        session.add(doc)
                        await session.flush()

                # 4. Create OCR Result
                await ocr_repo.create(
                    tenant_id=tenant_uuid,
                    document_id=doc_uuid,
                    raw_text=ocr_result.get("raw_text", ""),
                    entities=ocr_result.get("entities", []),
                    layout=ocr_result.get("layout", {}),
                    language=ocr_result.get("language", "en"),
                    model_version="penthus-1.2-alpha-4b",
                    prompt_version="ocr.v1",
                )
                await session.flush()

            logger.debug("ocr_persisted", document_id=document_id, request_id=request_id)

        except IntegrityError as e:
            logger.warning(
                "ocr_persist_fk_violation",
                document_id=document_id,
                tenant_id=str(tenant_id),
                error=str(e.orig) if getattr(e, "orig", None) else str(e),
                request_id=request_id,
            )
        except Exception as e:
            logger.error("ocr_persist_failed", document_id=document_id, error=str(e), request_id=request_id)

    async def _persist_ocr_unsafe(
        self,
        tenant_uuid,
        enc_uuid,
        doc_uuid,
        ocr_repo,
        doc_repo,
        ocr_result: Dict[str, Any],
        document_id: str,
        request_id: Optional[str],
    ) -> None:
        try:
            session = getattr(doc_repo, "session", None) if doc_repo else getattr(ocr_repo, "session", None)
            if not session:
                return

            try:
                doc = Document(
                    id=doc_uuid,
                    tenant_id=tenant_uuid,
                    encounter_id=enc_uuid,
                    content_hash="auto_stub",
                    mime_type="image/jpeg",
                    object_uri="auto_stub",
                )
                session.add(doc)
                await session.flush()
            except IntegrityError:
                pass

            await ocr_repo.create(
                tenant_id=tenant_uuid,
                document_id=doc_uuid,
                raw_text=ocr_result.get("raw_text", ""),
                entities=ocr_result.get("entities", []),
                layout=ocr_result.get("layout", {}),
                language=ocr_result.get("language", "en"),
                model_version="penthus-1.2-alpha-4b",
                prompt_version="ocr.v1",
            )
            logger.debug("ocr_persisted", document_id=document_id, request_id=request_id)
        except Exception as e:
            logger.error("ocr_persist_failed", document_id=document_id, error=str(e), request_id=request_id)
            if session and hasattr(session, "rollback"):
                try: await session.rollback()
                except Exception: pass