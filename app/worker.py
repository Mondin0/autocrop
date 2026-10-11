"""Local worker entrypoint for V2-04.

Pumps the existing V2-03 queue one job at a time with the production
detector (same defaults as the V1 CLI) and runs the expiration cleanup
on every idle pass. Unexpected pump errors are logged and retried, so
the container log always shows what the worker is waiting on.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.cli import build_detector
from app.jobs import JobService, RedisStateStore, S3BlobStore
from app.runtime import (READY_TIMEOUT_SECONDS, Settings, build_redis_client,
                         build_s3_client, ensure_bucket, wait_for_ready)

log = logging.getLogger("autocrop.worker")

IDLE_SECONDS = 1.0


def pump_once(service: JobService, detector: Any) -> bool:
    """Run one queued job; on an empty queue run cleanup and return False."""
    done = service.run_next(detector)
    if done is None:
        removed = service.cleanup()
        if removed:
            log.info("cleaned %d expired job(s)", removed)
        return False
    log.info("job %s %s: %d/%d processed",
             done["job_id"], done["status"],
             done["processed"], done["total"])
    return True


def main(settings: Settings | None = None, *,
         service: JobService | None = None,
         detector: Any = None) -> int:
    settings = settings or Settings.from_env()
    if service is None:
        redis_client = build_redis_client(settings)
        s3_client = build_s3_client(settings)
        service = JobService(RedisStateStore(redis_client),
                             S3BlobStore(s3_client, settings.s3_bucket))
        wait_for_ready(redis_client, s3_client, settings.s3_bucket,
                       timeout=READY_TIMEOUT_SECONDS)
        ensure_bucket(s3_client, settings.s3_bucket)
    if detector is None:
        detector = build_detector()
    while True:
        try:
            if not pump_once(service, detector):
                time.sleep(IDLE_SECONDS)
        except Exception:
            log.exception("worker pump failed; retrying")
            time.sleep(IDLE_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
