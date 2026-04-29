import pytest

from app.llm.retry import MAX_RETRIES, _retry_delay, retry_async


class TestRetryDelay:
    def test_exponential_backoff(self):
        d0 = _retry_delay(0)
        d1 = _retry_delay(1)
        d2 = _retry_delay(2)
        # base=2.0 → expected ~2, 4, 8 (plus jitter up to 25%)
        assert 2.0 <= d0 <= 2.5
        assert 4.0 <= d1 <= 5.0
        assert 8.0 <= d2 <= 10.0

    def test_caps_at_max_delay(self):
        delay = _retry_delay(100)
        assert delay <= 60.0 + 60.0 * 0.25


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_succeeds_immediately(self):
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_async(fn, retryable_exceptions=(ValueError,))
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_retryable_exception(self):
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "ok"

        result = await retry_async(
            fn,
            retryable_exceptions=(ValueError,),
            max_retries=5,
        )
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_non_retryable_immediately(self):
        async def fn():
            raise TypeError("not retryable")

        with pytest.raises(TypeError, match="not retryable"):
            await retry_async(fn, retryable_exceptions=(ValueError,))

    @pytest.mark.asyncio
    async def test_exhausts_retries_and_raises_last(self):
        async def fn():
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            await retry_async(fn, retryable_exceptions=(ValueError,), max_retries=2)

    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        attempts = []

        async def fn():
            if len(attempts) < 2:
                raise ValueError("transient")
            return "ok"

        def on_retry(exc, attempt, delay):
            attempts.append((type(exc).__name__, attempt, delay > 0))

        await retry_async(
            fn,
            retryable_exceptions=(ValueError,),
            max_retries=5,
            on_retry=on_retry,
        )
        assert len(attempts) == 2
        assert attempts[0][0] == "ValueError"
        assert attempts[0][2] is True  # delay > 0

    @pytest.mark.asyncio
    async def test_async_on_retry_callback_is_awaited(self):
        attempts = []

        async def fn():
            if len(attempts) < 2:
                raise ValueError("transient")
            return "ok"

        async def on_retry(exc, attempt, delay):
            attempts.append((type(exc).__name__, attempt, delay > 0))

        await retry_async(
            fn,
            retryable_exceptions=(ValueError,),
            max_retries=5,
            on_retry=on_retry,
        )
        assert len(attempts) == 2
        assert attempts[0][0] == "ValueError"

    @pytest.mark.asyncio
    async def test_max_retries_respected(self):
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await retry_async(fn, retryable_exceptions=(ValueError,), max_retries=3)

        # 1 initial + 3 retries = 4 total calls
        assert call_count == 4
