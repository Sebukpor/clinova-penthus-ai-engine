"""
Clinova Penthus AI Engine - Object Storage
Abstraction over OCI Object Storage / MinIO / S3-compatible storage.
"""

from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ObjectStorageService:
    """Object storage service for documents and artifacts."""

    def __init__(self):
        self.settings = get_settings()
        self._client = None

    async def _get_client(self):
        """Lazy initialization of storage client."""
        if self._client is None:
            try:
                from minio import Minio
                self._client = Minio(
                    self.settings.storage.endpoint.replace("http://", "").replace("https://", ""),
                    access_key=self.settings.storage.access_key,
                    secret_key=self.settings.storage.secret_key,
                    secure=self.settings.storage.secure,
                    region=self.settings.storage.region,
                )
                # Ensure bucket exists
                bucket = self.settings.storage.bucket
                if not self._client.bucket_exists(bucket):
                    self._client.make_bucket(bucket)
                    logger.info("storage_bucket_created", bucket=bucket)
            except ImportError:
                logger.warning("minio_not_installed")
                self._client = False  # Mark as unavailable
            except Exception as e:
                logger.error("storage_init_failed", error=str(e))
                self._client = False
        return self._client if self._client else None

    async def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload data to object storage."""
        client = await self._get_client()
        if not client:
            logger.warning("storage_not_available", key=key)
            return f"local://{key}"

        try:
            from io import BytesIO
            bucket = self.settings.storage.bucket
            result = client.put_object(
                bucket_name=bucket,
                object_name=key,
                data=BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            uri = f"s3://{bucket}/{key}" if hasattr(result, "bucket_name") else f"local://{key}"
            logger.debug("storage_uploaded", key=key, size=len(data))
            return uri
        except Exception as e:
            logger.error("storage_upload_failed", key=key, error=str(e))
            return f"local://{key}"

    async def download(self, key: str) -> Optional[bytes]:
        """Download data from object storage."""
        client = await self._get_client()
        if not client:
            return None

        try:
            bucket = self.settings.storage.bucket
            response = client.get_object(bucket, key)
            return response.read()
        except Exception as e:
            logger.error("storage_download_failed", key=key, error=str(e))
            return None

    async def delete(self, key: str) -> bool:
        """Delete object from storage."""
        client = await self._get_client()
        if not client:
            return False

        try:
            bucket = self.settings.storage.bucket
            client.remove_object(bucket, key)
            return True
        except Exception as e:
            logger.error("storage_delete_failed", key=key, error=str(e))
            return False
