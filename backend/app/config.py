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
    solana_rpc_url: str = Field(default="https://api.mainnet-beta.solana.com", alias="SOLANA_RPC_URL")
    watch_wallet_address: str = Field(default="", alias="WATCH_WALLET_ADDRESS")
    database_path: str = Field(default="data/cryptoarc.db", alias="DATABASE_PATH")
    live_trading_enabled: bool = Field(default=False, alias="LIVE_TRADING_ENABLED")
    live_signer_daemon_url: str = Field(default="http://127.0.0.1:8799", alias="LIVE_SIGNER_DAEMON_URL")
    live_signer_daemon_auth_token: str = Field(default="", alias="LIVE_SIGNER_DAEMON_AUTH_TOKEN")
    allowed_origins: str = Field(default="http://127.0.0.1:5173,http://localhost:5173", alias="ALLOWED_ORIGINS")
    dashboard_password: str = Field(default="", alias="DASHBOARD_PASSWORD")
    dashboard_totp_secret: str = Field(default="", alias="DASHBOARD_TOTP_SECRET")


@lru_cache
def get_config() -> AppConfig:
    return AppConfig()
