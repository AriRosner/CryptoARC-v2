from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass(frozen=True, slots=True)
class CriticalMetrics:
    observed_at: datetime
    snapshot_version: int
    queue_depth: int
    db_lock_wait_p99_ms: float
    source_loss: bool
    source_to_decision_p99_ms: float
    intent_to_quote_p99_ms: float
    memory_pct: float
    connections: int
    focused: bool = True
    connected: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_payload(self) -> dict[str, Any]:
        return {**asdict(self), "observed_at": self.observed_at.isoformat()}


@dataclass(frozen=True, slots=True)
class PressureState:
    status: str
    disabled_tiers: tuple[str, ...]
    failure_windows: int
    recovery_windows: int
    snapshot_version: int
    reasons: tuple[str, ...]
    worker_failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QueueJob:
    identity: str
    payload: dict[str, Any]
    attempts: int = 0


class BoundedWorkQueue:
    def __init__(self, *, max_items: int = 100, retry_limit: int = 3) -> None:
        self.max_items = max(1, max_items)
        self.retry_limit = max(1, retry_limit)
        self._queued: deque[QueueJob] = deque()
        self._claimed: dict[str, QueueJob] = {}
        self._dead: list[QueueJob] = []
        self._identities: set[str] = set()
        self._lock = Lock()

    def enqueue(self, identity: str, payload: dict[str, Any]) -> bool:
        with self._lock:
            if not identity or identity in self._identities or len(self._queued) + len(self._claimed) >= self.max_items:
                return False
            self._queued.append(QueueJob(identity, dict(payload)))
            self._identities.add(identity)
            return True

    def claim(self) -> QueueJob | None:
        with self._lock:
            if not self._queued:
                return None
            job = self._queued.popleft()
            job.attempts += 1
            self._claimed[job.identity] = job
            return job

    def finish(self, identity: str) -> bool:
        with self._lock:
            if self._claimed.pop(identity, None) is None:
                return False
            self._identities.discard(identity)
            return True

    def fail(self, identity: str, error: str) -> str:
        del error
        with self._lock:
            job = self._claimed.pop(identity, None)
            if job is None:
                return "stale_claim"
            if job.attempts >= self.retry_limit:
                self._dead.append(job)
                return "dead_letter"
            self._queued.appendleft(job)
            return "queued"

    @property
    def dead_letter_count(self) -> int:
        return len(self._dead)


class WorkloadGovernor:
    SHED_ORDER = ("model", "grading", "sentinel", "dashboard_analytics")
    CORE_TIERS = frozenset({"ingestion", "risk", "kill_switch", "reconciliation", "protective_exit"})

    def __init__(self, *, consecutive_failures: int = 3, recovery_windows: int = 3) -> None:
        self.consecutive_failures = max(1, consecutive_failures)
        self.required_recovery_windows = max(1, recovery_windows)
        self._failures = 0
        self._recoveries = 0
        self._disabled: tuple[str, ...] = ()
        self._snapshot_version = 0
        self._results: set[tuple[int, str]] = set()
        self._worker_failures: deque[str] = deque(maxlen=20)
        self._state = PressureState("healthy", (), 0, 0, 0, (), ())

    def observe(self, metrics: CriticalMetrics) -> PressureState:
        if metrics.snapshot_version <= self._snapshot_version:
            return self._state
        self._snapshot_version = metrics.snapshot_version
        reasons = self._pressure_reasons(metrics)
        if reasons:
            self._failures += 1
            self._recoveries = 0
            if self._failures >= self.consecutive_failures:
                self._disabled = self.SHED_ORDER
        else:
            self._failures = 0
            if self._disabled:
                self._recoveries += 1
                if self._recoveries >= self.required_recovery_windows:
                    self._disabled = ()
                    self._recoveries = 0
        status = "degraded_observability" if self._disabled else "healthy"
        self._state = PressureState(
            status=status,
            disabled_tiers=self._disabled,
            failure_windows=self._failures,
            recovery_windows=self._recoveries,
            snapshot_version=self._snapshot_version,
            reasons=tuple(reasons),
            worker_failures=tuple(self._worker_failures),
        )
        return self._state

    def allowed(self, tier: str) -> bool:
        if tier in self.CORE_TIERS:
            return True
        return tier not in self._disabled

    def record_result(self, job_identity: str, *, snapshot_version: int) -> bool:
        identity = (snapshot_version, job_identity)
        if snapshot_version != self._snapshot_version or not job_identity or identity in self._results:
            return False
        self._results.add(identity)
        if len(self._results) > 1000:
            self._results = {item for item in self._results if item[0] >= self._snapshot_version - 5}
        return True

    def record_worker_failure(self, tier: str, error: str) -> None:
        self._worker_failures.append(f"{tier}:{error[:160]}")

    def poll_interval_ms(self, tier: str, *, focused: bool, connected: bool) -> int:
        if not connected:
            return 60_000
        if not focused:
            return 30_000
        return 15_000 if not self.allowed(tier) else 5_000

    def current(self) -> PressureState:
        return self._state

    @staticmethod
    def _pressure_reasons(metrics: CriticalMetrics) -> list[str]:
        reasons: list[str] = []
        if metrics.queue_depth > 100:
            reasons.append("queue_depth")
        if metrics.db_lock_wait_p99_ms > 50:
            reasons.append("db_lock_wait_p99")
        if metrics.source_loss:
            reasons.append("source_loss")
        if metrics.source_to_decision_p99_ms > 1_000:
            reasons.append("source_to_decision_p99")
        if metrics.intent_to_quote_p99_ms > 1_000:
            reasons.append("intent_to_quote_p99")
        if metrics.memory_pct > 85:
            reasons.append("memory")
        if metrics.connections > 100:
            reasons.append("connections")
        return reasons
