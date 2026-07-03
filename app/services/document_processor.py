"""
Clinova Penthus AI Engine - Document Processing Utilities
Support for PDF, TXT, and multi-page document processing.
"""

import base64
import hashlib
import io
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)


class DocumentProcessingError(Exception):
    """Exception raised when document processing fails."""

    def __init__(self, message: str, document_type: Optional[str] = None):
        self.message = message
        self.document_type = document_type
        super().__init__(self.message)


class DocumentProcessor:
    """
    Document processor for PDF, TXT, and image-based clinical documents.
    
    This processor handles:
    - PDF rendering to images (page-by-page at high DPI)
    - TXT file decoding
    - Multi-page document handling
    - Document type detection
    """

    # Supported MIME types
    PDF_MIME_TYPES = {
        "application/pdf",
    }

    TXT_MIME_TYPES = {
        "text/plain",
    }

    IMAGE_MIME_TYPES = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }

    # PDF rendering settings
    PDF_DPI = 300  # Minimum 300 DPI for OCR quality
    PDF_MAX_PAGES = 50  # Safety limit for multi-page PDFs

    def __init__(self):
        """Initialize the document processor."""
        self._fitz = None
        logger.info("document_processor_initialized")

    def _load_fitz(self):
        """Lazily load PyMuPDF (fitz) library."""
        if self._fitz is None:
            try:
                import fitz  # PyMuPDF

                self._fitz = fitz
            except ImportError as e:
                logger.error("pymupdf_import_failed", error=str(e))
                raise DocumentProcessingError(
                    "PyMuPDF (fitz) library not available. Install with: pip install pymupdf",
                    document_type="pdf",
                )
        return self._fitz

    def detect_document_type(self, mime_type: str) -> str:
        """
        Detect document type from MIME type.

        Args:
            mime_type: MIME type string

        Returns:
            Document type: 'pdf', 'txt', or 'image'
        """
        mime_lower = mime_type.lower() if mime_type else ""

        if mime_lower in self.PDF_MIME_TYPES:
            return "pdf"
        elif mime_lower in self.TXT_MIME_TYPES:
            return "txt"
        elif mime_lower in self.IMAGE_MIME_TYPES:
            return "image"
        else:
            return "unknown"

    async def process_document(
        self,
        content: bytes,
        mime_type: str,
        document_id: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Process a document and extract text.

        Args:
            content: Raw document bytes
            mime_type: MIME type of the document
            document_id: Document identifier
            language: Document language

        Returns:
            Dictionary with:
            - document_type: 'pdf', 'txt', or 'image'
            - pages: List of page dictionaries with image bytes
            - raw_text: Extracted text (for TXT files)
            - page_count: Number of pages
        """
        doc_type = self.detect_document_type(mime_type)

        if doc_type == "pdf":
            return await self._process_pdf(content, document_id, language)
        elif doc_type == "txt":
            return await self._process_txt(content, document_id, language)
        elif doc_type == "image":
            return await self._process_image(content, mime_type, document_id, language)
        else:
            raise DocumentProcessingError(
                f"Unsupported document type: {mime_type}",
                document_type=mime_type,
            )

    async def _process_pdf(
        self,
        content: bytes,
        document_id: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Process a PDF document by rendering each page to an image.

        Args:
            content: PDF bytes
            document_id: Document identifier
            language: Document language

        Returns:
            Dictionary with rendered page images
        """
        fitz = self._load_fitz()

        try:
            # Open PDF from bytes
            pdf_doc = fitz.open(stream=content, filetype="pdf")

            # Check page count
            page_count = len(pdf_doc)
            if page_count > self.PDF_MAX_PAGES:
                logger.warning(
                    "pdf_page_limit_exceeded",
                    document_id=document_id,
                    page_count=page_count,
                    max_pages=self.PDF_MAX_PAGES,
                )
                page_count = self.PDF_MAX_PAGES

            pages = []
            for page_num in range(page_count):
                try:
                    page = pdf_doc[page_num]

                    # Render page to image at high DPI
                    # Use matrix for high-resolution rendering
                    mat = fitz.Matrix(self.PDF_DPI / 72.0, self.PDF_DPI / 72.0)
                    pix = page.get_pixmap(matrix=mat)

                    # Convert to PNG bytes
                    img_bytes = pix.tobytes("png")

                    # Encode to base64
                    img_base64 = base64.b64encode(img_bytes).decode("utf-8")

                    pages.append(
                        {
                            "page_number": page_num + 1,
                            "image": f"data:image/png;base64,{img_base64}",
                            "mime_type": "image/png",
                        }
                    )

                except Exception as page_error:
                    logger.error(
                        "pdf_page_rendering_failed",
                        document_id=document_id,
                        page_number=page_num + 1,
                        error=str(page_error),
                    )
                    # Continue with next page - don't fail entire document

            pdf_doc.close()

            logger.info(
                "pdf_processed",
                document_id=document_id,
                page_count=len(pages),
                dpi=self.PDF_DPI,
            )

            return {
                "document_type": "pdf",
                "pages": pages,
                "page_count": len(pages),
                "raw_text": "",  # Will be populated by OCR
            }

        except Exception as e:
            logger.error(
                "pdf_processing_failed",
                document_id=document_id,
                error=str(e),
            )
            raise DocumentProcessingError(
                f"Failed to process PDF: {str(e)}",
                document_type="pdf",
            )

    async def _process_txt(
        self,
        content: bytes,
        document_id: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Process a TXT file by decoding text.

        Args:
            content: TXT bytes
            document_id: Document identifier
            language: Document language

        Returns:
            Dictionary with decoded text
        """
        try:
            # Try UTF-8 first, then fallback to latin-1
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = content.decode("latin-1")

            logger.info(
                "txt_processed",
                document_id=document_id,
                text_length=len(text),
            )

            return {
                "document_type": "txt",
                "pages": [],  # No images needed for TXT
                "raw_text": text,
                "page_count": 1,
            }

        except Exception as e:
            logger.error(
                "txt_processing_failed",
                document_id=document_id,
                error=str(e),
            )
            raise DocumentProcessingError(
                f"Failed to process TXT: {str(e)}",
                document_type="txt",
            )

    async def _process_image(
        self,
        content: bytes,
        mime_type: str,
        document_id: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Process an image document.

        Args:
            content: Image bytes
            mime_type: Image MIME type
            document_id: Document identifier
            language: Document language

        Returns:
            Dictionary with image data
        """
        try:
            # Encode to base64
            img_base64 = base64.b64encode(content).decode("utf-8")

            logger.info(
                "image_processed",
                document_id=document_id,
                mime_type=mime_type,
            )

            return {
                "document_type": "image",
                "pages": [
                    {
                        "page_number": 1,
                        "image": f"data:{mime_type};base64,{img_base64}",
                        "mime_type": mime_type,
                    }
                ],
                "raw_text": "",  # Will be populated by OCR
                "page_count": 1,
            }

        except Exception as e:
            logger.error(
                "image_processing_failed",
                document_id=document_id,
                error=str(e),
            )
            raise DocumentProcessingError(
                f"Failed to process image: {str(e)}",
                document_type="image",
            )


def compute_content_hash(content: bytes) -> str:
    """Compute SHA-256 hash of document content."""
    return hashlib.sha256(content).hexdigest()


# Singleton instance
_processor: Optional[DocumentProcessor] = None


def get_document_processor() -> DocumentProcessor:
    """Get or create the document processor singleton."""
    global _processor
    if _processor is None:
        _processor = DocumentProcessor()
    return _processor
