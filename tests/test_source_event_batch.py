import asyncio
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from app import main as main_app
from app.core.models import BotStatus, TokenSignal, TokenStatus, utc_now
from app.core.sources import LaunchEvent
from app.core.state import BotState


class SourceEventBatchTests(unittest.TestCase):
    def make_state(self, directory: str) -> BotState:
        state = BotState(database_path=str(Path(directory) / "test.db"))
        state.status = BotStatus.RUNNING
        return state

    def make_token(self, token_id: str, mint: str, *, status: TokenStatus = TokenStatus.DETECTED) -> TokenSignal:
        token = TokenSignal(
            id=token_id,
            symbol="ARC",
            name="Arc Test",
            mint=mint,
            creator=f"creator_{token_id}",
            detected_at=utc_now(),
            age_seconds=5,
            buy_velocity=0.9,
            sell_pressure=0.1,
            metadata_score=0.9,
            current_price=0.00001,
        )
        token.status = status
        return token

    def make_trade(self, sequence: int, mint: str | None) -> LaunchEvent:
        return LaunchEvent(
            source="pumpportal",
            received_at=utc_now(),
            raw_payload={
                "sequence": sequence,
                "txType": "buy",
                "mint": mint,
                "marketCapSol": 20.0,
            },
            token=None,
            message=f"trade {sequence}",
            kind="trade",
            mint=mint,
            trade_side="buy",
        )

    async def drain(self, state: BotState, events: list[LaunchEvent]) -> asyncio.Queue[LaunchEvent]:
        previous_state = main_app.state
        previous_queue = main_app.launch_queue
        queue: asyncio.Queue[LaunchEvent] = asyncio.Queue()
        main_app.state = state
        main_app.launch_queue = queue
        try:
            for event in events:
                queue.put_nowait(event)
            await main_app.drain_launch_queue()
            await asyncio.wait_for(queue.join(), timeout=0.25)
            return queue
        finally:
            main_app.state = previous_state
            main_app.launch_queue = previous_queue

    def count_active_token_hydrations(self, state: BotState) -> list[None]:
        calls: list[None] = []
        original = state._ensure_active_tokens_loaded

        def counted_hydration() -> None:
            calls.append(None)
            original()

        state._ensure_active_tokens_loaded = counted_hydration
        return calls

    def test_drain_hydrates_active_tokens_once_for_multiple_eligible_trades(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            calls = self.count_active_token_hydrations(state)

            asyncio.run(
                self.drain(
                    state,
                    [
                        self.make_trade(1, "mint_active"),
                        self.make_trade(2, "mint_active"),
                        self.make_trade(3, "mint_active"),
                    ],
                )
            )

            self.assertEqual(len(calls), 1)

    def test_mixed_batch_preserves_event_order_evidence_and_observed_price_update(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            active = self.make_token("tok_active", "mint_active", status=TokenStatus.MONITORING)
            active.entry_price = 0.00001
            active.amount_sol = 0.1
            active.opened_at = utc_now() - timedelta(minutes=1)
            state.storage.save_token(active)
            state.tokens.clear()

            launch = LaunchEvent(
                source="pumpportal",
                received_at=utc_now(),
                raw_payload={"sequence": 1, "mint": "mint_launch", "txType": "create"},
                token=self.make_token("tok_launch", "mint_launch"),
                message="launch 1",
            )
            status = LaunchEvent(
                source="solana_logs",
                received_at=utc_now(),
                raw_payload={"sequence": 2},
                token=None,
                message="verification status 2",
                kind="verification_status",
            )

            asyncio.run(
                self.drain(
                    state,
                    [launch, status, self.make_trade(3, active.mint), self.make_trade(4, active.mint)],
                )
            )

            evidence = list(reversed(state.storage.load_source_events(10)))
            updated = next(token for token in state.storage.load_all_tokens(5000) if token.id == active.id)
            self.assertEqual([event.raw_payload["sequence"] for event in evidence], [1, 2, 3, 4])
            self.assertEqual([event.status for event in evidence], ["normalized", "status", "trade", "trade"])
            self.assertEqual(updated.observed_price_updates, 2)

    def test_drain_does_not_hydrate_when_batch_has_no_eligible_trade(self) -> None:
        cases = (
            ("non-trade", True, [LaunchEvent("mock", utc_now(), {"sequence": 1}, None, message="status")]),
            ("missing mint", True, [self.make_trade(1, None)]),
            ("observed prices disabled", False, [self.make_trade(1, "mint_active")]),
        )
        for name, use_observed_prices, events in cases:
            with self.subTest(name=name), TemporaryDirectory() as directory:
                state = self.make_state(directory)
                state.settings.use_observed_prices = use_observed_prices
                calls = self.count_active_token_hydrations(state)

                asyncio.run(self.drain(state, events))

                self.assertEqual(calls, [])

    def test_direct_ingest_and_apply_calls_hydrate_by_default(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            calls = self.count_active_token_hydrations(state)
            event = self.make_trade(1, "mint_active")

            state.ingest_source_event(event)
            state.apply_observed_trade(event)

            self.assertEqual(len(calls), 2)

    def test_drain_clears_remaining_queue_and_balances_tasks_if_state_stops(self) -> None:
        with TemporaryDirectory() as directory:
            state = self.make_state(directory)
            original = state.ingest_source_event

            def stop_after_first_event(event: LaunchEvent, **kwargs: object) -> None:
                original(event, **kwargs)
                state.status = BotStatus.STOPPED

            state.ingest_source_event = stop_after_first_event
            queue = asyncio.run(
                self.drain(
                    state,
                    [
                        LaunchEvent("mock", utc_now(), {"sequence": 1}, None, message="first"),
                        LaunchEvent("mock", utc_now(), {"sequence": 2}, None, message="second"),
                    ],
                )
            )

            self.assertTrue(queue.empty())
            self.assertEqual(state.storage.count_source_events(), 1)


if __name__ == "__main__":
    unittest.main()
