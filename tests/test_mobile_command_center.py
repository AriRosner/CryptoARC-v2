import base64
import json
import sqlite3
import unittest
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth import AuthManager
from app.core.models import LiveLedgerPosition, PriceObservation, TokenSignal, TokenStatus, TradeRecord
from app.core.state import BotState
from app.core.storage import Storage
from app.mobile.contracts import MobileActionStatus, MobileRealtimeEnvelope, MobileScope


class MobileCommandCenterContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = BotState(database_path=str(Path(self.directory.name) / "test.db"))

    @contextmanager
    def mobile_client(self):
        from app import main as main_app

        previous_state = main_app.state
        previous_auth = main_app.auth
        previous_key = main_app.config.mobile_push_token_encryption_key
        main_app.state = self.state
        main_app.auth = AuthManager(password="desktop-pass")
        main_app.config.mobile_push_token_encryption_key = base64.urlsafe_b64encode(
            b"cryptoarc-mobile-push-test-key!!"
        ).decode("ascii")
        desktop_token = main_app.auth.login("desktop-pass")
        try:
            yield (
                TestClient(main_app.app),
                {"Authorization": f"Bearer {desktop_token}"},
            )
        finally:
            main_app.state = previous_state
            main_app.auth = previous_auth
            main_app.config.mobile_push_token_encryption_key = previous_key

    def claim_device(
        self,
        client: TestClient,
        desktop_headers: dict[str, str],
        *,
        name: str,
        scopes: list[str],
    ) -> dict[str, object]:
        pairing_response = client.post(
            "/api/mobile/pairing/start",
            json={
                "api_base_url": "https://node.tailnet.ts.net",
                "scopes": scopes,
            },
            headers=desktop_headers,
        )
        self.assertEqual(pairing_response.status_code, 200)
        pairing = pairing_response.json()
        claim_response = client.post(
            "/api/mobile/pairing/claim",
            json={
                "pairing_id": pairing["id"],
                "code": pairing["code"],
                "device_name": name,
                "platform": "android",
            },
        )
        self.assertEqual(claim_response.status_code, 200)
        return claim_response.json()

    def seed_portfolio(self) -> None:
        now = datetime.now(timezone.utc)
        paper = TokenSignal(
            id="token-paper-open",
            symbol="ARC",
            name="CryptoARC",
            mint="mint-paper",
            creator="creator",
            detected_at=now - timedelta(hours=2),
            status=TokenStatus.PAPER_BOUGHT,
            amount_sol=0.4,
            entry_price=0.00001,
            current_price=0.000012,
            opened_at=now - timedelta(hours=1),
            pnl_sol=0.08,
            realized_pnl_sol=0.02,
            remaining_fraction=0.5,
            unrealized_pct=20.0,
            price_source="pumpportal",
            price_confidence=0.9,
            last_observed_trade_at=now - timedelta(seconds=10),
        )
        self.state.storage.save_token(paper)
        self.state.storage.save_trade(
            TradeRecord(
                id="trade-closed",
                token_id=paper.id,
                mode="paper",
                strategy_profile="balanced",
                entry_price=0.00001,
                exit_price=0.000011,
                amount_sol=0.5,
                pnl_sol=0.05,
                entry_reason="test",
                exit_reason="take profit",
                opened_at=now - timedelta(hours=3),
                closed_at=now - timedelta(hours=2),
            )
        )
        self.state.storage.save_live_ledger_position(
            LiveLedgerPosition(
                id="live-position-1",
                created_at=now - timedelta(days=2),
                updated_at=now - timedelta(minutes=5),
                mint="mint-live",
                wallet_public_key="wallet-public",
                symbol="LIVE",
                token_balance=1000.0,
                cost_basis_sol=0.2,
                realized_pnl_sol=0.01,
                reconciliation_status="matched",
                balance_verified_at=now - timedelta(seconds=30),
            )
        )
        self.state.storage.save_price_observation(
            PriceObservation(
                id="price-live",
                source="pumpportal",
                mint="mint-live",
                observed_at=now - timedelta(minutes=5),
                price=0.00025,
                price_source="direct",
                confidence=0.95,
                accepted=True,
                selected_price=0.00025,
            )
        )

    def test_portfolio_payload_is_complete_timeframed_and_contains_no_secret_fields(self) -> None:
        from app import main as main_app

        self.seed_portfolio()
        with self.mobile_client():
            for timeframe in ("1d", "1w", "1m", "all"):
                with self.subTest(timeframe=timeframe):
                    payload = main_app.mobile_service.portfolio(
                        device={"id": "mobile-portfolio"},
                        timeframe=timeframe,
                    )
                    self.assertEqual(payload["artifact_type"], "cryptoarc_mobile_portfolio")
                    self.assertEqual(payload["timeframe"], timeframe)
                    self.assertIn("equity_sol", payload["summary"])
                    self.assertIn("win_rate_pct", payload["summary"])
                    self.assertIn("health_score", payload["summary"])
                    self.assertIn("allocation", payload)
                    self.assertIn("series", payload)
                    self.assertEqual(
                        {position["id"] for position in payload["positions"]},
                        {"paper:token-paper-open", "live-position-1"},
                    )
                    self.assertTrue(payload["freshness"]["approximate_pnl"])
                    self.assertNotRegex(
                        json.dumps(payload).lower(),
                        r"private_key|seed|token_hash",
                    )

    def test_position_detail_preserves_stable_id_and_marks_stale_approximate_pnl(self) -> None:
        from app import main as main_app

        self.seed_portfolio()
        with self.mobile_client():
            first = main_app.mobile_service.positions(device={"id": "mobile-portfolio"})
            second = main_app.mobile_service.positions(device={"id": "mobile-portfolio"})
            self.assertEqual(
                [position["id"] for position in first["positions"]],
                [position["id"] for position in second["positions"]],
            )

            detail = main_app.mobile_service.position(
                device={"id": "mobile-portfolio"},
                position_id="live-position-1",
            )
            self.assertEqual(detail["id"], "live-position-1")
            self.assertFalse(detail["mark"]["fresh"])
            self.assertTrue(detail["pnl"]["approximate"])

    def test_portfolio_uses_remaining_paper_basis_without_double_counting_partial_exit_pnl(self) -> None:
        from app import main as main_app

        self.seed_portfolio()
        with self.mobile_client():
            payload = main_app.mobile_service.portfolio(
                device={"id": "mobile-portfolio"},
                timeframe="all",
            )
            paper = next(
                position
                for position in payload["positions"]
                if position["id"] == "paper:token-paper-open"
            )

            self.assertAlmostEqual(paper["cost_basis_sol"], 0.2)
            self.assertAlmostEqual(paper["realized_pnl_sol"], 0.02)
            self.assertAlmostEqual(paper["unrealized_pnl_sol"], 0.06)
            self.assertAlmostEqual(paper["value_sol"], 0.26)
            self.assertAlmostEqual(payload["summary"]["cost_basis_sol"], 0.4)
            self.assertAlmostEqual(payload["summary"]["tracked_value_sol"], 0.51)
            self.assertAlmostEqual(payload["summary"]["realized_pnl_sol"], 0.05)
            self.assertAlmostEqual(payload["summary"]["unrealized_pnl_sol"], 0.0)
            self.assertAlmostEqual(payload["summary"]["net_pnl_sol"], 0.05)
            self.assertAlmostEqual(payload["current_snapshot"]["realized_pnl_sol"], 0.03)
            self.assertAlmostEqual(payload["current_snapshot"]["unrealized_pnl_sol"], 0.11)
            self.assertAlmostEqual(payload["current_snapshot"]["net_pnl_sol"], 0.14)

    def test_portfolio_series_does_not_backfill_current_live_pnl_into_paper_history(self) -> None:
        from app import main as main_app

        self.seed_portfolio()
        with self.mobile_client():
            payload = main_app.mobile_service.portfolio(
                device={"id": "mobile-portfolio"},
                timeframe="all",
            )

            self.assertTrue(payload["series"])
            self.assertTrue(
                all(point["live_pnl_sol"] == 0.0 for point in payload["series"])
            )
            self.assertTrue(
                all(point["current_snapshot"] is False for point in payload["series"])
            )
            self.assertAlmostEqual(
                payload["current_snapshot"]["live_pnl_sol"],
                0.06,
            )

    def test_monitoring_paper_position_remains_visible_after_tick(self) -> None:
        from app import main as main_app

        now = datetime.now(timezone.utc)
        token = TokenSignal(
            id="token-after-tick",
            symbol="TICK",
            name="Ticked position",
            mint="mint-tick",
            creator="creator",
            detected_at=now - timedelta(minutes=2),
            status=TokenStatus.PAPER_BOUGHT,
            amount_sol=0.2,
            entry_price=0.00001,
            current_price=0.00001,
            opened_at=now - timedelta(minutes=1),
            last_observed_trade_at=now,
        )
        self.assertFalse(self.state.paper.tick(token, self.state.settings, 1.0))
        self.assertEqual(token.status, TokenStatus.MONITORING)
        self.state.storage.save_token(token)

        with self.mobile_client():
            payload = main_app.mobile_service.positions(
                device={"id": "mobile-portfolio"},
            )

        self.assertIn(
            "paper:token-after-tick",
            {position["id"] for position in payload["positions"]},
        )

    def test_position_percentage_is_unrealized_return_on_remaining_basis(self) -> None:
        from app import main as main_app

        now = datetime.now(timezone.utc)
        self.state.storage.save_live_ledger_position(
            LiveLedgerPosition(
                id="live-partial",
                created_at=now - timedelta(days=2),
                updated_at=now,
                mint="mint-partial",
                wallet_public_key="wallet-public",
                symbol="PART",
                token_balance=1000.0,
                cost_basis_sol=0.1,
                realized_pnl_sol=0.09,
                unrealized_pnl_sol=0.01,
                mark_price_sol=0.00011,
                mark_price_source="test",
                mark_price_confidence=1.0,
                mark_price_at=now,
                reconciliation_status="matched",
            )
        )
        with patch.object(self.state, "_refresh_live_position_estimate", return_value=None):
            with self.mobile_client():
                detail = main_app.mobile_service.position(
                    device={"id": "mobile-portfolio"},
                    position_id="live-partial",
                )

        self.assertEqual(detail["pnl_pct"], 10.0)
        self.assertEqual(detail["pnl"]["percentage"], 10.0)

    def test_selected_period_performance_is_separate_from_current_position_snapshot(self) -> None:
        from app import main as main_app

        self.seed_portfolio()
        old = datetime.now(timezone.utc) - timedelta(days=10)
        self.state.storage.save_trade(
            TradeRecord(
                id="trade-old",
                token_id="old-token",
                mode="paper",
                strategy_profile="balanced",
                entry_price=1.0,
                exit_price=2.0,
                amount_sol=1.0,
                pnl_sol=0.5,
                entry_reason="test",
                exit_reason="test",
                opened_at=old - timedelta(hours=1),
                closed_at=old,
            )
        )
        with self.mobile_client():
            one_day = main_app.mobile_service.portfolio(
                device={"id": "mobile-portfolio"},
                timeframe="1d",
            )
            all_time = main_app.mobile_service.portfolio(
                device={"id": "mobile-portfolio"},
                timeframe="all",
            )

        self.assertAlmostEqual(one_day["summary"]["selected_period_realized_pnl_sol"], 0.05)
        self.assertAlmostEqual(one_day["summary"]["net_pnl_sol"], 0.05)
        self.assertAlmostEqual(all_time["summary"]["selected_period_realized_pnl_sol"], 0.55)
        self.assertAlmostEqual(all_time["summary"]["net_pnl_sol"], 0.55)
        for key in (
            "tracked_value_sol",
            "cost_basis_sol",
            "realized_pnl_sol",
            "unrealized_pnl_sol",
            "net_pnl_sol",
            "paper_pnl_sol",
            "live_pnl_sol",
            "open_positions",
            "approximate",
        ):
            self.assertEqual(
                one_day["current_snapshot"][key],
                all_time["current_snapshot"][key],
            )
        self.assertAlmostEqual(one_day["current_snapshot"]["net_pnl_sol"], 0.14)

    def test_future_and_naive_marks_fail_closed_without_crashing(self) -> None:
        from app import main as main_app

        self.seed_portfolio()
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        paper = next(
            token
            for token in self.state.storage.load_all_tokens(50)
            if token.id == "token-paper-open"
        )
        paper.last_observed_trade_at = future
        self.state.storage.save_token(paper)
        self.state.storage.save_price_observation(
            PriceObservation(
                id="price-live-naive",
                source="pumpportal",
                mint="mint-live",
                observed_at=datetime(2099, 1, 1),
                price=0.00025,
                price_source="direct",
                confidence=0.95,
                accepted=True,
                selected_price=0.00025,
            )
        )

        with self.mobile_client():
            payload = main_app.mobile_service.positions(
                device={"id": "mobile-portfolio"},
            )
            live_detail = main_app.mobile_service.position(
                device={"id": "mobile-portfolio"},
                position_id="live-position-1",
            )

        positions = {position["id"]: position for position in payload["positions"]}
        self.assertFalse(positions["paper:token-paper-open"]["mark_fresh"])
        self.assertIsNone(positions["paper:token-paper-open"]["mark_age_seconds"])
        self.assertFalse(positions["live-position-1"]["mark_fresh"])
        self.assertGreater(positions["live-position-1"]["mark_age_seconds"], 0)
        self.assertAlmostEqual(live_detail["mark"]["price_sol"], 0.00025)
        self.assertAlmostEqual(live_detail["value_sol"], 0.25)
        self.assertAlmostEqual(live_detail["pnl"]["unrealized_sol"], 0.05)
        self.assertGreater(live_detail["mark"]["confidence"], 0)
        self.assertIn(payload["freshness"]["status"], {"stale", "unavailable"})

    def test_portfolio_routes_require_scope_and_unknown_position_is_404(self) -> None:
        self.seed_portfolio()
        with self.mobile_client() as (client, desktop_headers):
            denied = self.claim_device(
                client,
                desktop_headers,
                name="Monitor only",
                scopes=[MobileScope.MONITOR],
            )
            allowed = self.claim_device(
                client,
                desktop_headers,
                name="Portfolio reader",
                scopes=[MobileScope.PORTFOLIO_READ],
            )
            denied_headers = {"Authorization": f"Bearer {denied['token']}"}
            allowed_headers = {"Authorization": f"Bearer {allowed['token']}"}

            self.assertEqual(
                client.get("/api/mobile/portfolio?timeframe=1w", headers=denied_headers).status_code,
                403,
            )
            portfolio_response = client.get(
                "/api/mobile/portfolio?timeframe=1w",
                headers=allowed_headers,
            )
            positions_response = client.get(
                "/api/mobile/positions",
                headers=allowed_headers,
            )
            unknown_response = client.get(
                "/api/mobile/positions/missing-position",
                headers=allowed_headers,
            )

            self.assertEqual(portfolio_response.status_code, 200)
            self.assertEqual(portfolio_response.json()["timeframe"], "1w")
            self.assertEqual(positions_response.status_code, 200)
            self.assertEqual(unknown_response.status_code, 404)

    def test_portfolio_routes_distinguish_authentication_from_scope_and_revocation(self) -> None:
        routes = (
            "/api/mobile/portfolio?timeframe=1d",
            "/api/mobile/positions",
            "/api/mobile/positions/paper:token-paper-open",
        )
        self.seed_portfolio()
        with self.mobile_client() as (client, desktop_headers):
            monitor = self.claim_device(
                client,
                desktop_headers,
                name="Monitor",
                scopes=[MobileScope.MONITOR],
            )
            allowed = self.claim_device(
                client,
                desktop_headers,
                name="Allowed",
                scopes=[MobileScope.PORTFOLIO_READ],
            )
            expired = self.claim_device(
                client,
                desktop_headers,
                name="Expired",
                scopes=[MobileScope.PORTFOLIO_READ],
            )
            expired_device = self.state.storage.load_mobile_device(
                str(expired["device"]["id"])
            )
            self.assertIsNotNone(expired_device)
            expired_device["expires_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat()
            self.state.storage.save_mobile_device(expired_device)

            for route in routes:
                with self.subTest(route=route, credential="missing"):
                    self.assertEqual(client.get(route).status_code, 401)
                with self.subTest(route=route, credential="invalid"):
                    self.assertEqual(
                        client.get(
                            route,
                            headers={"Authorization": "Bearer invalid-mobile-token"},
                        ).status_code,
                        401,
                    )
                with self.subTest(route=route, credential="expired"):
                    self.assertEqual(
                        client.get(
                            route,
                            headers={"Authorization": f"Bearer {expired['token']}"},
                        ).status_code,
                        401,
                    )
                with self.subTest(route=route, credential="missing_scope"):
                    self.assertEqual(
                        client.get(
                            route,
                            headers={"Authorization": f"Bearer {monitor['token']}"},
                        ).status_code,
                        403,
                    )
                with self.subTest(route=route, credential="allowed"):
                    self.assertEqual(
                        client.get(
                            route,
                            headers={"Authorization": f"Bearer {allowed['token']}"},
                        ).status_code,
                        200,
                    )

            self.state.revoke_mobile_device(str(allowed["device"]["id"]))
            for route in routes:
                with self.subTest(route=route, credential="revoked"):
                    response = client.get(
                        route,
                        headers={"Authorization": f"Bearer {allowed['token']}"},
                    )
                    self.assertEqual(response.status_code, 401)
                    self.assertNotIn("revoked", response.text.lower())

    def test_portfolio_route_rejects_invalid_timeframe(self) -> None:
        self.seed_portfolio()
        with self.mobile_client() as (client, desktop_headers):
            allowed = self.claim_device(
                client,
                desktop_headers,
                name="Portfolio",
                scopes=[MobileScope.PORTFOLIO_READ],
            )
            response = client.get(
                "/api/mobile/portfolio?timeframe=quarter",
                headers={"Authorization": f"Bearer {allowed['token']}"},
            )
        self.assertEqual(response.status_code, 422)

    def test_portfolio_allocation_uses_only_positive_values_and_route_validates(self) -> None:
        self.seed_portfolio()
        now = datetime.now(timezone.utc)
        for token_id, symbol, pnl in (
            ("token-negative-value", "NEG", -0.2),
            ("token-zero-value", "ZERO", -0.1),
        ):
            self.state.storage.save_token(
                TokenSignal(
                    id=token_id,
                    symbol=symbol,
                    name=symbol,
                    mint=f"mint-{symbol.lower()}",
                    creator="creator",
                    detected_at=now,
                    status=TokenStatus.MONITORING,
                    amount_sol=0.1,
                    pnl_sol=pnl,
                    opened_at=now,
                    last_observed_trade_at=now,
                    price_source="test",
                    price_confidence=1.0,
                )
            )

        with self.mobile_client() as (client, desktop_headers):
            allowed = self.claim_device(
                client,
                desktop_headers,
                name="Allocation reader",
                scopes=[MobileScope.PORTFOLIO_READ],
            )
            response = client.get(
                "/api/mobile/portfolio?timeframe=all",
                headers={"Authorization": f"Bearer {allowed['token']}"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        allocation = payload["allocation"]
        self.assertTrue(all(row["value_sol"] > 0 for row in allocation))
        self.assertNotIn(
            "paper:token-negative-value",
            {row["key"] for row in allocation},
        )
        self.assertNotIn(
            "paper:token-zero-value",
            {row["key"] for row in allocation},
        )
        self.assertAlmostEqual(
            payload["summary"]["tracked_value_sol"],
            sum(row["value_sol"] for row in allocation),
        )
        self.assertTrue(
            all(0.0 <= row["percentage"] <= 100.0 for row in allocation)
        )
        self.assertEqual(
            round(sum(row["percentage"] for row in allocation), 2),
            100.0,
        )

    def test_portfolio_allocation_distributes_rounding_remainder_deterministically(
        self,
    ) -> None:
        allocation = self.state._mobile_allocation(
            [
                {
                    "id": "position-z",
                    "symbol": "Z",
                    "value_sol": 1.0,
                    "mode": "paper",
                },
                {
                    "id": "position-a",
                    "symbol": "A",
                    "value_sol": 1.0,
                    "mode": "paper",
                },
                {
                    "id": "position-m",
                    "symbol": "M",
                    "value_sol": 1.0,
                    "mode": "paper",
                },
            ]
        )

        self.assertEqual(
            [(row["key"], row["percentage"]) for row in allocation],
            [
                ("position-z", 33.33),
                ("position-a", 33.34),
                ("position-m", 33.33),
            ],
        )
        self.assertEqual(
            round(sum(row["percentage"] for row in allocation), 2),
            100.0,
        )

    def test_new_scopes_are_not_granted_by_legacy_control(self) -> None:
        pairing = self.state.create_mobile_pairing(
            api_base_url="https://node.tailnet.ts.net",
            scopes=["mobile:monitor", "mobile:control"],
        )
        claim = self.state.claim_mobile_pairing(
            pairing["id"], pairing["code"], "Pixel", "android"
        )

        self.assertNotIn(MobileScope.TRADE_EXECUTE, claim["scopes"])
        self.assertNotIn(MobileScope.TREASURY_REQUEST, claim["scopes"])

    def test_new_scopes_are_granted_only_when_explicitly_requested(self) -> None:
        pairing = self.state.create_mobile_pairing(
            api_base_url="https://node.tailnet.ts.net",
            scopes=[MobileScope.WALLET_READ, MobileScope.TRADE_EXECUTE],
        )
        claim = self.state.claim_mobile_pairing(
            pairing["id"], pairing["code"], "Pixel", "android"
        )

        self.assertIn(MobileScope.WALLET_READ, claim["scopes"])
        self.assertIn(MobileScope.TRADE_EXECUTE, claim["scopes"])
        self.assertNotIn(MobileScope.TREASURY_REQUEST, claim["scopes"])

    def test_realtime_envelope_requires_monotonic_sequence(self) -> None:
        first = MobileRealtimeEnvelope(
            event_type="cockpit",
            server_time=datetime.now(timezone.utc),
            sequence=41,
            payload={"ok": True},
        )
        second = MobileRealtimeEnvelope(
            event_type="cockpit",
            server_time=datetime.now(timezone.utc),
            sequence=42,
            payload={"ok": True},
        )

        self.assertEqual(first.sequence + 1, second.sequence)
        self.assertEqual(second.schema_version, 1)
        with self.assertRaises(ValidationError):
            MobileRealtimeEnvelope(
                event_type="cockpit",
                server_time=datetime.now(timezone.utc),
                sequence=0,
                payload={},
            )

    def test_action_status_contract_is_stable(self) -> None:
        self.assertEqual(
            [status.value for status in MobileActionStatus],
            [
                "pending",
                "verifying",
                "confirmed",
                "failed",
                "cancelled",
                "expired",
                "review_required",
            ],
        )

    def test_mobile_command_center_migration_contract_is_exact_and_idempotent(self) -> None:
        expected_columns = {
            "mobile_action_receipts": [
                ("id", "TEXT", 0, 1),
                ("idempotency_key_hash", "TEXT", 1, 0),
                ("device_id", "TEXT", 1, 0),
                ("action_type", "TEXT", 1, 0),
                ("entity_id", "TEXT", 1, 0),
                ("payload", "TEXT", 1, 0),
                ("status", "TEXT", 1, 0),
                ("created_at", "TEXT", 1, 0),
                ("updated_at", "TEXT", 1, 0),
            ],
            "mobile_destination_authorizations": [
                ("id", "TEXT", 0, 1),
                ("payload", "TEXT", 1, 0),
                ("created_at", "TEXT", 1, 0),
                ("expires_at", "TEXT", 1, 0),
                ("used_at", "TEXT", 0, 0),
            ],
            "mobile_push_registrations": [
                ("id", "TEXT", 0, 1),
                ("device_id", "TEXT", 1, 0),
                ("token_ciphertext", "TEXT", 1, 0),
                ("token_fingerprint", "TEXT", 1, 0),
                ("platform", "TEXT", 1, 0),
                ("created_at", "TEXT", 1, 0),
                ("updated_at", "TEXT", 1, 0),
                ("revoked_at", "TEXT", 0, 0),
            ],
            "mobile_alert_acknowledgements": [
                ("id", "TEXT", 0, 1),
                ("device_id", "TEXT", 1, 0),
                ("event_id", "TEXT", 1, 0),
                ("acknowledged_at", "TEXT", 1, 0),
            ],
        }
        expected_unique_columns = {
            "mobile_action_receipts": {("idempotency_key_hash",)},
            "mobile_destination_authorizations": set(),
            "mobile_push_registrations": {("token_fingerprint",)},
            "mobile_alert_acknowledgements": {("device_id", "event_id")},
        }
        with closing(sqlite3.connect(self.state.storage.path)) as connection:
            actual_columns = {}
            actual_unique_columns = {}
            for table in expected_columns:
                actual_columns[table] = [
                    (str(row[1]), str(row[2]), int(row[3]), int(row[5]))
                    for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                ]
                unique_columns = set()
                for index in connection.execute(f"PRAGMA index_list({table})").fetchall():
                    if not int(index[2]) or str(index[3]) != "u":
                        continue
                    unique_columns.add(
                        tuple(
                            str(row[2])
                            for row in connection.execute(
                                f"PRAGMA index_info({index[1]})"
                            ).fetchall()
                        )
                    )
                actual_unique_columns[table] = unique_columns
            migration = connection.execute(
                "SELECT version FROM schema_migrations WHERE migration_id = ?",
                ("010_mobile_command_center",),
            ).fetchone()

        self.assertEqual(actual_columns, expected_columns)
        self.assertEqual(actual_unique_columns, expected_unique_columns)
        self.assertEqual(migration, (10,))

        Storage(str(self.state.storage.path))
        with closing(sqlite3.connect(self.state.storage.path)) as connection:
            migration_count = connection.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE migration_id = ?",
                ("010_mobile_command_center",),
            ).fetchone()
        self.assertEqual(migration_count, (1,))

    def test_restore_migrates_version_nine_artifact_forward(self) -> None:
        root = Path(self.directory.name)
        source = Storage(str(root / "version-nine.db"))
        task_tables = {
            "mobile_action_receipts",
            "mobile_destination_authorizations",
            "mobile_push_registrations",
            "mobile_alert_acknowledgements",
        }
        with closing(sqlite3.connect(source.path)) as connection:
            for table in task_tables:
                connection.execute(f"DROP TABLE {table}")
            connection.execute(
                "DELETE FROM schema_migrations WHERE migration_id = ?",
                ("010_mobile_command_center",),
            )
            connection.commit()
        artifact = source.create_backup_artifact()
        target = Storage(str(root / "restore-target.db"))

        preview = target.preview_restore_artifact(artifact)
        result = target.restore_backup_artifact(artifact)

        self.assertEqual(preview["schema_version"], 9)
        self.assertIn("Artifact will be migrated forward after restore.", preview["warnings"])
        self.assertEqual(result["status"], "restored")
        self.assertEqual(target.schema_status()["current_version"], 10)
        with closing(sqlite3.connect(target.path)) as connection:
            restored_tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        self.assertTrue(task_tables.issubset(restored_tables))

    def test_monitor_only_token_cannot_read_wallet_or_approve_trade(self) -> None:
        from app import main as main_app

        previous_state = main_app.state
        previous_auth = main_app.auth
        main_app.state = self.state
        main_app.auth = AuthManager(password="desktop-pass")
        desktop_token = main_app.auth.login("desktop-pass")
        try:
            client = TestClient(main_app.app)
            pairing = client.post(
                "/api/mobile/pairing/start",
                json={
                    "api_base_url": "https://node.tailnet.ts.net",
                    "scopes": [MobileScope.MONITOR],
                },
                headers={"Authorization": f"Bearer {desktop_token}"},
            ).json()
            claim = client.post(
                "/api/mobile/pairing/claim",
                json={
                    "pairing_id": pairing["id"],
                    "code": pairing["code"],
                    "device_name": "Pixel",
                    "platform": "android",
                },
            ).json()
            headers = {"Authorization": f"Bearer {claim['token']}"}

            self.assertEqual(client.get("/api/mobile/wallet", headers=headers).status_code, 403)
            self.assertEqual(
                client.post(
                    "/api/mobile/trades/intent-1/approve",
                    headers=headers,
                ).status_code,
                403,
            )
        finally:
            main_app.state = previous_state
            main_app.auth = previous_auth

    def test_scoped_wallet_stub_and_incomplete_guarded_trade_request_are_inert(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Scoped Pixel",
                scopes=[MobileScope.WALLET_READ, MobileScope.TRADE_EXECUTE],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}
            financial_counts_before = (
                self.state.storage.count_trades(),
                self.state.storage.count_live_execution_requests(),
                self.state.storage.count_live_sessions(),
                self.state.storage.count_live_execution_audits(),
                self.state.storage.count_live_intents(),
                self.state.storage.count_live_ledger_positions(),
                self.state.storage.count_events(),
            )

            wallet_response = client.get("/api/mobile/wallet", headers=headers)
            trade_response = client.post(
                "/api/mobile/trades/intent-1/approve",
                headers=headers,
            )

            self.assertEqual(wallet_response.status_code, 501)
            self.assertEqual(trade_response.status_code, 422)
            self.assertEqual(
                (
                    self.state.storage.count_trades(),
                    self.state.storage.count_live_execution_requests(),
                    self.state.storage.count_live_sessions(),
                    self.state.storage.count_live_execution_audits(),
                    self.state.storage.count_live_intents(),
                    self.state.storage.count_live_ledger_positions(),
                    self.state.storage.count_events(),
                ),
                financial_counts_before,
            )

    def test_invalid_push_registration_requests_never_echo_the_token(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Push Pixel",
                scopes=[MobileScope.ALERTS],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}
            cases = {
                "malformed": {
                    "token": {"secret": "malformed-push-token-secret"},
                    "platform": "android",
                },
                "empty": {"token": "", "platform": "android"},
                "overlong": {
                    "token": "overlong-push-token-secret-" + ("x" * 4096),
                    "platform": "android",
                },
            }

            for name, request_body in cases.items():
                with self.subTest(name=name):
                    response = client.post(
                        "/api/mobile/notifications/register",
                        json=request_body,
                        headers=headers,
                    )
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(
                        response.json(),
                        {"detail": "Invalid mobile push registration request"},
                    )
                    self.assertNotIn("malformed-push-token-secret", response.text)
                    self.assertNotIn("overlong-push-token-secret", response.text)

            self.assertEqual(self.state.storage.count_mobile_push_registrations(), 0)

    def test_device_revocation_revokes_every_linked_push_registration(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Revoked Pixel",
                scopes=[MobileScope.ALERTS],
            )
            mobile_headers = {"Authorization": f"Bearer {claim['token']}"}
            for token in (
                "ExponentPushToken[first-secret-token]",
                "ExponentPushToken[second-secret-token]",
            ):
                response = client.post(
                    "/api/mobile/notifications/register",
                    json={"token": token, "platform": "android"},
                    headers=mobile_headers,
                )
                self.assertEqual(response.status_code, 200)

            revoke_response = client.post(
                f"/api/mobile/devices/{claim['device']['id']}/revoke",
                headers=desktop_headers,
            )

            self.assertEqual(revoke_response.status_code, 200)
            self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])
            registrations = self.state.storage.load_mobile_push_registrations(
                include_revoked=True
            )
            self.assertEqual(len(registrations), 2)
            self.assertTrue(all(str(item["revoked_at"] or "") for item in registrations))

    def test_same_device_duplicate_returns_canonical_persisted_metadata(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            claim = self.claim_device(
                client,
                desktop_headers,
                name="Duplicate Pixel",
                scopes=[MobileScope.ALERTS],
            )
            headers = {"Authorization": f"Bearer {claim['token']}"}
            token = "ExponentPushToken[canonical-same-device-secret]"
            with patch(
                "app.mobile.service.utc_now",
                return_value=datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc),
            ):
                first = client.post(
                    "/api/mobile/notifications/register",
                    json={"token": token, "platform": "android"},
                    headers=headers,
                )
            with patch(
                "app.mobile.service.utc_now",
                return_value=datetime(2026, 7, 26, 12, 5, tzinfo=timezone.utc),
            ):
                second = client.post(
                    "/api/mobile/notifications/register",
                    json={"token": token, "platform": "android"},
                    headers=headers,
                )
            persisted = self.state.storage.load_mobile_push_registrations(
                include_revoked=True
            )

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(len(persisted), 1)
            self.assertEqual(
                second.json()["registration"]["id"],
                first.json()["registration"]["id"],
            )
            self.assertEqual(
                second.json()["registration"]["created_at"],
                first.json()["registration"]["created_at"],
            )
            self.assertEqual(second.json()["registration"]["id"], persisted[0]["id"])
            self.assertEqual(
                second.json()["registration"]["created_at"],
                persisted[0]["created_at"],
            )
            self.assertEqual(
                second.json()["registration"]["updated_at"],
                persisted[0]["updated_at"],
            )

    def test_cross_device_duplicate_reassigns_canonical_registration(self) -> None:
        with self.mobile_client() as (client, desktop_headers):
            first_claim = self.claim_device(
                client,
                desktop_headers,
                name="First Pixel",
                scopes=[MobileScope.ALERTS],
            )
            second_claim = self.claim_device(
                client,
                desktop_headers,
                name="Second Pixel",
                scopes=[MobileScope.ALERTS],
            )
            token = "ExponentPushToken[canonical-cross-device-secret]"
            first = client.post(
                "/api/mobile/notifications/register",
                json={"token": token, "platform": "android"},
                headers={"Authorization": f"Bearer {first_claim['token']}"},
            )
            second = client.post(
                "/api/mobile/notifications/register",
                json={"token": token, "platform": "android"},
                headers={"Authorization": f"Bearer {second_claim['token']}"},
            )
            persisted = self.state.storage.load_mobile_push_registrations()

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(len(persisted), 1)
            self.assertEqual(
                second.json()["registration"]["id"],
                first.json()["registration"]["id"],
            )
            self.assertEqual(
                second.json()["registration"]["created_at"],
                first.json()["registration"]["created_at"],
            )
            self.assertEqual(
                second.json()["registration"]["device_id"],
                second_claim["device"]["id"],
            )
            self.assertEqual(persisted[0]["device_id"], second_claim["device"]["id"])

            first_revoke = client.post(
                f"/api/mobile/devices/{first_claim['device']['id']}/revoke",
                headers=desktop_headers,
            )
            self.assertEqual(first_revoke.status_code, 200)
            self.assertEqual(len(self.state.storage.load_mobile_push_registrations()), 1)

            second_revoke = client.post(
                f"/api/mobile/devices/{second_claim['device']['id']}/revoke",
                headers=desktop_headers,
            )
            self.assertEqual(second_revoke.status_code, 200)
            self.assertEqual(self.state.storage.load_mobile_push_registrations(), [])

    def test_push_registration_fails_closed_without_valid_encryption_key(self) -> None:
        from app import main as main_app

        previous_state = main_app.state
        previous_auth = main_app.auth
        previous_key = main_app.config.mobile_push_token_encryption_key
        main_app.state = self.state
        main_app.auth = AuthManager(password="desktop-pass")
        desktop_token = main_app.auth.login("desktop-pass")
        try:
            client = TestClient(main_app.app)
            pairing = client.post(
                "/api/mobile/pairing/start",
                json={
                    "api_base_url": "https://node.tailnet.ts.net",
                    "scopes": [MobileScope.ALERTS],
                },
                headers={"Authorization": f"Bearer {desktop_token}"},
            ).json()
            claim = client.post(
                "/api/mobile/pairing/claim",
                json={
                    "pairing_id": pairing["id"],
                    "code": pairing["code"],
                    "device_name": "Pixel",
                    "platform": "android",
                },
            ).json()
            headers = {"Authorization": f"Bearer {claim['token']}"}

            for key in ("", "not-a-valid-fernet-key"):
                with self.subTest(key=key):
                    main_app.config.mobile_push_token_encryption_key = key
                    response = client.post(
                        "/api/mobile/notifications/register",
                        json={
                            "token": "ExponentPushToken[raw-secret-token]",
                            "platform": "android",
                        },
                        headers=headers,
                    )
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(self.state.storage.count_mobile_push_registrations(), 0)
        finally:
            main_app.state = previous_state
            main_app.auth = previous_auth
            main_app.config.mobile_push_token_encryption_key = previous_key

    def test_push_registration_persists_only_ciphertext(self) -> None:
        from app import main as main_app

        previous_state = main_app.state
        previous_auth = main_app.auth
        previous_key = main_app.config.mobile_push_token_encryption_key
        main_app.state = self.state
        main_app.auth = AuthManager(password="desktop-pass")
        main_app.config.mobile_push_token_encryption_key = base64.urlsafe_b64encode(
            b"cryptoarc-mobile-push-test-key!!"
        ).decode("ascii")
        raw_token = "ExponentPushToken[raw-secret-token]"
        desktop_token = main_app.auth.login("desktop-pass")
        try:
            client = TestClient(main_app.app)
            pairing = client.post(
                "/api/mobile/pairing/start",
                json={
                    "api_base_url": "https://node.tailnet.ts.net",
                    "scopes": [MobileScope.ALERTS],
                },
                headers={"Authorization": f"Bearer {desktop_token}"},
            ).json()
            claim = client.post(
                "/api/mobile/pairing/claim",
                json={
                    "pairing_id": pairing["id"],
                    "code": pairing["code"],
                    "device_name": "Pixel",
                    "platform": "android",
                },
            ).json()

            response = client.post(
                "/api/mobile/notifications/register",
                json={"token": raw_token, "platform": "android"},
                headers={"Authorization": f"Bearer {claim['token']}"},
            )
            registrations = self.state.storage.load_mobile_push_registrations()
            encoded_response = json.dumps(response.json())
            encoded_export = json.dumps(self.state.export_data("all"))
            encoded_backup = json.dumps(self.state.storage.create_backup_artifact())
            encoded_events = json.dumps(
                [event.to_dict() for event in self.state.storage.load_all_events(100)]
            )
            database_bytes = Path(self.state.storage.path).read_bytes()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(registrations), 1)
            self.assertNotEqual(registrations[0]["token_ciphertext"], raw_token)
            self.assertNotIn(raw_token, encoded_response)
            self.assertNotIn(raw_token, encoded_export)
            self.assertNotIn(raw_token, encoded_backup)
            self.assertNotIn(raw_token, encoded_events)
            self.assertNotIn(raw_token.encode("utf-8"), database_bytes)
            self.assertNotIn("token_ciphertext", encoded_response)
            self.assertNotIn("token_fingerprint", encoded_response)
        finally:
            main_app.state = previous_state
            main_app.auth = previous_auth
            main_app.config.mobile_push_token_encryption_key = previous_key


if __name__ == "__main__":
    unittest.main()
