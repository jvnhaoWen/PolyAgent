from __future__ import annotations

import asyncio
import json
import logging
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .config import Settings
from .models import HealthStatus, Message, TradeRequest
from .nl_parser import parse_natural_language_to_market_query
from .polymarket_client import PolymarketClient
from .queue_bus import AbstractMessageBus


class BaseAgent:
    def __init__(self, name: str, bus: AbstractMessageBus, settings: Settings) -> None:
        self.name = name
        self.bus = bus
        self.settings = settings
        self._running = True
        self.health = HealthStatus(agent=name, ok=True, detail="booted")

    def stop(self) -> None:
        self._running = False

    async def run_forever(self) -> None:
        while self._running:
            try:
                await self.step()
                self.health = HealthStatus(agent=self.name, ok=True, detail="ok")
            except Exception as exc:
                self.health = HealthStatus(agent=self.name, ok=False, detail=str(exc))
                logging.exception("Agent %s loop error", self.name)
                await asyncio.sleep(2)

    async def step(self) -> None:
        raise NotImplementedError

    async def try_consume(self, topic: str, timeout_s: float) -> Message | None:
        try:
            return await asyncio.wait_for(self.bus.consume(topic), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None


class MarketAgent(BaseAgent):
    def __init__(self, bus: AbstractMessageBus, settings: Settings, client: PolymarketClient) -> None:
        super().__init__("market-agent", bus, settings)
        self.client = client

    def build_market_scan_queries(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        return [
            {
                "active": True,
                "closed": False,
                "liquidity_min": self.settings.liquidity_min_default,
                "order": "updatedAt",
                "ascending": False,
                "limit": 20,
            },
            {
                "active": True,
                "closed": False,
                "volume_min": self.settings.volume_min_default,
                "order": "volume",
                "ascending": False,
                "limit": 20,
            },
            {
                "active": True,
                "closed": False,
                "end_date_max": now.isoformat(),
                "order": "endDate",
                "ascending": True,
                "limit": 20,
            },
        ]

    async def step(self) -> None:
        for params in self.build_market_scan_queries():
            data = await self.client.fetch_gamma("/events", params)
            await self.bus.publish(
                "market_updates",
                Message(topic="market_updates", payload={"params": params, "data": data}, source=self.name),
            )
        await asyncio.sleep(self.settings.market_poll_seconds)


class NewsAgent(BaseAgent):
    def __init__(self, bus: AbstractMessageBus, settings: Settings) -> None:
        super().__init__("news-agent", bus, settings)

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        seeds = ["china", "election", "war", "bitcoin", "fed"]
        lower = text.lower()
        return [word for word in seeds if word in lower]

    async def _fetch_feed(self, url: str) -> list[str]:
        request = Request(url, headers={"User-Agent": "PolyAgent/1.0"})

        def _pull() -> list[str]:
            with urlopen(request, timeout=30) as response:
                xml_data = response.read().decode("utf-8", errors="ignore")
            root = ET.fromstring(xml_data)
            titles: list[str] = []
            for item in root.findall(".//item/title")[:10]:
                if item.text:
                    titles.append(item.text)
            return titles

        return await asyncio.to_thread(_pull)

    async def step(self) -> None:
        for feed in self.settings.news_feeds:
            try:
                titles = await self._fetch_feed(feed)
            except Exception:
                logging.warning("failed to fetch feed %s", feed)
                continue

            for title in titles:
                for tag in self._extract_keywords(title):
                    await self.bus.publish(
                        "news_signals",
                        Message(topic="news_signals", payload={"title": title, "tag_slug": tag}, source=self.name),
                    )
        await asyncio.sleep(self.settings.news_poll_seconds)


class StrategyAgent(BaseAgent):
    def __init__(self, bus: AbstractMessageBus, settings: Settings) -> None:
        super().__init__("strategy-agent", bus, settings)

    async def _handle_news(self) -> bool:
        news = await self.try_consume("news_signals", timeout_s=0.05)
        if news is None:
            return False

        query = parse_natural_language_to_market_query(f"{news.payload['tag_slug']} high liquidity and high volume")
        signal = {
            "strategy": "news_arbitrage",
            "tag_slug": news.payload["tag_slug"],
            "query": query,
            "confidence": round(random.uniform(0.55, 0.9), 3),
            "reason": news.payload.get("title", ""),
        }
        await self.bus.publish("trade_signals", Message(topic="trade_signals", payload=signal, source=self.name))
        return True

    async def _handle_market(self) -> bool:
        update = await self.try_consume("market_updates", timeout_s=0.05)
        if update is None:
            return False

        data = update.payload.get("data") or []
        if not isinstance(data, list):
            return True
        for item in data[:5]:
            vol = float(item.get("volume", 0) or 0)
            liq = float(item.get("liquidity", 0) or 0)
            if liq <= 0:
                continue
            kyle = vol / liq
            if kyle > 2:
                signal = {
                    "strategy": "liquidity_breakout",
                    "market": item,
                    "confidence": 0.6,
                    "kyle_lambda": kyle,
                }
                await self.bus.publish("trade_signals", Message(topic="trade_signals", payload=signal, source=self.name))
        return True

    async def step(self) -> None:
        handled_news = await self._handle_news()
        handled_market = await self._handle_market()
        if not handled_news and not handled_market:
            await asyncio.sleep(self.settings.strategy_poll_seconds)


class ExecutionAgent(BaseAgent):
    def __init__(self, bus: AbstractMessageBus, settings: Settings, client: PolymarketClient) -> None:
        super().__init__("execution-agent", bus, settings)
        self.client = client
        self.trade_logger = self._build_trade_logger(settings.log_path)

    @staticmethod
    def _build_trade_logger(path: Path) -> logging.Logger:
        path.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("trades")
        if not logger.handlers:
            handler = logging.FileHandler(path)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    async def _execute(self, request: TradeRequest) -> dict[str, Any]:
        payload = {
            "action": request.action,
            "token_id": request.token_id,
            "price": request.price,
            "size": request.size,
            "strategy": request.strategy,
        }
        result = await self.client.submit_order(payload)
        self.trade_logger.info(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), **payload, **result}))
        return result

    async def step(self) -> None:
        request_msg = await self.try_consume("execution_requests", timeout_s=0.1)
        signal_msg = await self.try_consume("trade_signals", timeout_s=0.1)
        if request_msg is None and signal_msg is None:
            await asyncio.sleep(self.settings.execution_poll_seconds)
            return

        if request_msg is not None:
            req = TradeRequest(**request_msg.payload)
            await self._execute(req)

        if signal_msg is not None:
            payload = signal_msg.payload
            market = payload.get("market", {})
            token_id = str(market.get("id", payload.get("tag_slug", "unknown")))
            simulated = TradeRequest(
                action="buy",
                token_id=token_id,
                price=float(payload.get("price", 0.5)),
                size=float(payload.get("size", 10)),
                strategy=payload.get("strategy", "auto"),
            )
            await self._execute(simulated)


class RiskAgent(BaseAgent):
    def __init__(self, bus: AbstractMessageBus, settings: Settings) -> None:
        super().__init__("risk-agent", bus, settings)

    async def step(self) -> None:
        await asyncio.sleep(self.settings.risk_poll_seconds)


class SchedulerAgent(BaseAgent):
    def __init__(self, bus: AbstractMessageBus, settings: Settings, managed: dict[str, BaseAgent]) -> None:
        super().__init__("scheduler-agent", bus, settings)
        self.managed = managed

    async def step(self) -> None:
        for name, agent in self.managed.items():
            status = {
                "agent": name,
                "ok": agent.health.ok,
                "detail": agent.health.detail,
                "updated_at": agent.health.updated_at.isoformat(),
            }
            await self.bus.publish("health", Message(topic="health", payload=status, source=self.name))
        await asyncio.sleep(self.settings.scheduler_poll_seconds)
