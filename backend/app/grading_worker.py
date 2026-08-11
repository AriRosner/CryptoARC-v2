from __future__ import annotations

import argparse
import socket
import time
from datetime import datetime, timedelta, timezone

from app.config import get_config
from app.core.storage import Storage
from app.core.trade_grading import DeterministicTradeGrader


def process_one(
    storage: Storage,
    *,
    worker_id: str,
    lease_seconds: int = 30,
    max_attempts: int = 3,
) -> bool:
    now = datetime.now(timezone.utc)
    job = storage.claim_trade_review(
        worker_id,
        now + timedelta(seconds=max(5, lease_seconds)),
        now=now,
    )
    if job is None:
        return False
    try:
        grade = DeterministicTradeGrader.grade(job.revision)
        if not storage.finish_trade_review(job.job_id, job.claim_id, job.revision.revision_id, grade):
            storage.fail_trade_review(job.job_id, job.claim_id, "stale result rejected", max_attempts=max_attempts)
    except Exception as exc:
        storage.fail_trade_review(
            job.job_id,
            job.claim_id,
            f"{exc.__class__.__name__}: {exc}",
            max_attempts=max_attempts,
        )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Low-priority deterministic trade grading worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued revision")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--lease-seconds", type=int, default=30)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    storage = Storage(get_config().database_path)
    worker_id = f"grading:{socket.gethostname()}:{id(storage)}"
    while True:
        processed = process_one(
            storage,
            worker_id=worker_id,
            lease_seconds=args.lease_seconds,
            max_attempts=args.max_attempts,
        )
        if args.once:
            return 0
        if not processed:
            time.sleep(max(0.1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
