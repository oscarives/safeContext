"""S3StorageAdapter — StoragePort backed by MinIO (via boto3).

ADR-008: WORM semantics — objects are written once and never overwritten.
The digest returned by put() is recorded in the artifacts table for audit.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import boto3
from botocore.config import Config

from workers.core.ports import StoragePort

logger = logging.getLogger(__name__)


class S3StorageAdapter(StoragePort):
    """StoragePort implementation that talks to MinIO (S3-compatible).

    ADR-011: This is the ONLY module in workers/ that imports boto3.
    """

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        use_ssl: bool = False,
    ) -> None:
        scheme = "https" if use_ssl else "http"
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=f"{scheme}://{endpoint_url}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )
        self._bucket = bucket

    # ── StoragePort ──────────────────────────────────────────────────────────

    async def put(
        self,
        key: str,
        data: bytes,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Store *data* in MinIO and return its SHA-256 hex digest."""
        digest = hashlib.sha256(data).hexdigest()
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            Metadata=metadata or {},
        )
        logger.debug(
            "s3_storage.put bucket=%s key=%s digest=%s bytes=%d",
            self._bucket,
            key,
            digest,
            len(data),
        )
        return digest

    async def get(self, key: str) -> bytes:
        """Retrieve and return bytes stored under *key*."""
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        data: bytes = resp["Body"].read()
        logger.debug(
            "s3_storage.get bucket=%s key=%s bytes=%d",
            self._bucket,
            key,
            len(data),
        )
        return data
