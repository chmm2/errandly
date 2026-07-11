"""Resilience primitives for talking to things that fail: retry with
exponential backoff for transient blips, a circuit breaker so a dead
dependency is failed fast instead of hammered.

Both are deliberately small — the point is owning the mechanism, not
importing a framework.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from enum import Enum

logger = logging.getLogger(__name__)


async def retry_with_backoff[T](
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 4,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Retry `fn` with exponential backoff + full jitter.

    Jitter matters: without it, every client that failed together retries
    together, and the recovering service is knocked straight back down
    (the thundering-herd / retry-storm problem).
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await fn()
        except retry_on as exc:
            last_exc = exc
            if attempt == attempts - 1:
                break
            delay = random.uniform(0, min(max_delay, base_delay * (2**attempt)))
            logger.warning(
                "attempt %d/%d failed (%s); retrying in %.2fs",
                attempt + 1, attempts, exc, delay,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


class CircuitState(str, Enum):
    CLOSED = "closed"        # normal operation
    OPEN = "open"            # dependency considered down; fail fast
    HALF_OPEN = "half_open"  # probing: let one call through


class CircuitOpenError(Exception):
    """Raised instead of calling a dependency the breaker considers down."""


class CircuitBreaker:
    """Classic three-state breaker.

    CLOSED → (failure_threshold consecutive failures) → OPEN
    OPEN → (reset_timeout elapses) → HALF_OPEN
    HALF_OPEN → success → CLOSED · failure → OPEN

    Protects the *caller* (no time wasted on doomed calls) and the
    *dependency* (no hammering while it restarts).
    """

    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None
        self.state = CircuitState.CLOSED

    def _check(self) -> None:
        if self.state is CircuitState.OPEN:
            if time.monotonic() - (self._opened_at or 0) >= self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("breaker %s: half-open, probing", self.name)
            else:
                raise CircuitOpenError(f"{self.name} circuit is open")

    def _on_success(self) -> None:
        if self.state is not CircuitState.CLOSED:
            logger.info("breaker %s: recovered, closing", self.name)
        self._failures = 0
        self.state = CircuitState.CLOSED

    def _on_failure(self) -> None:
        self._failures += 1
        if self.state is CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning("breaker %s: OPEN after %d failures", self.name, self._failures)

    async def call[T](self, fn: Callable[[], Awaitable[T]]) -> T:
        self._check()
        try:
            result = await fn()
        except Exception:
            self._on_failure()
            raise
        self._on_success()
        return result
