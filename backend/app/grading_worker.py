from __future__ import annotations

import argparse
import socket
import time
import json
from datetime import datetime, timedelta, timezone

from app.config import get_config
from app.core.storage import Storage
from app.core.trade_grading import DeterministicTradeGrader
from app.core.model_classifier import ClassificationClient, ClassificationItem, ModelBatchPolicy, RedactedClassifier


def process_one(
    storage: Storage,
    *,
    worker_id: str,
    lease_seconds: int = 30,
    max_attempts: int = 3,
    classification_policy: ModelBatchPolicy | None = None,
    classifier_client: ClassificationClient | None = None,
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
            return True
        if classification_policy and classification_policy.enabled and classifier_client is not None:
            estimated_tokens = max(1, len(json.dumps(grade.to_dict(), sort_keys=True)) // 4)
            estimated_cost = (estimated_tokens / 1000) * classification_policy.estimated_cost_per_1k_tokens
            budget_day = now.date().isoformat()
            if storage.reserve_model_classification_budget(
                budget_day,
                tokens=estimated_tokens,
                cost=estimated_cost,
                token_limit=classification_policy.daily_token_budget,
                cost_limit=classification_policy.daily_cost_budget,
            ):
                results = RedactedClassifier.classify(
                    [ClassificationItem(job_id=job.job_id, input_version=job.revision.revision_id, grade=grade)],
                    classification_policy,
                    classifier_client,
                )
                for result in results:
                    storage.save_model_classification(result)
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
    config = get_config()
    classification_policy = ModelBatchPolicy(
        enabled=config.grading_model_enabled,
        daily_token_budget=max(0, config.grading_model_daily_token_budget),
        daily_cost_budget=max(0.0, config.grading_model_daily_cost_budget),
        max_items=max(1, config.grading_model_max_items),
        timeout_seconds=max(0.1, config.grading_model_timeout_seconds),
        retry_limit=max(0, config.grading_model_retry_limit),
    )
    worker_id = f"grading:{socket.gethostname()}:{id(storage)}"
    while True:
        processed = process_one(
            storage,
            worker_id=worker_id,
            lease_seconds=args.lease_seconds,
            max_attempts=args.max_attempts,
            classification_policy=classification_policy,
            classifier_client=None,
        )
        if args.once:
            return 0
        if not processed:
            time.sleep(max(0.1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
