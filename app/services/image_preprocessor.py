"""
Clinova Penthus AI Engine - Image Preprocessing Service
Preprocesses clinical document images before OCR to improve accuracy.
"""

import base64
import io
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ExifTags
from skimage import transform as skimage_transform
from skimage.feature import canny
from skimage.measure import label, regionprops

from app.core.logging import get_logger

logger = get_logger(__name__)


class ImageFormat(str, Enum):
    """Supported image formats."""
    JPEG = "JPEG"
    PNG = "PNG"
    TIFF = "TIFF"
    BMP = "BMP"
    GIF = "GIF"
    WEBP = "WEBP"


@dataclass
class PreprocessingMetadata:
    """Metadata from image preprocessing operations."""
    original_width: int = 0
    original_height: int = 0
    processed_width: int = 0
    processed_height: int = 0
    orientation_corrected: bool = False
    deskew_angle: float = 0.0
    brightness_adjusted: bool = False
    contrast_adjusted: bool = False
    denoised: bool = False
    border_cropped: bool = False
    preprocessing_version: str = "image-preprocess.v1"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "original_width": self.original_width,
            "original_height": self.original_height,
            "processed_width": self.processed_width,
            "processed_height": self.processed_height,
            "orientation_corrected": self.orientation_corrected,
            "deskew_angle": round(self.deskew_angle, 2),
            "brightness_adjusted": self.brightness_adjusted,
            "contrast_adjusted": self.contrast_adjusted,
            "denoised": self.denoised,
            "border_cropped": self.border_cropped,
            "preprocessing_version": self.preprocessing_version,
        }


@dataclass
class PreprocessingResult:
    """Result of image preprocessing."""
    image_bytes: bytes
    metadata: PreprocessingMetadata = field(default_factory=PreprocessingMetadata)
    format: str = "PNG"
    success: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "success": self.success,
            "format": self.format,
            "metadata": self.metadata.to_dict(),
            "error_message": self.error_message,
        }


