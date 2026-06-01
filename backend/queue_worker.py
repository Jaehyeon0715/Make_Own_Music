# -*- coding: utf-8 -*-
"""Single-worker priority queue for GPU-heavy music generation tasks."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Awaitable, Callable, Optional


class Priority(IntEnum):
    HEAVY = 0  # Full multi-track generation.
    LIGHT = 1  # Track regeneration, repaint, provider switching.


class TaskType:
    GENERATE = "GENERATE"
    SEPARATE = "SEPARATE"
    REGENERATE = "REGENERATE"
    REPAINT = "REPAINT"
    SWITCH_PROVIDER = "SWITCH_PROVIDER"


@dataclass(order=True)
class QueueItem:
    priority: int
    seq: int = field(compare=True)  # FIFO within the same priority.
    task_type: str = field(compare=False)
    params: dict = field(compare=False)
    handler: Callable[..., Awaitable[None]] = field(compare=False)


class QueueWorker:
    """Singleton asyncio.PriorityQueue worker."""

    _instance: Optional["QueueWorker"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._seq = 0
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def enqueue(
        self,
        priority: Priority,
        task_type: str,
        params: dict,
        handler: Callable[..., Awaitable[None]],
    ) -> int:
        """Add a task and return current queue size."""
        self._seq += 1
        item = QueueItem(
            priority=priority,
            seq=self._seq,
            task_type=task_type,
            params=params,
            handler=handler,
        )
        await self._queue.put(item)
        return self._queue.qsize()

    def start(self):
        """Start the background worker loop once."""
        if self._task is None or self._task.done():
            self._queue = asyncio.PriorityQueue()  # rebind to current event loop
            self._seq = 0
            self._task = asyncio.create_task(self._worker_loop())

    def counts(self) -> dict:
        """Return queued HEAVY and LIGHT task counts."""
        heavy = light = 0
        for item in list(self._queue._queue):
            if item.priority == Priority.HEAVY:
                heavy += 1
            else:
                light += 1
        return {"heavy": heavy, "light": light}

    async def _worker_loop(self):
        while True:
            item: QueueItem = await self._queue.get()
            self._running = True
            try:
                await item.handler(**item.params)
            except Exception as e:
                print(f"[QueueWorker] task failed ({item.task_type}): {e}")
            finally:
                self._running = False
                self._queue.task_done()


worker = QueueWorker()
