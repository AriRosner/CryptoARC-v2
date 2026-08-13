import asyncio
import gc
import json
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import main as main_app
from app.core.models import SourceStatus
from app.core.sources import LaunchEvent, PumpPortalLaunchSource, SolanaLogsSource


class _TrackingQueue(asyncio.Queue[str]):
    def __init__(self) -> None:
        super().__init__()
        self.pending_get_started = asyncio.Event()
        self.pending_get_task: asyncio.Task[str] | None = None

    async def get(self) -> str:
        if self.empty():
            task = asyncio.current_task()
            assert task is not None
            self.pending_get_task = task
            self.pending_get_started.set()
        return await super().get()


class _BlockingWebSocket:
    def __init__(self) -> None:
        self.recv_started = asyncio.Event()
        self.recv_task: asyncio.Task[str] | None = None
        self.sent: list[dict[str, object]] = []
        self.sent_event = asyncio.Event()

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))
        self.sent_event.set()

    async def recv(self) -> str:
        task = asyncio.current_task()
        assert task is not None
        self.recv_task = task
        self.recv_started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class _FailingCleanupWebSocket(_BlockingWebSocket):
    async def recv(self) -> str:
        task = asyncio.current_task()
        assert task is not None
        self.recv_task = task
        self.recv_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError as exc:
            raise RuntimeError("recv cleanup failed api-key=sentinel-secret") from exc
        raise AssertionError("unreachable")


class _TimeoutWebSocket(_BlockingWebSocket):
    async def recv(self) -> str:
        raise TimeoutError("paid stream timed out")


class _WebSocketContext:
    def __init__(
        self,
        websocket: _BlockingWebSocket,
        *,
        entered: asyncio.Event | None = None,
        exited: asyncio.Event | None = None,
    ) -> None:
        self.websocket = websocket
        self.entered = entered
        self.exited = exited

    async def __aenter__(self) -> _BlockingWebSocket:
        if self.entered is not None:
            self.entered.set()
        return self.websocket

    async def __aexit__(self, *_: object) -> None:
        if self.exited is not None:
            self.exited.set()
        return None


class _StreamingWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self.messages = iter(messages)

    async def send(self, _: str) -> None:
        return None

    def __aiter__(self) -> "_StreamingWebSocket":
        return self

    async def __anext__(self) -> str:
        try:
            return next(self.messages)
        except StopIteration:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")


class _RuntimeState:
    def __init__(self) -> None:
        self.status = SimpleNamespace(value="running")
        self.settings = SimpleNamespace(
            detect_new_tokens=True,
            launch_source="pumpportal",
            launch_interval_seconds=1.0,
            max_trade_subscriptions=1,
        )
        self.source_status = SourceStatus(source="pumpportal")
        self.solana_logs_status = SourceStatus(source="solana_logs")
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def add_event(self, level: str, message: str, **details: object) -> None:
        self.events.append((level, message, details))

    def enforce_live_auth_startup_policy(self, _: bool) -> None:
        return None

    def preferred_shadow_trade_mints(self) -> list[str]:
        return []


class _SlowCancellationSource(PumpPortalLaunchSource):
    def __init__(self) -> None:
        super().__init__(ws_url="wss://example.invalid", max_trade_subscriptions=1)
        self.child_tasks: list[asyncio.Task[None]] = []
        self.children_started = asyncio.Event()
        self.cancel_launch = asyncio.Event()
        self.trade_cancelled = asyncio.Event()
        self.release_cleanup = asyncio.Event()
        self._started_count = 0

    def _record_child(self) -> None:
        task = asyncio.current_task()
        assert task is not None
        self.child_tasks.append(task)
        self._started_count += 1
        if self._started_count == 2:
            self.children_started.set()

    async def _run_launch_stream(
        self,
        queue: asyncio.Queue[LaunchEvent],
        status: SourceStatus,
        subscription_queue: asyncio.Queue[str],
    ) -> None:
        self._record_child()
        await self.cancel_launch.wait()
        raise asyncio.CancelledError

    async def _run_trade_stream(
        self,
        queue: asyncio.Queue[LaunchEvent],
        status: SourceStatus,
        subscription_queue: asyncio.Queue[str],
    ) -> None:
        self._record_child()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.trade_cancelled.set()
            while not self.release_cleanup.is_set():
                try:
                    await self.release_cleanup.wait()
                except asyncio.CancelledError:
                    continue
            raise


