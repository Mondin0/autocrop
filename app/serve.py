"""Local API entrypoint for V2-04.

Serves ``app.jobs.create_app`` with the real Redis/RustFS stores. Run with
``uvicorn app.serve:app`` inside the Compose network; the lifespan hook
waits for the dependencies and ensures the bucket, logging while it waits.
Passing ``state``/``blobs`` skips the real clients (tests).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from app.jobs import JobService, RedisStateStore, S3BlobStore, create_app
from app.runtime import (READY_TIMEOUT_SECONDS, Settings, build_redis_client,
                         build_s3_client, ensure_bucket, wait_for_ready)


def create_local_app(settings: Settings | None = None, *,
                     state: Any = None, blobs: Any = None) -> Any:
    settings = settings or Settings.from_env()
    redis_client: Any = None
    s3_client: Any = None
    if state is None:
        redis_client = build_redis_client(settings)
        state = RedisStateStore(redis_client)
    if blobs is None:
        s3_client = build_s3_client(settings)
        blobs = S3BlobStore(s3_client, settings.s3_bucket)
    service = JobService(state, blobs)

    @asynccontextmanager
    async def lifespan(app: Any) -> Any:
        if redis_client is not None or s3_client is not None:
            wait_for_ready(redis_client, s3_client, settings.s3_bucket,
                           timeout=READY_TIMEOUT_SECONDS)
            if s3_client is not None:
                ensure_bucket(s3_client, settings.s3_bucket)
        yield

    app = create_app(service)
    app.router.lifespan_context = lifespan
    return app


app = create_local_app()
