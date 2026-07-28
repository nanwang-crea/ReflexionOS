import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

from app.llm.base import LLMMessage, LLMToolCall
from app.llm.observability import LLMCallObservabilityContext, llm_observability_scope
from app.llm.openai_adapter import OpenAIAdapter
from app.models.llm_config import ProviderType, ResolvedLLMConfig
from app.observability.collector import ObservabilityCollector
from app.storage.database import Database
from app.storage.models import (
    LLMLogicalCallModel,
    LLMProviderRequestModel,
    ModelPricingModel,
)


class TestOpenAIAdapter:
    @staticmethod
    def _seed_price(db: Database):
        with db.get_session() as db_session:
            db_session.add(
                ModelPricingModel(
                    id="price-1",
                    provider_id="provider-openai",
                    model_pattern="model-gpt4",
                    match_type="exact",
                    priority=0,
                    input_price_nano_usd_per_million=1_000_000,
                    output_price_nano_usd_per_million=2_000_000,
                    cached_input_price_nano_usd_per_million=500_000,
                    currency="USD",
                    effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                    effective_to=None,
                )
            )

    @pytest.fixture
    def llm_config(self):
        return ResolvedLLMConfig(
            provider_id="provider-openai",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            model_id="model-gpt4",
            model="gpt-4-turbo-preview",
            api_key="test-api-key",
            temperature=0.7,
            max_tokens=1000,
        )

    @pytest.fixture
    def openai_adapter(self, llm_config):
        return OpenAIAdapter(llm_config)

    def test_adapter_initialization(self, openai_adapter, llm_config):
        assert openai_adapter.config == llm_config
        assert openai_adapter.model == "gpt-4-turbo-preview"

    def test_adapter_initialization_sets_browser_like_default_headers(self, llm_config):
        adapter = OpenAIAdapter(llm_config)

        headers = dict(adapter.client.default_headers)

        assert "claude-cli/" in headers["User-Agent"]
        assert headers["Accept"] == "application/json"
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        assert headers["Cache-Control"] == "no-cache"
        assert headers["Pragma"] == "no-cache"

    def test_get_model_name(self, openai_adapter):
        assert openai_adapter.get_model_name() == "gpt-4-turbo-preview"

    def test_convert_messages_preserves_empty_tool_content(self, openai_adapter):
        messages = [
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[LLMToolCall(id="call_empty", name="mock", arguments={})],
            ),
            LLMMessage(role="tool", content="", tool_call_id="call_empty"),
        ]

        converted = openai_adapter._convert_messages(messages)

        assert converted[0]["tool_calls"][0]["id"] == "call_empty"
        assert converted[1] == {
            "role": "tool",
            "content": "",
            "tool_call_id": "call_empty",
        }

    def test_convert_messages_adds_content_to_tool_message_without_content(
        self,
        openai_adapter,
    ):
        messages = [LLMMessage(role="tool", content=None, tool_call_id="call_missing")]

        converted = openai_adapter._convert_messages(messages)

        assert converted[0] == {
            "role": "tool",
            "content": "",
            "tool_call_id": "call_missing",
        }

    @pytest.mark.asyncio
    async def test_complete_success(self, openai_adapter):
        messages = [LLMMessage(role="user", content="Hello")]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi there!"
        mock_response.model = "gpt-4-turbo-preview"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 30
        mock_response.choices[0].finish_reason = "stop"

        with patch.object(
            openai_adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_response

            response = await openai_adapter.complete(messages)

            assert response.content == "Hi there!"
            assert response.model == "gpt-4-turbo-preview"
            assert response.usage["total_tokens"] == 50

    @pytest.mark.asyncio
    async def test_complete_with_none_content_returns_empty_string(self, openai_adapter):
        messages = [LLMMessage(role="user", content="Hello")]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.model = "gpt-4-turbo-preview"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 30
        mock_response.choices[0].finish_reason = "stop"

        with patch.object(
            openai_adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_response

            response = await openai_adapter.complete(messages)

            assert response.content == ""
            assert response.model == "gpt-4-turbo-preview"
            assert response.usage["total_tokens"] == 50

    @pytest.mark.asyncio
    async def test_stream_complete_updates_late_tool_call_id(self, openai_adapter):
        messages = [LLMMessage(role="user", content="Inspect README")]

        async def mock_stream():
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id=None,
                                    function=SimpleNamespace(
                                        name="mock_tool", arguments='{"path":"README'
                                    ),
                                )
                            ],
                        ),
                        finish_reason=None,
                    )
                ]
            )
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="fc_test_call_id",
                                    function=SimpleNamespace(name=None, arguments='.md"}'),
                                )
                            ],
                        ),
                        finish_reason="tool_calls",
                    )
                ]
            )

        with patch.object(
            openai_adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_stream()

            chunks = []
            async for chunk in openai_adapter.stream_complete(messages, tools=[]):
                chunks.append(chunk)

        tool_call_chunk = next(chunk for chunk in chunks if chunk.type == "tool_calls")
        assert tool_call_chunk.tool_calls[0].id == "fc_test_call_id"
        assert tool_call_chunk.tool_calls[0].name == "mock_tool"
        assert tool_call_chunk.tool_calls[0].arguments == {"path": "README.md"}

    @pytest.mark.asyncio
    async def test_complete_retries_on_rate_limit(self, openai_adapter):
        messages = [LLMMessage(role="user", content="Hello")]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.model = "gpt-4-turbo-preview"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 10
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 5
        mock_response.choices[0].finish_reason = "stop"

        call_count = 0

        async def create_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError(
                    message="rate limited",
                    response=MagicMock(status_code=429),
                    body=None,
                )
            return mock_response

        with (
            patch.object(
                openai_adapter.client.chat.completions,
                "create",
                new_callable=AsyncMock,
                side_effect=create_side_effect,
            ),
            patch("app.llm.retry.asyncio.sleep", new_callable=AsyncMock),
        ):
            response = await openai_adapter.complete(messages)
            assert response.content == "ok"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_complete_records_observability_attempts(self, llm_config, tmp_path):
        db = Database(str(tmp_path / "openai-observability.db"))
        self._seed_price(db)
        collector = ObservabilityCollector(db, journal_dir=tmp_path / "journal")
        adapter = OpenAIAdapter(
            llm_config,
            observability_collector=collector,
            observability_base_context=LLMCallObservabilityContext(
                project_id="project-1",
                session_id="session-1",
                turn_id="turn-1",
                run_id="run-1",
            ),
        )
        messages = [LLMMessage(role="user", content="Hello")]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.choices[0].message.tool_calls = []
        mock_response.choices[0].message.role = "assistant"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4-turbo-preview"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 10
        mock_response.usage.prompt_tokens = 6
        mock_response.usage.completion_tokens = 4
        mock_response.usage.prompt_tokens_details = MagicMock(cached_tokens=2)
        mock_response._request_id = "req-success"

        call_count = 0

        async def create_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError(
                    message="rate limited",
                    response=MagicMock(status_code=429),
                    body=None,
                )
            return mock_response

        with (
            patch.object(
                adapter.client.chat.completions,
                "create",
                new_callable=AsyncMock,
                side_effect=create_side_effect,
            ),
            patch("app.llm.retry.asyncio.sleep", new_callable=AsyncMock),
        ):
            with llm_observability_scope(LLMCallObservabilityContext(call_kind="main")):
                response = await adapter.complete(messages)

        assert response.content == "ok"
        with db.get_session() as db_session:
            logical_calls = db_session.query(LLMLogicalCallModel).all()
            provider_requests = (
                db_session.query(LLMProviderRequestModel)
                .order_by(LLMProviderRequestModel.request_attempt_index.asc())
                .all()
            )

            assert len(logical_calls) == 1
            assert logical_calls[0].status == "completed"
            assert logical_calls[0].call_kind == "main"
            assert logical_calls[0].request_count == 2

            assert [request.request_attempt_index for request in provider_requests] == [0, 1]
            assert provider_requests[0].status == "failed"
            assert provider_requests[1].status == "completed"
            assert provider_requests[1].provider_request_id == "req-success"
            assert provider_requests[1].input_tokens == 6
            assert provider_requests[1].output_tokens == 4
            assert provider_requests[1].cached_input_tokens == 2
            assert provider_requests[1].pricing_id == "price-1"
            assert provider_requests[1].cost_status == "exact"
            assert provider_requests[1].input_cost_nano_usd == 4
            assert provider_requests[1].output_cost_nano_usd == 8
            assert provider_requests[1].cached_input_cost_nano_usd == 1
            assert provider_requests[1].total_cost_nano_usd == 13

    @pytest.mark.asyncio
    async def test_stream_complete_records_early_disconnect_retry(self, llm_config, tmp_path):
        db = Database(str(tmp_path / "openai-stream-observability.db"))
        self._seed_price(db)
        collector = ObservabilityCollector(db, journal_dir=tmp_path / "journal")
        adapter = OpenAIAdapter(
            llm_config,
            observability_collector=collector,
            observability_base_context=LLMCallObservabilityContext(
                project_id="project-1",
                session_id="session-1",
                turn_id="turn-1",
                run_id="run-1",
            ),
        )
        messages = [LLMMessage(role="user", content="Hello")]

        async def broken_stream():
            raise RuntimeError("stream lost before first chunk")
            yield  # pragma: no cover

        async def good_stream():
            yield SimpleNamespace(
                usage=None,
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="ok", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
            )
            yield SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=8,
                    completion_tokens=3,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=1),
                ),
                choices=[],
            )

        with patch.object(
            adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=[broken_stream(), good_stream()],
        ):
            chunks = []
            with llm_observability_scope(LLMCallObservabilityContext(call_kind="main")):
                async for chunk in adapter.stream_complete(messages, tools=[]):
                    chunks.append(chunk)

        assert any(chunk.type == "content" for chunk in chunks)
        assert any(chunk.type == "done" for chunk in chunks)

        with db.get_session() as db_session:
            logical_calls = db_session.query(LLMLogicalCallModel).all()
            provider_requests = (
                db_session.query(LLMProviderRequestModel)
                .order_by(LLMProviderRequestModel.request_attempt_index.asc())
                .all()
            )

            assert len(logical_calls) == 1
            assert logical_calls[0].status == "completed"
            assert logical_calls[0].request_count == 2
            assert [request.status for request in provider_requests] == ["failed", "completed"]
            assert provider_requests[1].input_tokens == 8
            assert provider_requests[1].output_tokens == 3
            assert provider_requests[1].cached_input_tokens == 1
            assert provider_requests[1].pricing_id == "price-1"
            assert provider_requests[1].cost_status == "exact"
            assert provider_requests[1].input_cost_nano_usd == 7
            assert provider_requests[1].output_cost_nano_usd == 6
            assert provider_requests[1].cached_input_cost_nano_usd == 1
            assert provider_requests[1].total_cost_nano_usd == 14

    @pytest.mark.asyncio
    async def test_stream_complete_records_interrupted_on_cancel(self, llm_config, tmp_path):
        db = Database(str(tmp_path / "openai-stream-cancel.db"))
        collector = ObservabilityCollector(db, journal_dir=tmp_path / "journal")
        adapter = OpenAIAdapter(
            llm_config,
            observability_collector=collector,
            observability_base_context=LLMCallObservabilityContext(
                project_id="project-1",
                session_id="session-1",
                turn_id="turn-1",
                run_id="run-1",
            ),
        )

        async def cancelled_stream():
            raise asyncio.CancelledError()
            yield  # pragma: no cover

        with patch.object(
            adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=cancelled_stream(),
        ):
            with pytest.raises(asyncio.CancelledError):
                with llm_observability_scope(LLMCallObservabilityContext(call_kind="main")):
                    async for _chunk in adapter.stream_complete(
                        [LLMMessage(role="user", content="Hello")],
                        tools=[],
                    ):
                        pass

        with db.get_session() as db_session:
            logical_call = db_session.query(LLMLogicalCallModel).one()
            provider_request = db_session.query(LLMProviderRequestModel).one()
            assert logical_call.status == "interrupted"
            assert provider_request.status == "interrupted"

    @pytest.mark.asyncio
    async def test_complete_does_not_retry_auth_error(self, openai_adapter):
        from openai import AuthenticationError

        messages = [LLMMessage(role="user", content="Hello")]

        with (
            patch.object(
                openai_adapter.client.chat.completions,
                "create",
                new_callable=AsyncMock,
                side_effect=AuthenticationError(
                    message="bad key",
                    response=MagicMock(status_code=401),
                    body=None,
                ),
            ),
            pytest.raises(AuthenticationError),
        ):
            await openai_adapter.complete(messages)

    @pytest.mark.asyncio
    async def test_complete_retries_all_retryable_errors(self, openai_adapter):
        messages = [LLMMessage(role="user", content="Hello")]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.model = "gpt-4-turbo-preview"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 10
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 5
        mock_response.choices[0].finish_reason = "stop"

        errors = [
            RateLimitError(message="429", response=MagicMock(status_code=429), body=None),
            APITimeoutError(request=MagicMock()),
            APIConnectionError(request=MagicMock()),
            InternalServerError(message="500", response=MagicMock(status_code=500), body=None),
        ]
        call_count = 0

        async def create_side_effect(**kwargs):
            nonlocal call_count
            if call_count < len(errors):
                exc = errors[call_count]
                call_count += 1
                raise exc
            call_count += 1
            return mock_response

        with (
            patch.object(
                openai_adapter.client.chat.completions,
                "create",
                new_callable=AsyncMock,
                side_effect=create_side_effect,
            ),
            patch("app.llm.retry.asyncio.sleep", new_callable=AsyncMock),
        ):
            response = await openai_adapter.complete(messages)
            assert response.content == "ok"
            assert call_count == 5  # 4 errors + 1 success

    @pytest.mark.asyncio
    async def test_stream_complete_dsml_tool_calls(self, openai_adapter):
        """DSML markup in text content is parsed into structured tool_calls."""
        messages = [LLMMessage(role="user", content="Read the file")]

        dsml = (
            '<|DSML|tool_calls>'
            '<|DSML|invoke name="file">'
            '<|DSML|parameter name="action"><![CDATA[read]]></|DSML|parameter>'
            '<|DSML|parameter name="path"><![CDATA[/tmp/test.py]]></|DSML|parameter>'
            '</|DSML|invoke>'
            '</|DSML|tool_calls>'
        )

        async def mock_stream():
            # Pre-text chunk
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(content="Let me check.", tool_calls=None),
                    finish_reason=None,
                )]
            )
            # DSML arrives as a single chunk
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=dsml, tool_calls=None),
                    finish_reason=None,
                )]
            )
            # Stream ends
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=None, tool_calls=None),
                    finish_reason="stop",
                )]
            )

        with patch.object(
            openai_adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_stream()
            chunks = []
            async for chunk in openai_adapter.stream_complete(messages, tools=[]):
                chunks.append(chunk)

        content_chunks = [c for c in chunks if c.type == "content"]
        tool_call_chunks = [c for c in chunks if c.type == "tool_calls"]
        done_chunks = [c for c in chunks if c.type == "done"]

        # Pre-text yielded before DSML detection
        assert len(content_chunks) == 1
        assert content_chunks[0].content == "Let me check."
        # DSML parsed into tool_calls
        assert len(tool_call_chunks) == 1
        tc = tool_call_chunks[0].tool_calls[0]
        assert tc.name == "file"
        assert tc.arguments == {"action": "read", "path": "/tmp/test.py"}
        # No "done" chunk — tool_calls chunk carries finish_reason
        assert len(done_chunks) == 0

    @pytest.mark.asyncio
    async def test_stream_complete_dsml_split_across_chunks(self, openai_adapter):
        """DSML prefix split across chunks is handled via tail holdback."""
        messages = [LLMMessage(role="user", content="Read")]

        async def mock_stream():
            # Partial <|DSML| prefix arrives at end of first chunk
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(content="Thinking<|D", tool_calls=None),
                    finish_reason=None,
                )]
            )
            # Rest of DSML in next chunk
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(content='SML|tool_calls><|DSML|invoke name="file">'
                                          '<|DSML|parameter name="action"><![CDATA[read]]></|DSML|parameter>'
                                          '</|DSML|invoke></|DSML|tool_calls>', tool_calls=None),
                    finish_reason=None,
                )]
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=None, tool_calls=None),
                    finish_reason="stop",
                )]
            )

        with patch.object(
            openai_adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_stream()
            chunks = []
            async for chunk in openai_adapter.stream_complete(messages, tools=[]):
                chunks.append(chunk)

        content_chunks = [c for c in chunks if c.type == "content"]
        tool_call_chunks = [c for c in chunks if c.type == "tool_calls"]

        # "Thinking" was yielded; the "<|D" tail was held back
        assert len(content_chunks) == 1
        assert content_chunks[0].content == "Thinking"
        # DSML parsed correctly despite split
        assert len(tool_call_chunks) == 1
        assert tool_call_chunks[0].tool_calls[0].name == "file"

    @pytest.mark.asyncio
    async def test_stream_complete_no_dsml_normal_flow(self, openai_adapter):
        """Normal streaming without DSML is unaffected."""
        messages = [LLMMessage(role="user", content="Hello")]

        async def mock_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(content="Hi ", tool_calls=None),
                    finish_reason=None,
                )]
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(content="there!", tool_calls=None),
                    finish_reason=None,
                )]
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=None, tool_calls=None),
                    finish_reason="stop",
                )]
            )

        with patch.object(
            openai_adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_stream()
            chunks = []
            async for chunk in openai_adapter.stream_complete(messages, tools=[]):
                chunks.append(chunk)

        content_chunks = [c for c in chunks if c.type == "content"]
        done_chunks = [c for c in chunks if c.type == "done"]
        assert len(content_chunks) == 2
        assert content_chunks[0].content == "Hi "
        assert content_chunks[1].content == "there!"
        assert len(done_chunks) == 1

    @pytest.mark.asyncio
    async def test_complete_dsml_tool_calls(self, openai_adapter):
        """Non-streaming complete() also extracts DSML tool calls."""
        messages = [LLMMessage(role="user", content="Read file")]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            'Let me read it. '
            '<|DSML|tool_calls>'
            '<|DSML|invoke name="file">'
            '<|DSML|parameter name="action"><![CDATA[read]]></|DSML|parameter>'
            '<|DSML|parameter name="path"><![CDATA[/tmp/x]]></|DSML|parameter>'
            '</|DSML|invoke>'
            '</|DSML|tool_calls>'
        )
        mock_response.choices[0].message.tool_calls = None
        mock_response.model = "gpt-4-turbo-preview"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 10
        mock_response.usage.total_tokens = 15
        mock_response.choices[0].finish_reason = "stop"

        with patch.object(
            openai_adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_response
            response = await openai_adapter.complete(messages)

        assert response.has_tool_calls
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "file"
        assert response.tool_calls[0].arguments == {"action": "read", "path": "/tmp/x"}
        assert "Let me read it." in response.content
        assert "<|DSML|" not in response.content
        assert response.finish_reason == "tool_calls"

    def test_convert_multimodal_messages(self, openai_adapter):
        """测试多模态消息转换（内部格式 → OpenAI 格式）"""
        messages = [
            LLMMessage(
                role="user",
                content=[
                    {"type": "text", "text": "分析这张图片"},
                    {"type": "image_url", "url": "data:image/png;base64,abc123"},
                ]
            )
        ]

        converted = openai_adapter._convert_messages(messages)

        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert isinstance(converted[0]["content"], list)
        assert len(converted[0]["content"]) == 2
        assert converted[0]["content"][0] == {"type": "text", "text": "分析这张图片"}
        # image_url 应被转换为 OpenAI 嵌套格式
        assert converted[0]["content"][1] == {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,abc123"}
        }