class ImagePreprocessor:
    """
    Image preprocessing service for clinical document OCR.
    
    Applies a series of transformations to improve OCR accuracy while
    preserving document fidelity.
    """
    
    # Supported input formats
    SUPPORTED_FORMATS = {
        "image/jpeg": ImageFormat.JPEG,
        "image/png": ImageFormat.PNG,
        "image/tiff": ImageFormat.TIFF,
        "image/bmp": ImageFormat.BMP,
        "image/gif": ImageFormat.GIF,
        "image/webp": ImageFormat.WEBP,
    }
    
    # Maximum dimensions for model input
    MAX_WIDTH = 2048
    MAX_HEIGHT = 2048
    
    # Minimum dimensions
    MIN_WIDTH = 512
    MIN_HEIGHT = 512
    
    def __init__(self):
        """Initialize the image preprocessor."""
        logger.info("image_preprocessor_initialized")
    
    async def preprocess(
        self,
        image_data: bytes,
        mime_type: str = "image/png",
        target_width: Optional[int] = None,
        target_height: Optional[int] = None,
    ) -> PreprocessingResult:
        """
        Preprocess a clinical document image for OCR.
        
        Args:
            image_data: Raw image bytes
            mime_type: MIME type of the image
            target_width: Optional target width (overrides auto-sizing)
            target_height: Optional target height (overrides auto-sizing)
            
        Returns:
            PreprocessingResult with processed image and metadata
        """
        metadata = PreprocessingMetadata()
        
        try:
            # Step 1: Validate image format
            if mime_type not in self.SUPPORTED_FORMATS:
                raise ValueError(f"Unsupported image format: {mime_type}")
            
            # Step 2: Load and convert image
            img = Image.open(io.BytesIO(image_data))
            img = self._normalize_image(img)
            
            # Store original dimensions
            metadata.original_width = img.width
            metadata.original_height = img.height
            
            # Step 3: Correct orientation using EXIF
            img, orientation_corrected = self._correct_orientation(img)
            metadata.orientation_corrected = orientation_corrected
            
            # Step 4: Resize to model-supported size
            img = self._resize_image(
                img, 
                target_width or self.MAX_WIDTH,
                target_height or self.MAX_HEIGHT,
            )
            
            # Step 5: Apply brightness and contrast normalization
            img, brightness_adjusted, contrast_adjusted = self._normalize_brightness_contrast(img)
            metadata.brightness_adjusted = brightness_adjusted
            metadata.contrast_adjusted = contrast_adjusted
            
            # Step 6: Apply mild denoising
            img = self._denoise(img)
            metadata.denoised = True
            
            # Step 7: Deskew to correct rotation
            img, deskew_angle = self._deskew(img)
            metadata.deskew_angle = deskew_angle
            
            # Step 8: Apply sharpening if beneficial
            img = self._sharpen(img)
            
            # Step 9: Detect and crop excessive borders
            img, border_cropped = self._crop_borders(img)
            metadata.border_cropped = border_cropped
            
            # Update processed dimensions
            metadata.processed_width = img.width
            metadata.processed_height = img.height
            
            # Convert back to bytes
            output_format = ImageFormat.PNG
            img_bytes = self._image_to_bytes(img, output_format)
            
            logger.info(
                "image_preprocessed",
                original_size=(metadata.original_width, metadata.original_height),
                processed_size=(metadata.processed_width, metadata.processed_height),
                orientation_corrected=metadata.orientation_corrected,
                deskew_angle=metadata.deskew_angle,
            )
            
            return PreprocessingResult(
                image_bytes=img_bytes,
                metadata=metadata,
                format=output_format.value,
                success=True,
            )
            
        except Exception as e:
            logger.error("image_preprocessing_failed", error=str(e))
            return PreprocessingResult(
                image_bytes=image_data,  # Return original on failure
                metadata=metadata,
                format=mime_type.split("/")[-1].upper(),
                success=False,
                error_message=str(e),
            )
    
    def _normalize_image(self, img: Image.Image) -> Image.Image:
        """Convert image to normalized RGB or grayscale representation."""
        # Convert to RGB if necessary (handles RGBA, P, L modes)
        if img.mode in ("RGBA", "LA", "P"):
            # Create white background for transparent images
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        return img
    
    def _correct_orientation(self, img: Image.Image) -> Tuple[Image.Image, bool]:
        """Correct orientation using EXIF metadata."""
        corrected = False
        
        try:
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag == "Orientation":
                        # Apply orientation correction
                        if value == 2:
                            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                            corrected = True
                        elif value == 3:
                            img = img.rotate(180, expand=True)
                            corrected = True
                        elif value == 4:
                            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                            corrected = True
                        elif value == 5:
                            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT).rotate(90, expand=True)
                            corrected = True
                        elif value == 6:
                            img = img.rotate(270, expand=True)
                            corrected = True
                        elif value == 7:
                            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT).rotate(270, expand=True)
                            corrected = True
                        elif value == 8:
                            img = img.rotate(90, expand=True)
                            corrected = True
                        break
        except (AttributeError, KeyError, TypeError):
            # No EXIF data or unable to read it
            pass
        
        return img, corrected
    
    def _resize_image(
        self, 
        img: Image.Image, 
        max_width: int, 
        max_height: int,
    ) -> Image.Image:
        """Resize image while preserving aspect ratio."""
        original_width, original_height = img.size
        
        # Check if resizing is needed
        if original_width <= max_width and original_height <= max_height:
            # Ensure minimum dimensions
            if original_width < self.MIN_WIDTH or original_height < self.MIN_HEIGHT:
                scale = max(self.MIN_WIDTH / original_width, self.MIN_HEIGHT / original_height)
                new_width = int(original_width * scale)
                new_height = int(original_height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return img
        
        # Calculate scale to fit within max dimensions
        scale = min(max_width / original_width, max_height / original_height)
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)
        
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        return img
    
    def _normalize_brightness_contrast(
        self, 
        img: Image.Image,
    ) -> Tuple[Image.Image, bool, bool]:
        """Apply brightness and contrast normalization."""
        brightness_adjusted = False
        contrast_adjusted = False
        
        # Convert to numpy for analysis
        img_array = np.array(img)
        
        # Calculate mean brightness
        mean_brightness = np.mean(img_array)
        
        # Adjust brightness if too dark or too bright
        if mean_brightness < 100:
            # Image is too dark
            enhancer = ImageEnhance.Brightness(img)
            brightness_factor = 128 / mean_brightness
            brightness_factor = min(brightness_factor, 1.5)  # Cap at 1.5x
            img = enhancer.enhance(brightness_factor)
            brightness_adjusted = True
        elif mean_brightness > 200:
            # Image is too bright
            enhancer = ImageEnhance.Brightness(img)
            brightness_factor = 128 / mean_brightness
            brightness_factor = max(brightness_factor, 0.7)  # Don't go below 0.7x
            img = enhancer.enhance(brightness_factor)
            brightness_adjusted = True
        
        # Adjust contrast if too low
        img_array = np.array(img)
        std_dev = np.std(img_array)
        
        if std_dev < 50:
            # Low contrast
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.3)
            contrast_adjusted = True
        
        return img, brightness_adjusted, contrast_adjusted
    
    def _denoise(self, img: Image.Image) -> Image.Image:
        """Apply mild denoising to reduce noise."""
        # Use Gaussian blur with small radius for mild denoising
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
        return img
    
    def _deskew(self, img: Image.Image) -> Tuple[Image.Image, float]:
        """Detect and correct skew angle."""
        img_array = np.array(img.convert("L"))  # Convert to grayscale
        
        # Edge detection
        edges = canny(img_array)
        
        # Find lines using Hough transform
        from skimage.transform import hough_line, hough_line_peaks
        
        try:
            h, theta, d = hough_line(edges)
            _, peak_theta, _ = hough_line_peaks(h, theta, d)
            
            if len(peak_theta) > 0:
                # Calculate skew angle
                skew_angle = np.rad2deg(peak_theta[0]) - 90
                
                # Only deskew if angle is significant (> 0.5 degrees)
                if abs(skew_angle) > 0.5:
                    # Limit deskew angle to reasonable range
                    skew_angle = max(min(skew_angle, 10), -10)
                    img = img.rotate(skew_angle, expand=True, fillcolor=(255, 255, 255))
                    return img, skew_angle
        except Exception:
            # Skip deskewing if detection fails
            pass
        
        return img, 0.0
    
    def _sharpen(self, img: Image.Image) -> Image.Image:
        """Apply sharpening if it improves text clarity."""
        # Use unsharp mask for controlled sharpening
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
        return img
    
    def _crop_borders(self, img: Image.Image) -> Tuple[Image.Image, bool]:
        """Detect and crop excessive borders."""
        img_array = np.array(img.convert("L"))  # Convert to grayscale
        
        # Find non-white regions
        # Assume white background (255, 255, 255)
        threshold = 240
        non_white = img_array < threshold
        
        # Find bounding box of content
        rows = np.any(non_white, axis=1)
        cols = np.any(non_white, axis=0)
        
        if not np.any(rows) or not np.any(cols):
            # Entire image is white, don't crop
            return img, False
        
        row_indices = np.where(rows)[0]
        col_indices = np.where(cols)[0]
        
        top, bottom = row_indices[0], row_indices[-1]
        left, right = col_indices[0], col_indices[-1]
        
        # Add small margin
        margin = 5
        top = max(0, top - margin)
        bottom = min(img_array.shape[0] - 1, bottom + margin)
        left = max(0, left - margin)
        right = min(img_array.shape[1] - 1, right + margin)
        
        # Check if cropping would remove significant content
        original_area = img.width * img.height
        cropped_area = (right - left + 1) * (bottom - top + 1)
        
        if cropped_area < original_area * 0.9:
            # Crop only if we're removing at least 10% of the image
            img = img.crop((left, top, right + 1, bottom + 1))
            return img, True
        
        return img, False
    
    def _image_to_bytes(self, img: Image.Image, format: ImageFormat) -> bytes:
        """Convert PIL Image to bytes."""
        buffer = io.BytesIO()
        img.save(buffer, format=format.value, quality=95, optimize=True)
        buffer.seek(0)
        return buffer.getvalue()
    
    def encode_to_base64(self, image_bytes: bytes) -> str:
        """Encode image bytes to base64 string."""
        return base64.b64encode(image_bytes).decode("utf-8")
    
    def decode_from_base64(self, base64_string: str) -> bytes:
        """Decode base64 string to image bytes."""
        # Strip data URI prefix if present
        if ";base64," in base64_string:
            base64_string = base64_string.split(";base64,")[1]
        elif "," in base64_string and base64_string.startswith("data"):
            base64_string = base64_string.split(",")[1]
        
        return base64.b64decode(base64_string)


# Singleton instance
_preprocessor: Optional[ImagePreprocessor] = None


def get_preprocessor() -> ImagePreprocessor:
    """Get or create the image preprocessor singleton."""
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = ImagePreprocessor()
    return _preprocessor
