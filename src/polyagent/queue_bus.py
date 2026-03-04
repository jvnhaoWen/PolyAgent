from __future__ import annotations

import abc
import asyncio
import json
import uuid
from collections import defaultdict
from typing import DefaultDict

from .config import Settings
from .models import Message


class AbstractMessageBus(abc.ABC):
    @abc.abstractmethod
    async def publish(self, topic: str, message: Message) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def consume(self, topic: str) -> Message:
        raise NotImplementedError


class InMemoryMessageBus(AbstractMessageBus):
    """Simple in-process queue transport."""

    def __init__(self) -> None:
        self._queues: DefaultDict[str, asyncio.Queue[Message]] = defaultdict(asyncio.Queue)

    def queue(self, topic: str) -> asyncio.Queue[Message]:
        return self._queues[topic]

    async def publish(self, topic: str, message: Message) -> None:
        await self.queue(topic).put(message)

    async def consume(self, topic: str) -> Message:
        return await self.queue(topic).get()


class RedisMessageBus(AbstractMessageBus):
    """Redis Streams-backed queue transport for multi-process / distributed agents."""

    def __init__(self, redis_url: str, stream_prefix: str = "polyagent") -> None:
        try:
            import redis.asyncio as redis
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError("redis package is required for RedisMessageBus") from exc

        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._stream_prefix = stream_prefix
        self._consumer_id = f"consumer-{uuid.uuid4().hex[:8]}"

    def _stream(self, topic: str) -> str:
        return f"{self._stream_prefix}:{topic}"

    def _group(self, topic: str) -> str:
        return f"{self._stream_prefix}:{topic}:group"

    async def ensure_group(self, topic: str) -> None:
        stream = self._stream(topic)
        group = self._group(topic)
        try:
            await self._redis.xgroup_create(stream, group, id="$", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(self, topic: str, message: Message) -> None:
        payload = {
            "topic": message.topic,
            "source": message.source,
            "created_at": message.created_at.isoformat(),
            "payload": json.dumps(message.payload, ensure_ascii=False),
        }
        await self._redis.xadd(self._stream(topic), payload)

    async def consume(self, topic: str) -> Message:
        stream = self._stream(topic)
        group = self._group(topic)
        await self.ensure_group(topic)

        while True:
            response = await self._redis.xreadgroup(
                groupname=group,
                consumername=self._consumer_id,
                streams={stream: ">"},
                count=1,
                block=1000,
            )
            if not response:
                continue

            _, messages = response[0]
            msg_id, fields = messages[0]
            await self._redis.xack(stream, group, msg_id)
            return Message(
                topic=fields.get("topic", topic),
                source=fields.get("source", "unknown"),
                payload=json.loads(fields.get("payload", "{}")),
            )


def build_message_bus(settings: Settings) -> AbstractMessageBus:
    if settings.message_bus_backend == "redis":
        return RedisMessageBus(settings.redis_url, settings.redis_stream_prefix)
    return InMemoryMessageBus()
