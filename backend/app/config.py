from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    pumpfun_source: Literal["mock", "pumpportal"] = Field(default="pumpportal", alias="PUMPFUN_SOURCE")
    pumpportal_ws_url: str = Field(default="wss://pumpportal.fun/api/data", alias="PUMPPORTAL_WS_URL")
    solana_wss_endpoint: str = Field(default="", alias="SOLANA_WSS_ENDPOINT")
    solana_logs_mentions_address: str = Field(default="", alias="SOLANA_LOGS_MENTIONS_ADDRESS")
    solana_rpc_url: str = Field(default="https://api.mainnet-beta.solana.com", alias="SOLANA_RPC_URL")
    watch_wallet_address: str = Field(default="", alias="WATCH_WALLET_ADDRESS")
    database_path: str = Field(default="data/cryptoarc.db", alias="DATABASE_PATH")
    live_trading_enabled: bool = Field(default=False, alias="LIVE_TRADING_ENABLED")
    live_signer_daemon_url: str = Field(default="http://127.0.0.1:8799", alias="LIVE_SIGNER_DAEMON_URL")
    live_signer_daemon_auth_token: str = Field(default="", alias="LIVE_SIGNER_DAEMON_AUTH_TOKEN")
    telegram_alerts_enabled: bool = Field(default=False, alias="TELEGRAM_ALERTS_ENABLED")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    telegram_alert_min_interval_seconds: int = Field(default=60, alias="TELEGRAM_ALERT_MIN_INTERVAL_SECONDS")
    allowed_origins: str = Field(default="http://127.0.0.1:5173,http://localhost:5173", alias="ALLOWED_ORIGINS")
    dashboard_password: str = Field(default="", alias="DASHBOARD_PASSWORD")
    dashboard_totp_secret: str = Field(default="", alias="DASHBOARD_TOTP_SECRET")
    mobile_public_api_base_url: str = Field(default="", alias="MOBILE_PUBLIC_API_BASE_URL")
    mobile_pairing_ttl_seconds: int = Field(default=300, alias="MOBILE_PAIRING_TTL_SECONDS")
    mobile_token_ttl_days: int = Field(default=30, alias="MOBILE_TOKEN_TTL_DAYS")
    mobile_push_token_encryption_key: str = Field(default="", alias="MOBILE_PUSH_TOKEN_ENCRYPTION_KEY")
    mobile_expo_push_enabled: bool = Field(default=False, alias="MOBILE_EXPO_PUSH_ENABLED")
    mobile_expo_push_timeout_seconds: float = Field(default=10.0, alias="MOBILE_EXPO_PUSH_TIMEOUT_SECONDS")
    grading_model_enabled: bool = Field(default=False, alias="GRADING_MODEL_ENABLED")
    grading_model_daily_token_budget: int = Field(default=100_000, alias="GRADING_MODEL_DAILY_TOKEN_BUDGET")
    grading_model_daily_cost_budget: float = Field(default=10.0, alias="GRADING_MODEL_DAILY_COST_BUDGET")
    grading_model_max_items: int = Field(default=8, alias="GRADING_MODEL_MAX_ITEMS")
    grading_model_timeout_seconds: float = Field(default=10.0, alias="GRADING_MODEL_TIMEOUT_SECONDS")
    grading_model_retry_limit: int = Field(default=1, alias="GRADING_MODEL_RETRY_LIMIT")


@lru_cache
def get_config() -> AppConfig:
    return AppConfig()
