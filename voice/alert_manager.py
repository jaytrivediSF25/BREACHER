"""4-tier alert escalation priority queue.

Sits between the scene model and TTS engine, ensuring the most critical
intelligence is always delivered first. Higher-priority alerts interrupt
lower-priority speech.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from config import AlertTier

logger = logging.getLogger("breacher.alerts")


@dataclass(order=True)
class AlertMessage:
    priority: int
    timestamp: float = field(compare=False, default_factory=time.time)
    text: str = field(compare=False, default="")
    tier: AlertTier = field(compare=False, default=AlertTier.P4_STATUS)
    metadata: dict = field(compare=False, default_factory=dict)


class AlertManager:
    """Priority queue that feeds the TTS engine with escalation logic."""

    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[AlertMessage] = asyncio.PriorityQueue()
        self._current_priority: Optional[int] = None
        self._tts = None
        self._running = False
        self._last_spoken: str = ""

    def set_tts(self, tts) -> None:
        self._tts = tts

    async def enqueue(
        self,
        text: str,
        priority: AlertTier = AlertTier.P4_STATUS,
        metadata: Optional[dict] = None,
    ) -> None:
        """Add a message to the priority queue."""
        msg = AlertMessage(
            priority=int(priority),
            text=text,
            tier=priority,
            metadata=metadata or {},
        )
        await self._queue.put(msg)
        logger.debug("Enqueued [P%d]: %s", priority, text[:60])

        if (
            self._tts
            and self._tts.is_speaking
            and self._current_priority is not None
            and int(priority) < self._current_priority
        ):
            logger.info("Higher priority alert — interrupting current speech")
            await self._tts.cancel()

    async def consume_loop(self) -> None:
        """Run forever, pulling from the queue and feeding the TTS engine."""
        self._running = True
        logger.info("Alert manager consume loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if not self._running:
                break

            self._current_priority = msg.priority
            self._last_spoken = msg.text

            if self._tts:
                logger.info("[P%d] Speaking: %s", msg.priority, msg.text[:80])
                await self._tts.speak(msg.text, priority=msg.tier)
            else:
                logger.warning("No TTS engine — would say: %s", msg.text)

            self._current_priority = None

    def flush(self) -> None:
        """Clear all pending messages (used on abort)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.info("Alert queue flushed")

    def stop(self) -> None:
        self._running = False

    @property
    def last_spoken(self) -> str:
        return self._last_spoken

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()
