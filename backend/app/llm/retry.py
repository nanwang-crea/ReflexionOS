from __future__ import annotations

import asyncio
import inspect
import logging
import random
from collections.abc import Callable
from typing import Any, TypeVar

from app.errors import LLMRetryExhaustedError as RetryExhaustedError

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_RETRIES = 5
BASE_DELAY = 2.0
MAX_DELAY = 60.0


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
    cancel_event: asyncio.Event | None = None,
) -> Any:
    """
    Retry an async callable with exponential backoff.

    Only exceptions in *retryable_exceptions* trigger a retry;
    everything else propagates immediately.

    If *cancel_event* is provided and becomes set, the retry loop
    aborts immediately by raising ``asyncio.CancelledError``.
    The event is checked before each attempt and during the
    back-off sleep (which is interrupted as soon as the event fires).
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()
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
            if cancel_event is not None:
                done, _ = await asyncio.wait(
                    [asyncio.ensure_future(asyncio.sleep(delay)),
                     asyncio.ensure_future(cancel_event.wait())],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    task.exception()
                if cancel_event.is_set():
                    raise asyncio.CancelledError()
            else:
                await asyncio.sleep(delay)

    if raise_retry_exhausted and last_exc is not None:
        raise RetryExhaustedError(last_exception=last_exc, max_retries=max_retries) from last_exc

    raise last_exc  # type: ignore[misc]
