"""LLM 请求的异步重试工具。

提供带指数退避 + 抖动的通用异步重试函数 retry_async，用于包装 LLM 调用，
在遇到限流/超时/连接失败/服务端错误等瞬时性异常时自动重试，并支持通过
cancel_event 中途取消重试循环。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import random
from collections.abc import Callable
from typing import Any, TypeVar

from app.errors import LLMRetryExhaustedError

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_RETRIES = 5
BASE_DELAY = 2.0
MAX_DELAY = 60.0


def _retry_delay(attempt: int) -> float:
    """计算第 attempt 次重试的等待时间（带抖动的指数退避）

    输入: attempt - 当前重试次数（从 0 开始）
    逻辑: 基础延迟按 2^attempt 指数增长，封顶 MAX_DELAY；再叠加 0~25% 的随机抖动，
          避免多个请求同时失败后又同时重试造成惊群效应
    返回: 本次重试前应等待的秒数
    """
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
    """对异步可调用对象执行带指数退避的重试

    输入:
        fn: 待执行的无参异步可调用对象（通常是一个 lambda 包装的 API 调用）
        retryable_exceptions: 触发重试的异常类型元组，命中之外的异常直接向上抛出
        max_retries: 最大重试次数
        on_retry: 每次触发重试时的回调 (exception, attempt, delay)，可为异步函数；
                  不提供时默认写 warning 日志
        raise_retry_exhausted: 重试耗尽后是否包装为 LLMRetryExhaustedError 抛出，
                                否则直接抛出最后一次捕获的原始异常
        cancel_event: 取消事件；在每次尝试前以及退避等待期间检查，一旦被设置
                      立即以 asyncio.CancelledError 中止重试循环（等待可被打断，
                      无需等满整个 delay）

    逻辑:
        循环最多 max_retries+1 次调用 fn；仅 retryable_exceptions 命中的异常会被
        捕获并触发退避等待后重试，其余异常立即向上传播；每次退避时若配置了
        cancel_event，用 asyncio.wait 让"睡眠"和"等待取消信号"竞速，谁先完成
        就先响应，从而支持随时中断重试

    返回:
        fn() 的成功返回值；重试耗尽后按 raise_retry_exhausted 决定抛出何种异常
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
                # 让"退避等待"和"取消信号"两个协程竞速，任一先完成就返回，
                # 从而实现退避期间也能被 cancel_event 及时打断，而不是死等 delay 秒
                done, pending = await asyncio.wait(
                    [asyncio.ensure_future(asyncio.sleep(delay)),
                     asyncio.ensure_future(cancel_event.wait())],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    task.exception()
                for task in pending:
                    task.cancel()
                if cancel_event.is_set():
                    # 主动取消属于独立控制流，与当前 except 捕获的重试异常无关，
                    # 用 from None 断开异常链，避免把无关的重试错误挂到取消信号上
                    raise asyncio.CancelledError() from None
            else:
                await asyncio.sleep(delay)

    if raise_retry_exhausted and last_exc is not None:
        raise LLMRetryExhaustedError(last_exception=last_exc, max_retries=max_retries) from last_exc

    raise last_exc  # type: ignore[misc]
