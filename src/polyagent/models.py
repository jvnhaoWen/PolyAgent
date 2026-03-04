from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass(slots=True)
class Message:
    """Generic inter-agent message."""

    topic: str
    payload: Dict[str, Any]
    source: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class TradeRequest:
    action: str
    token_id: str
    price: float
    size: float
    strategy: str = "manual"


@dataclass(slots=True)
class HealthStatus:
    agent: str
    ok: bool
    detail: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