class SourceCancellationTests(unittest.IsolatedAsyncioTestCase):
    def test_single_trade_slot_waits_for_evidence_dwell_before_rotation(self) -> None:
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid",
            max_trade_subscriptions=1,
        )

        self.assertFalse(source._trade_subscription_can_rotate(100.0, 699.9))
        self.assertTrue(source._trade_subscription_can_rotate(100.0, 700.0))

    async def test_trade_stream_reconnect_never_exceeds_subscription_cap(self) -> None:
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid",
            max_trade_subscriptions=1,
        )
        event_queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        subscription_queue: asyncio.Queue[str] = asyncio.Queue()
        subscription_queue.put_nowait("Mint111")
        status = SourceStatus(source="pumpportal")
        reconnect_websocket = _BlockingWebSocket()
        first_connection_exited = asyncio.Event()
        reconnect_entered = asyncio.Event()
        stream_task: asyncio.Task[None] | None = None

        with (
            patch(
                "app.core.sources.websockets.connect",
                side_effect=[
                    _WebSocketContext(_TimeoutWebSocket(), exited=first_connection_exited),
                    _WebSocketContext(reconnect_websocket, entered=reconnect_entered),
                ],
            ),
            patch("app.core.sources.asyncio.sleep", return_value=None),
        ):
            try:
                stream_task = asyncio.create_task(
                    source._run_trade_stream(event_queue, status, subscription_queue)
                )
                await asyncio.wait_for(first_connection_exited.wait(), timeout=1)
                subscription_queue.put_nowait("Mint222")
                await asyncio.wait_for(reconnect_entered.wait(), timeout=1)

                self.assertEqual(status.active_trade_subscriptions, 1)
                self.assertEqual(status.trade_reconnect_events, 1)
                self.assertEqual(status.trade_reconnect_attempts, 0)
                self.assertEqual(status.last_disconnect_stream, "trade")
                self.assertEqual(status.last_recovered_stream, "trade")
                self.assertEqual(status.pumpportal_funding_message, "")
                self.assertIsNotNone(status.last_disconnect_at)
                self.assertIsNotNone(status.last_recovered_at)
                assert status.last_disconnect_at is not None
                assert status.last_recovered_at is not None
                self.assertGreaterEqual(status.last_recovered_at, status.last_disconnect_at)
                self.assertEqual(reconnect_websocket.sent[0], {"method": "subscribeTokenTrade", "keys": ["Mint111"]})
            finally:
                if stream_task is not None:
                    stream_task.cancel()
                    await asyncio.gather(stream_task, return_exceptions=True)

    async def test_launch_stream_retains_recovered_disconnect_evidence(self) -> None:
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid?api-key=redacted",
            max_trade_subscriptions=0,
        )
        event_queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        subscription_queue: asyncio.Queue[str] = asyncio.Queue()
        status = SourceStatus(source="pumpportal")
        reconnect_entered = asyncio.Event()
        recovered_websocket = _StreamingWebSocket([])
        stream_task: asyncio.Task[None] | None = None

        with (
            patch(
                "app.core.sources.websockets.connect",
                side_effect=[
                    TimeoutError("network changed"),
                    _WebSocketContext(recovered_websocket, entered=reconnect_entered),
                ],
            ),
            patch("app.core.sources.asyncio.sleep", return_value=None),
        ):
            try:
                stream_task = asyncio.create_task(
                    source._run_launch_stream(event_queue, status, subscription_queue)
                )
                await asyncio.wait_for(reconnect_entered.wait(), timeout=1)

                self.assertEqual(status.status, "connected")
                self.assertEqual(status.reconnect_attempts, 0)
                self.assertEqual(status.reconnect_events, 1)
                self.assertEqual(status.last_disconnect_stream, "launch")
                self.assertEqual(status.last_recovered_stream, "launch")
                self.assertIsNotNone(status.last_disconnect_at)
                self.assertIsNotNone(status.last_recovered_at)
                assert status.last_disconnect_at is not None
                assert status.last_recovered_at is not None
                self.assertGreaterEqual(status.last_recovered_at, status.last_disconnect_at)
            finally:
                if stream_task is not None:
                    stream_task.cancel()
                    await asyncio.gather(stream_task, return_exceptions=True)

    async def test_launch_retries_count_one_incident_until_recovery(self) -> None:
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid?api-key=redacted",
            max_trade_subscriptions=0,
        )
        event_queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        subscription_queue: asyncio.Queue[str] = asyncio.Queue()
        status = SourceStatus(source="pumpportal")
        reconnect_entered = asyncio.Event()
        stream_task: asyncio.Task[None] | None = None

        with (
            patch(
                "app.core.sources.websockets.connect",
                side_effect=[
                    TimeoutError("network unavailable"),
                    TimeoutError("network unavailable"),
                    _WebSocketContext(_StreamingWebSocket([]), entered=reconnect_entered),
                ],
            ),
            patch("app.core.sources.asyncio.sleep", return_value=None),
        ):
            try:
                stream_task = asyncio.create_task(
                    source._run_launch_stream(event_queue, status, subscription_queue)
                )
                await asyncio.wait_for(reconnect_entered.wait(), timeout=1)

                self.assertEqual(status.reconnect_events, 1)
                self.assertEqual(status.reconnect_attempts, 0)
                self.assertEqual(status.last_recovered_stream, "launch")
            finally:
                if stream_task is not None:
                    stream_task.cancel()
                    await asyncio.gather(stream_task, return_exceptions=True)

    async def test_candidate_preempts_ordinary_launch_without_second_subscription(self) -> None:
        preferred: list[str] = []
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid",
            max_trade_subscriptions=1,
            preferred_trade_mints=lambda: list(preferred),
            preference_poll_seconds=0.01,
        )
        event_queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        subscription_queue: asyncio.Queue[str] = asyncio.Queue()
        subscription_queue.put_nowait("OrdinaryMint")
        status = SourceStatus(source="pumpportal")
        websocket = _BlockingWebSocket()

        with patch("app.core.sources.websockets.connect", return_value=_WebSocketContext(websocket)):
            task = asyncio.create_task(source._run_trade_stream(event_queue, status, subscription_queue))
            try:
                await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)
                websocket.sent_event.clear()
                preferred[:] = ["CandidateMint"]
                await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)
                for _ in range(20):
                    if {"method": "subscribeTokenTrade", "keys": ["CandidateMint"]} in websocket.sent:
                        break
                    websocket.sent_event.clear()
                    await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)

                self.assertIn({"method": "unsubscribeTokenTrade", "keys": ["OrdinaryMint"]}, websocket.sent)
                self.assertIn({"method": "subscribeTokenTrade", "keys": ["CandidateMint"]}, websocket.sent)
                self.assertLessEqual(status.active_trade_subscriptions, 1)
                self.assertEqual(status.trade_subscription_priority, "shadow_candidate")
                self.assertEqual(status.preferred_trade_mint_prefix, "Candidat")
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_candidate_slot_moves_to_next_authoritative_preference(self) -> None:
        preferred = ["CandidateOne"]
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid",
            max_trade_subscriptions=1,
            preferred_trade_mints=lambda: list(preferred),
            preference_poll_seconds=0.01,
        )
        event_queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        subscription_queue: asyncio.Queue[str] = asyncio.Queue()
        subscription_queue.put_nowait("OrdinaryMint")
        status = SourceStatus(source="pumpportal")
        websocket = _BlockingWebSocket()

        with patch("app.core.sources.websockets.connect", return_value=_WebSocketContext(websocket)):
            task = asyncio.create_task(source._run_trade_stream(event_queue, status, subscription_queue))
            try:
                await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)
                preferred[:] = ["CandidateTwo"]
                for _ in range(20):
                    if {"method": "subscribeTokenTrade", "keys": ["CandidateTwo"]} in websocket.sent:
                        break
                    websocket.sent_event.clear()
                    await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)

                self.assertIn({"method": "subscribeTokenTrade", "keys": ["CandidateOne"]}, websocket.sent)
                self.assertIn({"method": "unsubscribeTokenTrade", "keys": ["CandidateOne"]}, websocket.sent)
                self.assertIn({"method": "subscribeTokenTrade", "keys": ["CandidateTwo"]}, websocket.sent)
                self.assertLessEqual(status.active_trade_subscriptions, 1)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_transient_preference_error_keeps_active_candidate(self) -> None:
        calls = 0
        def preferred() -> list[str]:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise sqlite3.OperationalError("database locked")
            return ["CandidateOne"]
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid", max_trade_subscriptions=1,
            preferred_trade_mints=preferred, preference_poll_seconds=0.01,
        )
        queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        subscriptions: asyncio.Queue[str] = asyncio.Queue()
        subscriptions.put_nowait("OrdinaryMint")
        status = SourceStatus(source="pumpportal")
        websocket = _BlockingWebSocket()
        with patch("app.core.sources.websockets.connect", return_value=_WebSocketContext(websocket)):
            task = asyncio.create_task(source._run_trade_stream(queue, status, subscriptions))
            try:
                await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)
                await asyncio.sleep(0.05)
                self.assertNotIn({"method": "unsubscribeTokenTrade", "keys": ["CandidateOne"]}, websocket.sent)
                self.assertEqual(status.trade_subscription_priority, "shadow_candidate")
            finally:
                task.cancel(); await asyncio.gather(task, return_exceptions=True)

    async def test_candidate_reserves_one_slot_without_dropping_other_ordinary_slots(self) -> None:
        preferred: list[str] = []
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid", max_trade_subscriptions=2,
            preferred_trade_mints=lambda: list(preferred), preference_poll_seconds=0.01,
        )
        queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        subscriptions: asyncio.Queue[str] = asyncio.Queue()
        subscriptions.put_nowait("OrdinaryOne"); subscriptions.put_nowait("OrdinaryTwo")
        status = SourceStatus(source="pumpportal")
        websocket = _BlockingWebSocket()
        with patch("app.core.sources.websockets.connect", return_value=_WebSocketContext(websocket)):
            task = asyncio.create_task(source._run_trade_stream(queue, status, subscriptions))
            try:
                for _ in range(20):
                    if {"method": "subscribeTokenTrade", "keys": ["OrdinaryTwo"]} in websocket.sent:
                        break
                    websocket.sent_event.clear(); await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)
                preferred[:] = ["CandidateMint"]
                for _ in range(20):
                    if {"method": "subscribeTokenTrade", "keys": ["CandidateMint"]} in websocket.sent:
                        break
                    websocket.sent_event.clear(); await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)
                unsubscribed = [m["keys"][0] for m in websocket.sent if m["method"] == "unsubscribeTokenTrade"]
                self.assertEqual(len(unsubscribed), 1)
                self.assertEqual(status.active_trade_subscriptions, 2)
            finally:
                task.cancel(); await asyncio.gather(task, return_exceptions=True)

    async def test_candidate_present_at_startup_fills_spare_ordinary_slot(self) -> None:
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid", max_trade_subscriptions=2,
            preferred_trade_mints=lambda: ["CandidateMint"], preference_poll_seconds=0.01,
        )
        queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        subscriptions: asyncio.Queue[str] = asyncio.Queue()
        subscriptions.put_nowait("OrdinaryOne")
        status = SourceStatus(source="pumpportal")
        websocket = _BlockingWebSocket()
        with patch("app.core.sources.websockets.connect", return_value=_WebSocketContext(websocket)):
            task = asyncio.create_task(source._run_trade_stream(queue, status, subscriptions))
            try:
                for _ in range(20):
                    if {"method": "subscribeTokenTrade", "keys": ["OrdinaryOne"]} in websocket.sent:
                        break
                    websocket.sent_event.clear(); await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)
                self.assertIn({"method": "subscribeTokenTrade", "keys": ["CandidateMint"]}, websocket.sent)
                self.assertIn({"method": "subscribeTokenTrade", "keys": ["OrdinaryOne"]}, websocket.sent)
                self.assertEqual(status.active_trade_subscriptions, 2)
            finally:
                task.cancel(); await asyncio.gather(task, return_exceptions=True)

    async def test_solana_logs_source_does_not_queue_failed_transactions(self) -> None:
        failed = json.dumps(
            {
                "params": {
                    "result": {
                        "context": {"slot": 1},
                        "value": {"signature": "SigFailed", "err": {"InstructionError": [0, "Custom"]}, "logs": []},
                    }
                }
            }
        )
        successful = json.dumps(
            {
                "params": {
                    "result": {
                        "context": {"slot": 2},
                        "value": {"signature": "SigSuccessful", "err": None, "logs": ["Program log: Instruction: Create"]},
                    }
                }
            }
        )
        websocket = _StreamingWebSocket([failed, successful])
        source = SolanaLogsSource("wss://example.invalid", "PumpFunProgram111")
        queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        status = SourceStatus(source="solana_logs")

        with patch("app.core.sources.websockets.connect", return_value=_WebSocketContext(websocket)):
            run_task = asyncio.create_task(source.run(queue, status))
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1)
                self.assertEqual(event.raw_payload["params"]["result"]["value"]["signature"], "SigSuccessful")
                self.assertTrue(queue.empty())
                self.assertEqual(status.failed_events_seen, 1)
                self.assertEqual(status.events_received, 1)
            finally:
                run_task.cancel()
                await asyncio.gather(run_task, return_exceptions=True)

    async def test_solana_logs_source_queues_only_create_notifications(self) -> None:
        trade = json.dumps(
            {
                "params": {
                    "result": {
                        "context": {"slot": 3},
                        "value": {"signature": "SigTrade", "err": None, "logs": ["Program log: Instruction: Buy"]},
                    }
                }
            }
        )
        create = json.dumps(
            {
                "params": {
                    "result": {
                        "context": {"slot": 4},
                        "value": {"signature": "SigCreate", "err": None, "logs": ["Program log: Instruction: Create"]},
                    }
                }
            }
        )
        websocket = _StreamingWebSocket([trade, create])
        source = SolanaLogsSource("wss://example.invalid", "PumpFunProgram111")
        queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        status = SourceStatus(source="solana_logs")

        with patch("app.core.sources.websockets.connect", return_value=_WebSocketContext(websocket)):
            run_task = asyncio.create_task(source.run(queue, status))
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1)
                self.assertEqual(event.raw_payload["params"]["result"]["value"]["signature"], "SigCreate")
                self.assertTrue(queue.empty())
                self.assertEqual(status.raw_events_seen, 2)
                self.assertEqual(status.events_received, 1)
            finally:
                run_task.cancel()
                await asyncio.gather(run_task, return_exceptions=True)

    async def test_ensure_source_task_redacts_completed_failure_status_and_event(self) -> None:
        async def failed_source_root() -> None:
            raise RuntimeError("source failed api-key=sentinel-secret")

        previous_state = main_app.state
        previous_source_task = main_app.source_task
        previous_source_key = main_app.source_key
        state = _RuntimeState()
        state.settings.detect_new_tokens = False
        captured: list[tuple[str, str]] = []
        state.add_event = lambda _, message, **__: captured.append(
            (message, state.source_status.message)
        )
        fault_task = asyncio.create_task(failed_source_root())
        await asyncio.wait({fault_task})
        main_app.state = state
        main_app.source_task = fault_task
        main_app.source_key = ("pumpportal", 1.0, 1)

        try:
            await main_app.ensure_source_task()
        finally:
            main_app.state = previous_state
            main_app.source_task = previous_source_task
            main_app.source_key = previous_source_key

        encoded_diagnostics = str(captured)
        self.assertIn("RuntimeError", encoded_diagnostics)
        self.assertNotIn("sentinel-secret", encoded_diagnostics)

    async def test_ensure_solana_task_redacts_completed_failure_status_and_event(self) -> None:
        async def failed_solana_root() -> None:
            raise RuntimeError("solana failed api-key=sentinel-secret")

        previous_state = main_app.state
        previous_solana_task = main_app.solana_logs_task
        previous_solana_key = main_app.solana_logs_key
        state = _RuntimeState()
        state.settings.detect_new_tokens = False
        captured: list[tuple[str, str]] = []
        state.add_event = lambda _, message, **__: captured.append(
            (message, state.solana_logs_status.message)
        )
        fault_task = asyncio.create_task(failed_solana_root())
        await asyncio.wait({fault_task})
        main_app.state = state
        main_app.solana_logs_task = fault_task
        main_app.solana_logs_key = ("wss://example.invalid", "Mint111")

        try:
            await main_app.ensure_solana_logs_task()
        finally:
            main_app.state = previous_state
            main_app.solana_logs_task = previous_solana_task
            main_app.solana_logs_key = previous_solana_key

        encoded_diagnostics = str(captured)
        self.assertIn("RuntimeError", encoded_diagnostics)
        self.assertNotIn("sentinel-secret", encoded_diagnostics)

    async def test_stop_runtime_tasks_consumes_already_failed_source_root(self) -> None:
        async def failed_source_root() -> None:
            raise RuntimeError("source root failed before stop api-key=sentinel-secret")

        previous_state = main_app.state
        previous_source_task = main_app.source_task
        previous_source_key = main_app.source_key
        previous_solana_task = main_app.solana_logs_task
        previous_solana_key = main_app.solana_logs_key
        previous_launch_queue = main_app.launch_queue
        loop = asyncio.get_running_loop()
        previous_exception_handler = loop.get_exception_handler()
        exception_contexts: list[dict[str, object]] = []
        loop.set_exception_handler(lambda _, context: exception_contexts.append(context))
        fault_task = asyncio.create_task(failed_source_root())
        await asyncio.wait({fault_task})
        main_app.state = _RuntimeState()
        main_app.source_task = fault_task
        main_app.source_key = ("pumpportal", 1.0, 1)
        main_app.solana_logs_task = None
        main_app.solana_logs_key = None
        main_app.launch_queue = asyncio.Queue()

        try:
            result = await main_app.stop_runtime_tasks()
            events = list(main_app.state.events)
        finally:
            main_app.state = previous_state
            main_app.source_task = previous_source_task
            main_app.source_key = previous_source_key
            main_app.solana_logs_task = previous_solana_task
            main_app.solana_logs_key = previous_solana_key
            main_app.launch_queue = previous_launch_queue
            del fault_task
            gc.collect()
            await asyncio.sleep(0)
            loop.set_exception_handler(previous_exception_handler)

        encoded_diagnostics = f"{result['source_stop_warning']} {events}"
        self.assertIn("RuntimeError", encoded_diagnostics)
        self.assertNotIn("sentinel-secret", encoded_diagnostics)
        self.assertEqual(exception_contexts, [])

    async def test_source_timeout_retains_ownership_and_deduplicates_late_cleanup(self) -> None:
        root_started = asyncio.Event()
        cancellation_started = asyncio.Event()
        release_cleanup = asyncio.Event()

        async def stubborn_source_root() -> None:
            root_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellation_started.set()
                while not release_cleanup.is_set():
                    try:
                        await release_cleanup.wait()
                    except asyncio.CancelledError:
                        continue
                raise RuntimeError("late source cleanup failed")

        previous_state = main_app.state
        previous_source_task = main_app.source_task
        previous_source_key = main_app.source_key
        previous_solana_task = main_app.solana_logs_task
        previous_solana_key = main_app.solana_logs_key
        previous_launch_queue = main_app.launch_queue
        state = _RuntimeState()
        root_task = asyncio.create_task(stubborn_source_root())
        main_app.state = state
        main_app.source_task = root_task
        main_app.source_key = ("mock", 99.0, 0)
        main_app.solana_logs_task = None
        main_app.solana_logs_key = None
        main_app.launch_queue = asyncio.Queue()
        original_cancel_and_wait = main_app._cancel_and_wait_source_tasks

        async def fast_cancel_and_wait(named_tasks: list[tuple[str, asyncio.Task]]) -> list[str]:
            return await original_cancel_and_wait(named_tasks, timeout_seconds=0.01)

        try:
            await asyncio.wait_for(root_started.wait(), timeout=1)
            with patch(
                "app.main._cancel_and_wait_source_tasks",
                side_effect=fast_cancel_and_wait,
            ):
                first = await main_app.stop_runtime_tasks()
                await asyncio.wait_for(cancellation_started.wait(), timeout=1)
                second = await main_app.stop_runtime_tasks()
                with patch("app.main.make_source") as replacement_factory:
                    await main_app.ensure_source_task()
                    replacement_factory.assert_not_called()

            self.assertIs(main_app.source_task, root_task)
            self.assertEqual(state.source_status.status, "error")
            self.assertTrue(first["source_stop_warning"])
            self.assertEqual(second["source_stop_warning"], "")

            release_cleanup.set()
            await asyncio.wait({root_task}, timeout=1)
            await asyncio.sleep(0)
            await main_app.stop_runtime_tasks()

            timeout_events = [
                message
                for _, message, _ in state.events
                if "did not acknowledge cancellation" in message
            ]
            late_failure_events = [
                message
                for _, message, _ in state.events
                if "Source cleanup failure (RuntimeError)" in message
            ]
            self.assertEqual(len(timeout_events), 1)
            self.assertEqual(len(late_failure_events), 1)
            self.assertIsNone(main_app.source_task)
        finally:
            release_cleanup.set()
            root_task.cancel()
            await asyncio.gather(root_task, return_exceptions=True)
            main_app.state = previous_state
            main_app.source_task = previous_source_task
            main_app.source_key = previous_source_key
            main_app.solana_logs_task = previous_solana_task
            main_app.solana_logs_key = previous_solana_key
            main_app.launch_queue = previous_launch_queue

    async def test_lifespan_records_background_task_failure(self) -> None:
        async def failed_bot_loop() -> None:
            raise RuntimeError("bot loop failed during shutdown api-key=sentinel-secret")

        async def idle_loop() -> None:
            await asyncio.Event().wait()

        previous_state = main_app.state
        previous_source_task = main_app.source_task
        previous_source_key = main_app.source_key
        previous_solana_task = main_app.solana_logs_task
        previous_solana_key = main_app.solana_logs_key
        state = _RuntimeState()
        main_app.state = state
        main_app.source_task = None
        main_app.source_key = None
        main_app.solana_logs_task = None
        main_app.solana_logs_key = None

        try:
            with (
                patch("app.main.bot_loop", side_effect=failed_bot_loop),
                patch("app.main.live_audit_poll_loop", side_effect=idle_loop),
                patch("app.main.latency_probe_loop", side_effect=idle_loop),
            ):
                async with main_app.lifespan(None):
                    await asyncio.sleep(0)
        finally:
            main_app.state = previous_state
            main_app.source_task = previous_source_task
            main_app.source_key = previous_source_key
            main_app.solana_logs_task = previous_solana_task
            main_app.solana_logs_key = previous_solana_key

        encoded_events = str(state.events)
        self.assertIn("RuntimeError", encoded_events)
        self.assertNotIn("sentinel-secret", encoded_events)

    async def test_trade_stream_logs_nested_cleanup_failure_without_masking_cancellation(self) -> None:
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid",
            max_trade_subscriptions=1,
        )
        event_queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        subscription_queue = _TrackingQueue()
        subscription_queue.put_nowait("Mint111")
        websocket = _FailingCleanupWebSocket()
        stream_task: asyncio.Task[None] | None = None

        with patch(
            "app.core.sources.websockets.connect",
            return_value=_WebSocketContext(websocket),
        ):
            try:
                stream_task = asyncio.create_task(
                    source._run_trade_stream(
                        event_queue,
                        SourceStatus(source="pumpportal"),
                        subscription_queue,
                    )
                )
                await asyncio.wait_for(websocket.recv_started.wait(), timeout=1)
                await asyncio.wait_for(subscription_queue.pending_get_started.wait(), timeout=1)

                with self.assertLogs("app.core.sources", level="WARNING") as captured:
                    stream_task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await stream_task

                encoded_logs = " ".join(captured.output)
                self.assertIn("RuntimeError", encoded_logs)
                self.assertNotIn("sentinel-secret", encoded_logs)
            finally:
                cleanup_tasks = [
                    task
                    for task in (
                        stream_task,
                        websocket.recv_task,
                        subscription_queue.pending_get_task,
                    )
                    if task is not None
                ]
                for task in cleanup_tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    async def test_stop_runtime_tasks_reaps_source_root_and_descendant(self) -> None:
        child_started = asyncio.Event()
        child_finished = asyncio.Event()
        child_tasks: list[asyncio.Task[None]] = []

        async def source_child() -> None:
            child_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                child_finished.set()

        async def source_root() -> None:
            child_task = asyncio.create_task(source_child())
            child_tasks.append(child_task)
            try:
                await child_task
            finally:
                child_task.cancel()
                await asyncio.gather(child_task, return_exceptions=True)

        previous_state = main_app.state
        previous_source_task = main_app.source_task
        previous_source_key = main_app.source_key
        previous_solana_task = main_app.solana_logs_task
        previous_solana_key = main_app.solana_logs_key
        previous_launch_queue = main_app.launch_queue
        root_task = asyncio.create_task(source_root())
        main_app.state = _RuntimeState()
        main_app.source_task = root_task
        main_app.source_key = ("pumpportal", 1.0, 1)
        main_app.solana_logs_task = None
        main_app.solana_logs_key = None
        main_app.launch_queue = asyncio.Queue()

        try:
            await asyncio.wait_for(child_started.wait(), timeout=1)

            result = await main_app.stop_runtime_tasks()

            self.assertTrue(root_task.done())
            self.assertTrue(child_tasks[0].done())
            self.assertTrue(child_finished.is_set())
            self.assertTrue(result["source_task_cancelled"])
            self.assertEqual(result["source_stop_warning"], "")
        finally:
            root_task.cancel()
            for task in child_tasks:
                task.cancel()
            await asyncio.gather(root_task, *child_tasks, return_exceptions=True)
            main_app.state = previous_state
            main_app.source_task = previous_source_task
            main_app.source_key = previous_source_key
            main_app.solana_logs_task = previous_solana_task
            main_app.solana_logs_key = previous_solana_key
            main_app.launch_queue = previous_launch_queue

    async def test_source_replacement_awaits_previous_root_before_starting_new_one(self) -> None:
        previous_root_started = asyncio.Event()
        previous_root_finished = asyncio.Event()
        replacement_started = asyncio.Event()

        async def previous_root() -> None:
            previous_root_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                previous_root_finished.set()

        class _ReplacementSource:
            async def run(
                self,
                queue: asyncio.Queue[LaunchEvent],
                status: SourceStatus,
            ) -> None:
                replacement_started.set()
                await asyncio.Event().wait()

        previous_state = main_app.state
        previous_source_task = main_app.source_task
        previous_source_key = main_app.source_key
        previous_launch_queue = main_app.launch_queue
        old_root_task = asyncio.create_task(previous_root())
        main_app.state = _RuntimeState()
        main_app.source_task = old_root_task
        main_app.source_key = ("mock", 99.0, 0)
        main_app.launch_queue = asyncio.Queue()

        try:
            await asyncio.wait_for(previous_root_started.wait(), timeout=1)
            with patch("app.main.make_source", return_value=_ReplacementSource()):
                await main_app.ensure_source_task()

            self.assertTrue(old_root_task.done())
            self.assertTrue(previous_root_finished.is_set())
            self.assertIsNot(main_app.source_task, old_root_task)
            await asyncio.wait_for(replacement_started.wait(), timeout=1)
        finally:
            tasks = [
                task
                for task in (old_root_task, main_app.source_task)
                if task is not None
            ]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            main_app.state = previous_state
            main_app.source_task = previous_source_task
            main_app.source_key = previous_source_key
            main_app.launch_queue = previous_launch_queue

    async def test_trade_stream_cancellation_reaps_nested_wait_tasks(self) -> None:
        source = PumpPortalLaunchSource(
            ws_url="wss://example.invalid",
            max_trade_subscriptions=1,
        )
        event_queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        subscription_queue = _TrackingQueue()
        subscription_queue.put_nowait("Mint111")
        websocket = _BlockingWebSocket()
        stream_task: asyncio.Task[None] | None = None

        with patch(
            "app.core.sources.websockets.connect",
            return_value=_WebSocketContext(websocket),
        ):
            try:
                stream_task = asyncio.create_task(
                    source._run_trade_stream(
                        event_queue,
                        SourceStatus(source="pumpportal"),
                        subscription_queue,
                    )
                )
                await asyncio.wait_for(websocket.recv_started.wait(), timeout=1)
                await asyncio.wait_for(subscription_queue.pending_get_started.wait(), timeout=1)
                recv_task = websocket.recv_task
                pending_get_task = subscription_queue.pending_get_task
                assert recv_task is not None
                assert pending_get_task is not None

                stream_task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await stream_task

                self.assertTrue(recv_task.done())
                self.assertTrue(pending_get_task.done())
            finally:
                cleanup_tasks = [
                    task
                    for task in (
                        stream_task,
                        websocket.recv_task,
                        subscription_queue.pending_get_task,
                    )
                    if task is not None
                ]
                for task in cleanup_tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    async def test_source_cancellation_awaits_launch_and_trade_children(self) -> None:
        source = _SlowCancellationSource()
        run_task = asyncio.create_task(
            source.run(
                asyncio.Queue(),
                SourceStatus(source="pumpportal"),
            )
        )

        try:
            await asyncio.wait_for(source.children_started.wait(), timeout=1)
            source.cancel_launch.set()
            await asyncio.wait_for(source.trade_cancelled.wait(), timeout=1)
            await asyncio.sleep(0)

            self.assertFalse(run_task.done())

            source.release_cleanup.set()
            with self.assertRaises(asyncio.CancelledError):
                await run_task
            self.assertTrue(all(task.done() for task in source.child_tasks))
        finally:
            source.release_cleanup.set()
            for task in [run_task, *source.child_tasks]:
                if not task.done():
                    task.cancel()
            await asyncio.gather(run_task, *source.child_tasks, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
