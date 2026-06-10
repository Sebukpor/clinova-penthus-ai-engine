"""
Clinova Penthus AI Engine - OCR Dependency Resolver
Resolves OCR for workflows that need it, with caching and deduplication.
"""

import hashlib
import uuid
from typing import Any, Dict, Optional, Tuple

from app.core.config import get_settings
from app.core.errors import OCRDependencyError
from app.core.logging import get_logger
from app.core.observability import record_ocr_cache_hit
from app.llm.json_repair import parse_model_output
from app.llm.messages import build_messages
from app.llm.vllm_client import VLLMClient
from app.prompts.manager import PromptManager
from app.schemas.ocr import OCRResult as OCRResultSchema
from app.services.image_preprocessor import get_preprocessor, PreprocessingMetadata

logger = get_logger(__name__)


class OCRDependencyResolver:
    """
    OCR Dependency Resolver

    Rules:
    1. If document_id has existing OCR in PostgreSQL, reuse it.
    2. If PostgreSQL miss but Redis has valid cache, reuse and persist.
    3. If neither, execute OCR prompt through vLLM.
    4. Persist OCR output.
    5. Update encounter context.
    6. Never execute OCR twice for same content hash unless forced.
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
        # In-memory deduplication cache for same-content requests during process lifetime
        self._local_cache: dict[str, Dict[str, Any]] = {}

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
        """
        Resolve OCR for a document.

        Args:
            tenant_id: Tenant identifier
            encounter_id: Encounter identifier
            document_id: Document identifier
            content_hash: SHA-256 hash of document content
            image: Base64 image or object storage URI
            text: Optional text (for text-only OCR)
            language: Document language
            force_rerun: Force OCR re-execution
            request_id: Request correlation ID
            mime_type: MIME type of the image (e.g., "image/png")

        Returns:
            Tuple of (OCR result dict, was_reused boolean)
        """
        # Accept either UUID objects or arbitrary string tenant/document IDs used in tests.
        try:
            tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        except Exception:
            tenant_uuid = tenant_id

        try:
            doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id
        except Exception:
            doc_uuid = document_id

        # Local deduplication: if we've already processed this content in this process, reuse it
        local_key = self._cache_key(tenant_id, content_hash)
        if not force_rerun and local_key in self._local_cache:
            logger.debug("ocr_local_cache_hit", document_id=document_id, request_id=request_id)
            return self._local_cache[local_key], True

        # 1. Check PostgreSQL for existing OCR result
        if not force_rerun and self.db:
            existing = await self.db.ocr_results.get_by_document(tenant_uuid, doc_uuid)
            if existing:
                logger.info(
                    "ocr_db_hit",
                    document_id=document_id,
                    request_id=request_id,
                )
                record_ocr_cache_hit("db_hit")
                return self._db_to_schema(existing), True

        # 2. Check Redis cache
        cache_key = self._cache_key(tenant_id, content_hash)
        if not force_rerun and self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info(
                    "ocr_cache_hit",
                    document_id=document_id,
                    request_id=request_id,
                )
                record_ocr_cache_hit("hit")
                # Persist to DB
                if self.db:
                    await self._persist_ocr(tenant_id, document_id, cached, request_id)
                return cached, True

        # 3. Execute OCR via vLLM
        if not image and not text:
            raise OCRDependencyError(
                message="No image or text provided for OCR",
                request_id=request_id,
            )

        logger.info(
            "ocr_executing",
            document_id=document_id,
            has_image=bool(image),
            has_text=bool(text),
            request_id=request_id,
        )
        record_ocr_cache_hit("miss")

        ocr_result = await self._execute_ocr(
            document_id=document_id,
            image=image,
            text=text,
            language=language,
            request_id=request_id,
            mime_type=mime_type,
        )

        # 4. Persist OCR result
        if self.db:
            await self._persist_ocr(tenant_id, document_id, ocr_result, request_id)

        # Store in local dedup cache for subsequent calls
        try:
            self._local_cache[local_key] = ocr_result
        except Exception:
            pass

        # 5. Cache in Redis
        if self.cache:
            await self.cache.set(
                cache_key,
                ocr_result,
                ttl=self.settings.ocr.cache_ttl_seconds,
            )

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
        """Execute OCR prompt through vLLM with image preprocessing."""
        # Preprocess image if provided
        preprocessed_image = image
        preprocessing_metadata = None
        
        if image and mime_type:
            try:
                preprocessor = get_preprocessor()
                
                # Decode base64 image if needed
                image_bytes = preprocessor.decode_from_base64(image)
                
                # Preprocess the image
                result = await preprocessor.preprocess(
                    image_data=image_bytes,
                    mime_type=mime_type,
                )
                
                if result.success:
                    # Encode preprocessed image back to base64
                    preprocessed_image = preprocessor.encode_to_base64(result.image_bytes)
                    preprocessing_metadata = result.metadata.to_dict()
                    
                    logger.info(
                        "image_preprocessing_completed",
                        document_id=document_id,
                        metadata=preprocessing_metadata,
                        request_id=request_id,
                    )
                else:
                    logger.warning(
                        "image_preprocessing_failed_continuing_with_original",
                        document_id=document_id,
                        error=result.error_message,
                        request_id=request_id,
                    )
            except Exception as e:
                logger.error(
                    "image_preprocessing_error",
                    document_id=document_id,
                    error=str(e),
                    request_id=request_id,
                )
                # Continue with original image on error
        
        # Get prompt
        prompt_data = self.prompts.render_prompt(
            capability="ocr",
            variables={
                "document_id": document_id,
                "language": language,
            },
        )

        messages = build_messages(
            system=prompt_data["system"],
            user=prompt_data["user"],
        )

        # If image provided, add it to user message
        if preprocessed_image:
            from app.llm.messages import add_image_to_message
            user_msg = messages[-1]
            # Strip data URI prefix if present
            b64_data = preprocessed_image
            if ";base64," in preprocessed_image:
                b64_data = preprocessed_image.split(";base64,")[1]
            elif "," in preprocessed_image:
                b64_data = preprocessed_image.split(",")[1]
            add_image_to_message(user_msg, b64_data)

        # Call vLLM with OCR-specific parameters
        response = await self.vllm.chat_completion(
            messages=messages,
            temperature=prompt_data.get("temperature", 0.0),
            max_tokens=prompt_data.get("max_tokens", 6048),
            top_p=prompt_data.get("top_p", 0.80),
            top_k=prompt_data.get("top_k", 10),
            presence_penalty=prompt_data.get("presence_penalty", 0.0),
            repetition_penalty=prompt_data.get("repetition_penalty", 1.03),
            workflow="ocr",
            request_id=request_id,
        )

        # Parse and validate output
        try:
            ocr_data = parse_model_output(
                response.content,
                OCRResultSchema,
                request_id=request_id,
            )
            result = ocr_data.model_dump()
            # Ensure document_id is set
            result["document_id"] = document_id
            
            # Add preprocessing metadata if available
            if preprocessing_metadata:
                result["preprocessing_metadata"] = preprocessing_metadata
            
            return result
        except Exception as e:
            logger.error(
                "ocr_parse_failed",
                error=str(e),
                document_id=document_id,
                request_id=request_id,
            )
            # Return minimal result on parse failure
            return {
                "document_id": document_id,
                "raw_text": text or "",
                "entities": [],
                "layout": {"pages": 1, "blocks": []},
                "language": language,
                "confidence": 0.0,
                "_parse_error": str(e),
                "preprocessing_metadata": preprocessing_metadata,
            }

    async def _persist_ocr(
        self,
        tenant_id: str,
        document_id: str,
        ocr_result: Dict[str, Any],
        request_id: Optional[str] = None,
    ) -> None:
        """Persist OCR result to database."""
        if not self.db:
            return
        try:
            try:
                tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
            except Exception:
                tenant_uuid = tenant_id

            try:
                doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id
            except Exception:
                doc_uuid = document_id

            await self.db.ocr_results.create(
                tenant_id=tenant_uuid,
                document_id=doc_uuid,
                raw_text=ocr_result.get("raw_text", ""),
                entities=ocr_result.get("entities", []),
                layout=ocr_result.get("layout", {}),
                language=ocr_result.get("language", "en"),
                confidence=ocr_result.get("confidence"),
                model_version="penthus-1.2-alpha-4b",
                prompt_version="ocr.v1",
            )
            logger.debug("ocr_persisted", document_id=document_id, request_id=request_id)
        except Exception as e:
            logger.error("ocr_persist_failed", document_id=document_id, error=str(e))
            # Don't raise - OCR result is still usable

    def _cache_key(self, tenant_id: str, content_hash: str) -> str:
        """Generate Redis cache key for OCR result."""
        return f"ocr:{tenant_id}:{content_hash}"

    @staticmethod
    def compute_content_hash(data: bytes) -> str:
        """Compute SHA-256 content hash."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _db_to_schema(db_result) -> Dict[str, Any]:
        """Convert database OCR result to schema dict."""
        return {
            "document_id": str(db_result.document_id),
            "raw_text": db_result.raw_text,
            "entities": db_result.entities,
            "layout": db_result.layout,
            "language": db_result.language,
            "confidence": float(db_result.confidence) if db_result.confidence else None,
        }
