"""Shared local-runtime wiring for V2-04.

Builds the V2-03 job service from environment variables with real
Redis/RustFS clients, waits until they answer, and ensures the bucket.
Importing this module needs no live services or YOLO weights; tests
inject in-memory stores or fake clients instead.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

from app.jobs import JobService, RedisStateStore, S3BlobStore

log = logging.getLogger("autocrop.runtime")

READY_TIMEOUT_SECONDS = 120.0
_RETRY_SECONDS = 1.0


@dataclass(frozen=True)
class Settings:
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint: str = "http://rustfs:9000"
    s3_bucket: str = "autocrop"
    s3_access_key: str = "autocrop-local"
    s3_secret_key: str = "autocrop-local-secret-01"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        src = os.environ if env is None else env

        def get(key: str, default: str) -> str:
            return src.get(key, default) or default

        defaults = cls()
        return cls(
            redis_url=get("AUTOCROP_REDIS_URL", defaults.redis_url),
            s3_endpoint=get("AUTOCROP_S3_ENDPOINT", defaults.s3_endpoint),
            s3_bucket=get("AUTOCROP_S3_BUCKET", defaults.s3_bucket),
            s3_access_key=get("AUTOCROP_S3_ACCESS_KEY",
                              defaults.s3_access_key),
            s3_secret_key=get("AUTOCROP_S3_SECRET_KEY",
                              defaults.s3_secret_key),
        )


def build_redis_client(settings: Settings) -> Any:
    import redis

    return redis.Redis.from_url(settings.redis_url)


def build_s3_client(settings: Settings) -> Any:
    import boto3
    from botocore.config import Config

    # RustFS without server domains only answers path-style requests.
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )


def build_service(settings: Settings | None = None, *,
                  state: Any = None, blobs: Any = None,
                  process_fn: Any = None) -> JobService:
    """Build the V2-03 service; inject ``state``/``blobs`` to avoid clients."""
    settings = settings or Settings.from_env()
    if state is None:
        state = RedisStateStore(build_redis_client(settings))
    if blobs is None:
        blobs = S3BlobStore(build_s3_client(settings), settings.s3_bucket)
    if process_fn is None:
        return JobService(state, blobs)
    return JobService(state, blobs, process_fn=process_fn)


def _missing_bucket(exc: Exception) -> bool:
    text = str(exc)
    return ("404" in text or "NoSuchBucket" in text
            or "Not Found" in text)


def wait_for_ready(redis_client: Any = None, s3_client: Any = None,
                   bucket: str = "autocrop", *,
                   timeout: float = READY_TIMEOUT_SECONDS,
                   sleep: Any = time.sleep) -> None:
    """Block until Redis/RustFS answer; raise ``TimeoutError`` naming them."""
    deadline = time.monotonic() + timeout
    while True:
        problems = []
        if redis_client is not None:
            try:
                redis_client.ping()
            except Exception as exc:
                problems.append(f"redis: {exc}")
        if s3_client is not None:
            try:
                s3_client.head_bucket(Bucket=bucket)
            except Exception as exc:
                if not _missing_bucket(exc):
                    problems.append(f"rustfs: {exc}")
        if not problems:
            return
        message = "; ".join(problems)
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"timed out waiting for services: {message}")
        log.info("waiting for services (%s)", message)
        sleep(_RETRY_SECONDS)


def ensure_bucket(s3_client: Any, bucket: str) -> None:
    """Create ``bucket`` when missing; propagate any other S3 error."""
    try:
        s3_client.head_bucket(Bucket=bucket)
    except Exception as exc:
        if not _missing_bucket(exc):
            raise
        s3_client.create_bucket(Bucket=bucket)
        log.info("created bucket %r", bucket)
