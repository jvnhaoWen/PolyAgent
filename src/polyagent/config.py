from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Settings:
    gamma_base_url: str = os.getenv("POLY_GAMMA_BASE_URL", "https://gamma-api.polymarket.com")
    clob_base_url: str = os.getenv("POLY_CLOB_BASE_URL", "https://clob.polymarket.com")

    # Redis transport is default; set MESSAGE_BUS_BACKEND=memory for local fallback.
    message_bus_backend: str = os.getenv("MESSAGE_BUS_BACKEND", "redis").lower()
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_stream_prefix: str = os.getenv("REDIS_STREAM_PREFIX", "polyagent")

    market_poll_seconds: float = float(os.getenv("MARKET_POLL_SECONDS", "20"))
    news_poll_seconds: float = float(os.getenv("NEWS_POLL_SECONDS", "45"))
    strategy_poll_seconds: float = float(os.getenv("STRATEGY_POLL_SECONDS", "10"))
    execution_poll_seconds: float = float(os.getenv("EXECUTION_POLL_SECONDS", "2"))
    scheduler_poll_seconds: float = float(os.getenv("SCHEDULER_POLL_SECONDS", "5"))
    risk_poll_seconds: float = float(os.getenv("RISK_POLL_SECONDS", "15"))

    liquidity_min_default: int = int(os.getenv("LIQUIDITY_MIN_DEFAULT", "100000"))
    volume_min_default: int = int(os.getenv("VOLUME_MIN_DEFAULT", "1000000"))

    news_feeds: list[str] = field(
        default_factory=lambda: [
            item.strip()
            for item in os.getenv(
                "NEWS_FEEDS",
                "https://feeds.bbci.co.uk/news/world/rss.xml,https://www.reutersagency.com/feed/?best-topics=politics",
            ).split(",")
            if item.strip()
        ]
    )
    log_path: Path = Path(os.getenv("TRADE_LOG_PATH", "logs/trades.log"))

    # Real trading credentials. These must be provided via environment variables only.
    private_key: str | None = os.getenv("POLYMARKET_PRIVATE_KEY")
    chain_id: int = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
    funder: str | None = os.getenv("POLYMARKET_FUNDER")
    signature_type: int = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "1"))


settings = Settings()
