from __future__ import annotations

from datetime import timedelta
import hashlib

from app.core.models import BotSettings, BotStats, TokenSignal, TokenStatus, utc_now


class PaperTrader:
    """Simple deterministic paper trade lifecycle."""

    def buy(self, token: TokenSignal, settings: BotSettings) -> TokenSignal:
        token.status = TokenStatus.BUYING
        if self._fill_failed(token, settings):
            token.fill_failed = True
            token.reason = "paper fill failed"
            token.decision_log.append("Paper buy failed: simulated fill miss")
            token.status = TokenStatus.SKIPPED
            return token

        if settings.paper_fill_delay_ticks > 0:
            token.fill_delay_ticks_remaining = settings.paper_fill_delay_ticks
            token.decision_log.append(f"Paper buy queued with {settings.paper_fill_delay_ticks} tick fill delay")

        token.amount_sol = settings.trade_size_sol
        speed_impact = {"slow": 0.0, "normal": 0.05, "fast": 0.12, "turbo": 0.25}.get(settings.trading_speed, 0.05)
        token.price_impact_pct = round(settings.paper_price_impact_pct + speed_impact + (token.buy_velocity * 0.08), 4)
        slippage_multiplier = 1 + ((settings.slippage_tolerance_pct + token.price_impact_pct) / 100)
        token.entry_price = max(0.000001, (token.current_price or 0.00001) * slippage_multiplier)
        token.slippage_paid_pct = settings.slippage_tolerance_pct
        token.fee_paid_sol = round(settings.trade_size_sol * (settings.paper_fee_bps / 10000), 6)
        token.current_price = token.entry_price
        token.peak_price = token.entry_price
        token.trough_price = token.entry_price
        token.opened_at = utc_now()
        token.pnl_sol = 0.0
        token.entry_strategy_profile = settings.strategy_profile
        token.entry_risk_filters = [
            f"max creator hold {settings.max_creator_hold_pct:.1f}%",
            "honeypot filter on" if settings.filter_honeypots else "honeypot filter off",
            "rug filter on" if settings.filter_rug_risk else "rug filter off",
        ]
        token.decision_log.append(
            f"Paper buy filled at {token.entry_price:.8f}; impact {token.price_impact_pct:.2f}%; fee {token.fee_paid_sol:.6f} SOL"
        )
        token.status = TokenStatus.BUYING if token.fill_delay_ticks_remaining > 0 else TokenStatus.PAPER_BOUGHT
        return token

    def tick(self, token: TokenSignal, settings: BotSettings, price_delta_pct: float) -> bool:
        if token.status == TokenStatus.BUYING and token.fill_delay_ticks_remaining > 0:
            token.fill_delay_ticks_remaining -= 1
            token.decision_log.append(f"Paper fill pending; {token.fill_delay_ticks_remaining} ticks remaining")
            if token.fill_delay_ticks_remaining == 0:
                token.status = TokenStatus.PAPER_BOUGHT
                token.decision_log.append("Paper delayed buy filled")
            return False

        if token.status not in {TokenStatus.PAPER_BOUGHT, TokenStatus.MONITORING} or token.entry_price is None:
            return False

        token.status = TokenStatus.MONITORING
        token.ticks_held += 1
        token.current_price = max(0.0000001, (token.current_price or token.entry_price) * (1 + price_delta_pct / 100))
        token.peak_price = max(token.peak_price or token.current_price, token.current_price)
        token.trough_price = min(token.trough_price or token.current_price, token.current_price)

        move_pct = ((token.current_price - token.entry_price) / token.entry_price) * 100
        token.unrealized_pct = round(move_pct, 2)
        token.highest_unrealized_pct = max(token.highest_unrealized_pct, token.unrealized_pct)
        token.lowest_unrealized_pct = min(token.lowest_unrealized_pct, token.unrealized_pct)
        if token.opened_at:
            token.hold_duration_seconds = max(0, int((utc_now() - token.opened_at).total_seconds()))
        gross_pnl = settings.trade_size_sol * (move_pct / 100)
        exit_fee = settings.trade_size_sol * (settings.paper_fee_bps / 10000)
        token.pnl_sol = round(gross_pnl - token.fee_paid_sol - exit_fee, 6)

        if move_pct >= settings.take_profit_pct:
            self.close(token, "take profit")
            return True

        if move_pct <= -settings.stop_loss_pct:
            self.close(token, "stop loss")
            return True

        if token.opened_at and utc_now() - token.opened_at >= timedelta(seconds=settings.max_hold_time_seconds):
            self.close(token, "max hold time")
            return True

        if token.ticks_held >= settings.max_position_ticks:
            self.close(token, "max position ticks")
            return True

        return False

    def close(self, token: TokenSignal, reason: str = "manual") -> None:
        token.status = TokenStatus.SELLING
        token.status = TokenStatus.PAPER_SOLD
        token.exit_price = token.current_price
        token.closed_at = utc_now()
        token.exit_reason = reason
        if token.opened_at:
            token.hold_duration_seconds = max(0, int((token.closed_at - token.opened_at).total_seconds()))
        token.decision_log.append(f"Paper sell filled: {reason}")

    def _fill_failed(self, token: TokenSignal, settings: BotSettings) -> bool:
        if settings.paper_failed_fill_pct <= 0:
            return False
        digest = hashlib.sha256(f"{token.id}:{token.mint}".encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 10000
        return bucket < int(settings.paper_failed_fill_pct * 100)

    def apply_closed_trade(self, token: TokenSignal, stats: BotStats) -> BotStats:
        pnl = token.pnl_sol or 0.0
        stats.total_trades += 1
        stats.total_pnl_sol = round(stats.total_pnl_sol + pnl, 6)

        if pnl > stats.scratch_threshold_sol:
            stats.successful_trades += 1
        elif pnl < -stats.scratch_threshold_sol:
            stats.losing_trades += 1
        else:
            stats.scratch_trades += 1

        stats.best_trade_sol = max(stats.best_trade_sol, pnl)
        stats.worst_trade_sol = min(stats.worst_trade_sol, pnl)
        decisive = stats.successful_trades + stats.losing_trades
        stats.win_rate_pct = int((stats.successful_trades / decisive) * 100) if decisive else 0
        stats.gross_win_rate_pct = int((stats.successful_trades / stats.total_trades) * 100) if stats.total_trades else 0
        stats.scratch_rate_pct = int((stats.scratch_trades / stats.total_trades) * 100) if stats.total_trades else 0
        return stats
