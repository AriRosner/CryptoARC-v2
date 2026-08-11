from __future__ import annotations

import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.core.model_classifier import ClassificationItem, ModelBatchPolicy, RedactedClassifier
from app.core.models import TradeGrade
from app.core.storage import Storage
from app.config import AppConfig


NOW = datetime(2026, 8, 10, 20, 0, tzinfo=timezone.utc)


def grade() -> TradeGrade:
    return TradeGrade(
        grade_id="grade-1",
        trade_id="trade-1",
        revision_id="trade-1:r1",
        mode="paper",
        created_at=NOW,
        grader_version="deterministic-trade-grader-v1",
        rules_version="rules-v1",
        strategy_version="strategy-v1",
        data_schema_version=16,
        classifications={"entry": "warning", "signal": "good", "risk": "good", "source": "good", "execution": "warning", "exit": "poor", "outcome": "poor"},
        ex_ante_facts={"signal_score": 80, "entry_reason": "creator seed phrase is secret", "operator_name": "Ari"},
        ex_post_facts={"pnl_sol": -0.01, "exit_reason": "signed_transaction=raw-secret"},
        evidence_ids=("decision-1",),
        confidence=0.9,
        reasons=("entry:warning",),
    )


def item(**changes: object) -> ClassificationItem:
    values = {"job_id": "job-1", "input_version": "input-v1", "grade": grade()}
    values.update(changes)
    return ClassificationItem(**values)


class FailIfCalled:
    def classify(self, batch: list[dict[str, object]], timeout_seconds: float) -> list[dict[str, object]]:
        raise AssertionError("client must not be called")


class RecordingClient:
    def __init__(self, mutate_identity: bool = False) -> None:
        self.calls: list[list[dict[str, object]]] = []
        self.mutate_identity = mutate_identity

    def classify(self, batch: list[dict[str, object]], timeout_seconds: float) -> list[dict[str, object]]:
        self.calls.append(batch)
        results = []
        for payload in batch:
            identity = dict(payload["identity"])
            if self.mutate_identity:
                identity["revision_id"] = "stale"
            results.append({**identity, "category": "timing_ambiguity", "explanation": "Late exit may have amplified loss."})
        return results


class ModelClassifierTests(unittest.TestCase):
    def test_application_config_is_disabled_by_default(self) -> None:
        self.assertFalse(AppConfig(_env_file=None).grading_model_enabled)

    def test_disabled_default_never_calls_client_or_replaces_rule_grade(self) -> None:
        policy = ModelBatchPolicy()
        self.assertFalse(policy.enabled)
        original = item()
        self.assertEqual(RedactedClassifier.classify([original], policy, FailIfCalled()), [])
        self.assertEqual(original.grade.classifications["entry"], "warning")

    def test_budget_exhaustion_never_calls_client(self) -> None:
        policy = ModelBatchPolicy(enabled=True, daily_token_budget=0, daily_cost_budget=0)
        self.assertEqual(RedactedClassifier.classify([item()], policy, FailIfCalled()), [])

    def test_payload_is_allowlisted_and_recursively_redacted(self) -> None:
        client = RecordingClient()
        results = RedactedClassifier.classify([item()], ModelBatchPolicy(enabled=True), client)
        serialized = str(client.calls).lower()
        self.assertNotIn("ari", serialized)
        self.assertNotIn("raw-secret", serialized)
        self.assertNotIn("seed phrase", serialized)
        self.assertEqual(results[0].category, "timing_ambiguity")
        self.assertEqual(set(client.calls[0][0]), {"identity", "objective_grade", "facts"})

    def test_batch_and_item_sizes_are_bounded(self) -> None:
        client = RecordingClient()
        rows = [item(job_id=f"job-{index}", input_version=f"input-{index}") for index in range(5)]
        RedactedClassifier.classify(rows, ModelBatchPolicy(enabled=True, max_items=2, max_chars_per_item=1200), client)
        self.assertEqual(len(client.calls[0]), 2)
        self.assertTrue(all(len(str(payload)) <= 1400 for payload in client.calls[0]))

    def test_stale_identity_output_is_rejected(self) -> None:
        self.assertEqual(RedactedClassifier.classify([item()], ModelBatchPolicy(enabled=True), RecordingClient(mutate_identity=True)), [])

    def test_client_failure_timeout_and_cancellation_are_isolated(self) -> None:
        class SlowClient:
            def classify(self, batch: list[dict[str, object]], timeout_seconds: float) -> list[dict[str, object]]:
                time.sleep(0.1)
                return []
        cancelled = threading.Event()
        cancelled.set()
        self.assertEqual(RedactedClassifier.classify([item()], ModelBatchPolicy(enabled=True), FailIfCalled(), cancel_event=cancelled), [])
        started = time.perf_counter()
        self.assertEqual(RedactedClassifier.classify([item()], ModelBatchPolicy(enabled=True, timeout_seconds=0.01, retry_limit=0), SlowClient()), [])
        self.assertLess(time.perf_counter() - started, 0.08)


class ModelBudgetLedgerTests(unittest.TestCase):
    def test_daily_budget_reservation_is_atomic_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            storage = Storage(str(Path(root) / "budget.db"))
            self.assertTrue(storage.reserve_model_classification_budget("2026-08-10", tokens=80, cost=0.8, token_limit=100, cost_limit=1.0))
            self.assertFalse(storage.reserve_model_classification_budget("2026-08-10", tokens=21, cost=0.1, token_limit=100, cost_limit=1.0))
            self.assertEqual(storage.model_classification_budget("2026-08-10"), {"tokens": 80, "cost": 0.8})


if __name__ == "__main__":
    unittest.main()
