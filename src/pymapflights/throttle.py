"""Client-side enforcement of the map.flights rate limits, shared per key.

All clients created with the same key in one process share one `KeyThrottle`,
so no caller can bypass the live-data interval by creating a second client.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Final

from .exceptions import MapFlightsRateLimitError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

LIVE_INTERVAL_S: Final = 5.0
"""`/live` and `/near`: at most one request every 5 s per key."""
MINUTE_LIMIT: Final = 60
"""All endpoints together: at most 60 requests per minute per key."""
MINUTE_WINDOW_S: Final = 60.0

SCOPE_LIVE: Final = "live"
SCOPE_MINUTE: Final = "minute"
SCOPE_DAY: Final = "day"


class KeyThrottle:
    """Rate limits of one API key."""

    def __init__(self) -> None:
        """Initialize with the limits in force at creation time."""
        self.live_interval = LIVE_INTERVAL_S
        self.minute_limit = MINUTE_LIMIT
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None
        self._next_live = 0.0
        self._minute: deque[float] = deque()
        self._blocked: dict[str, float] = {}

    def _live_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    @asynccontextmanager
    async def live(self) -> AsyncIterator[None]:
        """Hold the live slot of the key for one request.

        Waits for the next free slot when it is at most one interval away and
        refuses (local 429) when the key is blocked for longer. The slot is used
        up whatever the outcome; a `/near` outside the area costs it too.
        """
        async with self._live_lock():
            now = time.monotonic()
            free_at = max(self._next_live, self._blocked.get(SCOPE_LIVE, 0.0))
            wait = free_at - now
            if wait > self.live_interval:
                raise _local_error(SCOPE_LIVE, wait)
            if wait > 0:
                await asyncio.sleep(wait)
            self._take_minute_slot()
            try:
                yield
            finally:
                self._next_live = time.monotonic() + self.live_interval

    def rest(self) -> None:
        """Account for one request to an endpoint outside the live group."""
        now = time.monotonic()
        for scope in (SCOPE_DAY, SCOPE_MINUTE):
            wait = self._blocked.get(scope, 0.0) - now
            if wait > 0:
                raise _local_error(scope, wait)
        self._take_minute_slot()

    def block(self, scope: str, retry_after: int | None) -> None:
        """Remember a 429 so that further requests are not sent too early."""
        if retry_after is None or retry_after <= 0:
            return
        until = time.monotonic() + retry_after
        self._blocked[scope] = max(self._blocked.get(scope, 0.0), until)

    def _take_minute_slot(self) -> None:
        now = time.monotonic()
        while self._minute and self._minute[0] <= now - MINUTE_WINDOW_S:
            self._minute.popleft()
        if len(self._minute) >= self.minute_limit:
            raise _local_error(SCOPE_MINUTE, self._minute[0] + MINUTE_WINDOW_S - now)
        self._minute.append(now)


def _local_error(scope: str, wait: float) -> MapFlightsRateLimitError:
    retry_after = max(1, math.ceil(wait))
    return MapFlightsRateLimitError(
        f"Rate limit '{scope}' reached, retry in {retry_after} s",
        retry_after=retry_after,
        scope=scope,
        limit=None,
        local=True,
    )


_throttles: dict[str, KeyThrottle] = {}


def throttle_for(api_key: str) -> KeyThrottle:
    """Return the shared throttle of `api_key`."""
    if (throttle := _throttles.get(api_key)) is None:
        throttle = _throttles[api_key] = KeyThrottle()
    return throttle
