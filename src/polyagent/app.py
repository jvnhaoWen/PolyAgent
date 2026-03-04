from __future__ import annotations

import asyncio
import logging

from .agents import ExecutionAgent, MarketAgent, NewsAgent, RiskAgent, SchedulerAgent, StrategyAgent
from .config import settings
from .models import Message
from .polymarket_client import PolymarketClient
from .queue_bus import AbstractMessageBus, build_message_bus


class TradingInterface:
    def __init__(self, bus: AbstractMessageBus) -> None:
        self.bus = bus

    async def buy(self, token_id: str, price: float, size: float, strategy: str = "manual") -> None:
        await self._send("buy", token_id, price, size, strategy)

    async def sell(self, token_id: str, price: float, size: float, strategy: str = "manual") -> None:
        await self._send("sell", token_id, price, size, strategy)

    async def split(self, token_id: str, size: float, strategy: str = "manual") -> None:
        await self._send("split", token_id, 0.0, size, strategy)

    async def merge(self, token_id: str, size: float, strategy: str = "manual") -> None:
        await self._send("merge", token_id, 0.0, size, strategy)

    async def _send(self, action: str, token_id: str, price: float, size: float, strategy: str) -> None:
        payload = {"action": action, "token_id": token_id, "price": price, "size": size, "strategy": strategy}
        await self.bus.publish("execution_requests", Message(topic="execution_requests", payload=payload, source="manual-interface"))


async def run_runtime() -> None:
    bus = build_message_bus(settings)
    client = PolymarketClient(
        settings.gamma_base_url,
        settings.clob_base_url,
        private_key=settings.private_key,
        chain_id=settings.chain_id,
        funder=settings.funder,
        signature_type=settings.signature_type,
    )

    market = MarketAgent(bus, settings, client)
    news = NewsAgent(bus, settings)
    strategy = StrategyAgent(bus, settings)
    execution = ExecutionAgent(bus, settings, client)
    risk = RiskAgent(bus, settings)
    managed = {
        market.name: market,
        news.name: news,
        strategy.name: strategy,
        execution.name: execution,
        risk.name: risk,
    }
    scheduler = SchedulerAgent(bus, settings, managed)

    tasks = [asyncio.create_task(agent.run_forever(), name=agent.name) for agent in [*managed.values(), scheduler]]
    await asyncio.gather(*tasks)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run_runtime())


if __name__ == "__main__":
    main()
