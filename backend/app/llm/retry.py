from __future__ import annotations

import asyncio
import inspect
import logging
import random
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_RETRIES = 5
BASE_DELAY = 2.0
MAX_DELAY = 60.0


class RetryExhaustedError(Exception):
    """Raised when a retryable operation exhausts its configured retry budget."""

    def __init__(self, last_exception: Exception, *, max_retries: int):
        self.last_exception = last_exception
        self.max_retries = max_retries
        super().__init__(f"retry exhausted after {max_retries} retries: {last_exception}")


def _retry_delay(attempt: int) -> float:
    """Exponential backoff with jitter: 2^attempt * base + random jitter."""
    delay = min(BASE_DELAY * (2**attempt), MAX_DELAY)
    jitter = random.uniform(0, delay * 0.25)
    return delay + jitter


async def retry_async(
    fn: Callable[..., Any],
    *,
    retryable_exceptions: tuple[type[Exception], ...],
    max_retries: int = MAX_RETRIES,
    on_retry: Callable[[Exception, int, int], None] | None = None,
    raise_retry_exhausted: bool = False,
) -> Any:
    """
    Retry an async callable with exponential backoff.

    Only exceptions in *retryable_exceptions* trigger a retry;
    everything else propagates immediately.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            delay = _retry_delay(attempt)
            if on_retry:
                result = on_retry(exc, attempt, delay)
                if inspect.isawaitable(result):
                    await result
            else:
                logger.warning(
                    "LLM 请求失败 (%s)，第 %d/%d 次重试，%.1fs 后重试: %s",
                    type(exc).__name__,
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                )
            await asyncio.sleep(delay)

    if raise_retry_exhausted and last_exc is not None:
        raise RetryExhaustedError(last_exc, max_retries=max_retries) from last_exc

    raise last_exc  # type: ignore[misc]
