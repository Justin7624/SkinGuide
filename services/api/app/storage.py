# services/api/app/storage.py

import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import boto3
from botocore.client import Config as BotoConfig

from .config import settings

@dataclass
class StoredObject:
    uri: str  # file://... or s3://bucket/key

class Storage:
    def put_bytes(self, *, data: bytes, key: str, content_type: str) -> StoredObject:
        raise NotImplementedError

    def get_local_path_if_any(self, uri: str) -> Optional[str]:
        return None


class LocalStorage(Storage):
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def put_bytes(self, *, data: bytes, key: str, content_type: str) -> StoredObject:
        # key like "progress/ab/cd.jpg" or "donations/ab/sha.jpg"
        full_path = os.path.join(self.base_dir, key)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(data)
        return StoredObject(uri=f"file://{full_path}")

    def get_local_path_if_any(self, uri: str) -> Optional[str]:
        p = urlparse(uri)
        if p.scheme == "file":
            return p.path
        return None


class S3Storage(Storage):
    def __init__(self, bucket: str, prefix: str):
        self.bucket = bucket
        self.prefix = prefix.strip("/")

        session = boto3.session.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.s3 = session.client("s3", config=BotoConfig(signature_version="s3v4"))

    def put_bytes(self, *, data: bytes, key: str, content_type: str) -> StoredObject:
        s3_key = f"{self.prefix}/{key}".lstrip("/")
        self.s3.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return StoredObject(uri=f"s3://{self.bucket}/{s3_key}")


_storage_singleton: Storage | None = None

def get_storage() -> Storage:
    global _storage_singleton
    if _storage_singleton is not None:
        return _storage_singleton

    if settings.STORAGE_BACKEND == "s3":
        if not settings.S3_BUCKET:
            raise RuntimeError("STORAGE_BACKEND=s3 requires S3_BUCKET")
        _storage_singleton = S3Storage(bucket=settings.S3_BUCKET, prefix=settings.S3_PREFIX)
        return _storage_singleton

    # Default local: base_dir governs root; we store subfolders under it
    # Use /data as base so existing volumes still work.
    _storage_singleton = LocalStorage(base_dir="/data")
    return _storage_singleton
