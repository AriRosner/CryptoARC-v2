from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Protocol, Sequence

from app.core.models import TradeGrade


@dataclass(frozen=True, slots=True)
class ModelBatchPolicy:
    enabled: bool = False
    daily_token_budget: int = 100_000
    daily_cost_budget: float = 10.0
    max_items: int = 8
    max_chars_per_item: int = 2_000
    timeout_seconds: float = 10.0
    retry_limit: int = 1
    estimated_cost_per_1k_tokens: float = 0.01
    tokens_used: int = 0
    cost_used: float = 0.0


@dataclass(frozen=True, slots=True)
class ClassificationItem:
    job_id: str
    input_version: str
    grade: TradeGrade


@dataclass(frozen=True, slots=True)
class ModelClassification:
    job_id: str
    trade_id: str
    revision_id: str
    strategy_version: str
    rules_version: str
    input_version: str
    data_schema_version: int
    category: str
    explanation: str


class ClassificationClient(Protocol):
    def classify(self, batch: list[dict[str, object]], timeout_seconds: float) -> list[dict[str, object]]: ...


class RedactedClassifier:
    """Optional narrative-only adapter; deterministic grades always remain authoritative."""

    FACT_ALLOWLIST = frozenset(
        {
            "signal_score",
            "entry_compliant",
            "risk_clear",
            "source_confidence",
            "latency_ms",
            "slippage_pct",
            "entry_reason",
            "pnl_sol",
            "exit_compliant",
            "exit_reason",
            "hold_duration_seconds",
            "total_cost_sol",
        }
    )
    SECRET_DENYLIST = (
        "private_key",
        "seed",
        "authorization",
        "signed_transaction",
        "auth_token",
        "operator_name",
        "password",
    )

    @classmethod
    def classify(
        cls,
        batch: Sequence[ClassificationItem],
        policy: ModelBatchPolicy,
        client: ClassificationClient,
        *,
        cancel_event: threading.Event | None = None,
    ) -> list[ModelClassification]:
        if not policy.enabled or not batch or policy.daily_token_budget <= policy.tokens_used or policy.daily_cost_budget <= policy.cost_used:
            return []
        if cancel_event is not None and cancel_event.is_set():
            return []
        bounded = list(batch[: max(0, policy.max_items)])
        payloads = [cls._payload(item, max(200, policy.max_chars_per_item)) for item in bounded]
        estimated_tokens = sum(max(1, len(json.dumps(payload, sort_keys=True)) // 4) for payload in payloads)
        estimated_cost = (estimated_tokens / 1000) * max(0.0, policy.estimated_cost_per_1k_tokens)
        if policy.tokens_used + estimated_tokens > policy.daily_token_budget:
            return []
        if policy.cost_used + estimated_cost > policy.daily_cost_budget:
            return []

        raw_results: list[dict[str, object]] | None = None
        for _ in range(max(0, policy.retry_limit) + 1):
            if cancel_event is not None and cancel_event.is_set():
                return []
            raw_results = cls._bounded_call(client, payloads, max(0.001, policy.timeout_seconds))
            if raw_results is not None:
                break
        if raw_results is None:
            return []

        identities = {str(payload["identity"]["job_id"]): dict(payload["identity"]) for payload in payloads}
        accepted: list[ModelClassification] = []
        for raw in raw_results[: len(payloads)]:
            job_id = str(raw.get("job_id") or "")
            expected = identities.get(job_id)
            if expected is None or any(raw.get(key) != value for key, value in expected.items()):
                continue
            category = cls._safe_text(raw.get("category"), 80)
            explanation = cls._safe_text(raw.get("explanation"), 500)
            if not category or not explanation:
                continue
            accepted.append(
                ModelClassification(
                    job_id=job_id,
                    trade_id=str(expected["trade_id"]),
                    revision_id=str(expected["revision_id"]),
                    strategy_version=str(expected["strategy_version"]),
                    rules_version=str(expected["rules_version"]),
                    input_version=str(expected["input_version"]),
                    data_schema_version=int(expected["data_schema_version"]),
                    category=category,
                    explanation=explanation,
                )
            )
        return accepted

    @classmethod
    def _payload(cls, item: ClassificationItem, max_chars: int) -> dict[str, object]:
        grade = item.grade
        identity = {
            "job_id": item.job_id,
            "trade_id": grade.trade_id,
            "revision_id": grade.revision_id,
            "strategy_version": grade.strategy_version,
            "rules_version": grade.rules_version,
            "input_version": item.input_version,
            "data_schema_version": grade.data_schema_version,
        }
        facts: dict[str, object] = {}
        for source in (grade.ex_ante_facts, grade.ex_post_facts):
            for key, value in source.items():
                if key in cls.FACT_ALLOWLIST:
                    facts[key] = cls._redact(value)
        payload: dict[str, object] = {
            "identity": identity,
            "objective_grade": dict(grade.classifications),
            "facts": facts,
        }
        while len(json.dumps(payload, sort_keys=True)) > max_chars and facts:
            facts.pop(next(reversed(facts)))
        return payload

    @classmethod
    def _redact(cls, value: object) -> object:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if cls._secret_text(key) else cls._redact(item)
                for key, item in value.items()
                if key in cls.FACT_ALLOWLIST
            }
        if isinstance(value, (list, tuple)):
            return [cls._redact(item) for item in value[:20]]
        if isinstance(value, str):
            return "[REDACTED]" if cls._secret_text(value) else value[:500]
        return value if isinstance(value, (bool, int, float)) or value is None else "[REDACTED]"

    @classmethod
    def _secret_text(cls, value: str) -> bool:
        lowered = value.lower()
        return any(term in lowered for term in cls.SECRET_DENYLIST)

    @classmethod
    def _safe_text(cls, value: object, limit: int) -> str:
        text = str(value or "").strip()[:limit]
        return "" if cls._secret_text(text) else text

    @staticmethod
    def _bounded_call(
        client: ClassificationClient,
        payloads: list[dict[str, object]],
        timeout_seconds: float,
    ) -> list[dict[str, object]] | None:
        outcome: dict[str, object] = {}

        def run() -> None:
            try:
                outcome["result"] = client.classify(payloads, timeout_seconds)
            except Exception as exc:
                outcome["error"] = exc

        thread = threading.Thread(target=run, name="bounded-model-classifier", daemon=True)
        thread.start()
        thread.join(timeout_seconds)
        result = outcome.get("result")
        return result if not thread.is_alive() and isinstance(result, list) else None
