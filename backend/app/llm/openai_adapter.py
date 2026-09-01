"""OpenAI 兼容接口的 LLM 适配器实现。

将 UniversalLLMInterface 统一接口对接到 OpenAI Chat Completion API
（以及使用相同协议的第三方兼容服务）。核心职责：
1. 内部消息/工具定义 与 OpenAI 请求体格式的双向转换；
2. 非流式/流式两种调用方式，并叠加指数退避重试（retry.py）；
3. 流式场景下对工具调用增量（tool_calls delta）做聚合与索引纠错，
   兼容部分服务商在同一 index 下拼接多个工具调用的乱序/粘包情况；
4. 兼容部分模型把工具调用以 DSML 文本形式塞进正文的情况（dsml_tool_parser.py）；
5. 兼容部分模型的推理/思维链内容字段命名差异（reasoning_content 等）。
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from app.llm.base import (
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    StreamChunk,
    UniversalLLMInterface,
)
from app.llm.client_headers import browser_like_default_headers
from app.llm.dsml_tool_parser import contains_dsml, parse_dsml_tool_calls
from app.llm.retry import retry_async
from app.models.llm_config import ResolvedLLMConfig

logger = logging.getLogger(__name__)

# Exceptions that warrant a retry (transient / server-side failures).
_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


class OpenAIAdapter(UniversalLLMInterface):
    """OpenAI API 适配器 - 支持原生工具调用和流式输出"""

    def __init__(self, config: ResolvedLLMConfig, *, on_retry=None, cancel_event: asyncio.Event | None = None):
        """初始化适配器

        输入:
            config: 已解析的 LLM 配置（模型名、api_key、base_url、temperature、max_tokens 等）
            on_retry: 重试回调，透传给 retry_async
            cancel_event: 取消事件，透传给 retry_async，用于中止重试/等待
        逻辑: 保存配置，构造底层 AsyncOpenAI 客户端（未配置 api_key 时用占位符，
              避免 SDK 因缺少 key 直接报错；附加类浏览器请求头降低被网关拦截概率）
        返回: 无
        """
        self.config = config
        self.model = config.model
        self.on_retry = on_retry
        self.cancel_event = cancel_event

        self.client = AsyncOpenAI(
            api_key=config.api_key or "reflexion-placeholder-key",
            base_url=config.base_url if config.base_url else None,
            default_headers=browser_like_default_headers(),
        )

        logger.info("OpenAI 适配器初始化完成, 模型: %s", self.model)

    async def complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> LLMResponse:
        """
        同步补全（支持工具调用），带指数退避重试

        Args:
            messages: 消息列表
            tools: 可用工具列表

        Returns:
            LLMResponse: 响应结果
        """
        openai_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools) if tools else None

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        response = await retry_async(
            lambda: self.client.chat.completions.create(**kwargs),
            retryable_exceptions=_RETRYABLE,
            on_retry=self.on_retry,
            raise_retry_exhausted=True,
            cancel_event=self.cancel_event,
        )

        return self._parse_response(response)

    _MAX_STREAM_RETRIES = 3  # 流式连接阶段/早期断连的最大重试次数（已产出内容后断连不再重试）

    async def stream_complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> AsyncIterator[StreamChunk]:
        """
        流式补全（支持工具调用），连接阶段和流早期断连均带重试

        Args:
            messages: 消息列表
            tools: 可用工具列表

        Yields:
            StreamChunk: 流式输出块
        """
        openai_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools) if tools else None

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        # 外层循环：流连接建立后、尚未产出任何内容前就断连，则整体重试
        # （已经 yield 过内容后再出错就不重试，避免给调用方产出重复/错乱的内容）
        for stream_attempt in range(self._MAX_STREAM_RETRIES):
            stream = await retry_async(
                lambda: self.client.chat.completions.create(**kwargs),
                retryable_exceptions=_RETRYABLE,
                on_retry=self.on_retry,
                raise_retry_exhausted=True,
                cancel_event=self.cancel_event,
            )

            # current_tool_calls: 按流式 index 聚合中的工具调用 {index: {id, name, arguments}}
            # _next_tc_index: 下一个可用的工具调用 index，用于在检测到"粘包/index 复用"时分配新 index
            current_tool_calls: dict[int, dict] = {}
            _next_tc_index = 0
            # DSML 是部分模型把工具调用写进正文文本的标记前缀，见 dsml_tool_parser.py
            _dsml_prefix = "<|DSML|"
            _content_buf = ""  # 累积至今的完整正文内容，用于检测/截取 DSML 片段
            _dsml_detected = False  # 一旦命中 DSML 前缀，后续正文不再作为普通 content 输出
            _yielded_cursor = 0  # _content_buf 中已经 yield 给调用方的位置游标
            yielded_any = False  # 本次连接是否已产出过任何内容，决定断连时是否允许重试

            try:
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason

                    # 部分模型/网关会在 delta 上携带推理（思维链）内容，字段名不统一，见 _extract_reasoning_delta
                    reasoning_delta = self._extract_reasoning_delta(delta)
                    if reasoning_delta:
                        yielded_any = True
                        yield StreamChunk(type="reasoning", reasoning_content=reasoning_delta)

                    if delta.content:
                        _content_buf += delta.content

                        if not _dsml_detected:
                            # 尚未检测到 DSML：先看当前累积内容里是否已经出现完整的 DSML 前缀
                            idx = _content_buf.find(_dsml_prefix)
                            if idx != -1:
                                # 命中 DSML 前缀：其之前的部分是正常正文，照常输出；
                                # 之后的内容不再作为 content 流式吐出（留到 finish 时统一走 DSML 解析）
                                _dsml_detected = True
                                if idx > _yielded_cursor:
                                    yielded_any = True
                                    yield StreamChunk(
                                        type="content",
                                        content=_content_buf[_yielded_cursor:idx],
                                    )
                                _yielded_cursor = len(_content_buf)
                            else:
                                # 尚未出现 DSML 前缀，但需要防止前缀恰好被切在两个 chunk 之间：
                                # 只输出到"结尾不与 DSML 前缀任何前缀重叠"的安全位置，
                                # 剩余的可疑尾部留在缓冲区等下一个 chunk 补全后再判断
                                safe_end = len(_content_buf)
                                for i in range(1, min(len(_dsml_prefix), len(_content_buf) + 1)):
                                    if _dsml_prefix.startswith(_content_buf[-i:]):
                                        safe_end = len(_content_buf) - i
                                        break
                                if safe_end > _yielded_cursor:
                                    yielded_any = True
                                    yield StreamChunk(
                                        type="content",
                                        content=_content_buf[_yielded_cursor:safe_end],
                                    )
                                    _yielded_cursor = safe_end

                    if delta.tool_calls:
                        # 聚合结构化 tool_calls 增量。多数 OpenAI 兼容服务按 tc.index 分组增量拼接，
                        # 但部分服务商在同一个 index 下把多个工具调用的 JSON 参数直接拼接输出
                        # （形如 "{...}{...}"），或者 id 复用导致新旧调用被误判为同一个。
                        # 下面通过"已有调用的 arguments 已闭合成完整 JSON 对象（以 } 结尾）却又来了新数据"
                        # 这一信号，判定为新的工具调用，主动分配新 index，避免把多个调用的参数拼在一起。
                        for tc in delta.tool_calls:
                            tc_index = tc.index

                            if tc_index not in current_tool_calls:
                                if tc.id and tc_index != _next_tc_index:
                                    # 有新 id 且 index 不连续：视为一次全新的工具调用，正常按其自身 index 记录
                                    pass
                                elif not tc.id and tc_index in current_tool_calls and current_tool_calls[tc_index]["arguments"].rstrip().endswith("}"):
                                    # 无 id 且该 index 已存在且参数已闭合：说明是紧跟着的下一个调用复用了 index，改用新 index
                                    _next_tc_index += 1
                                    tc_index = _next_tc_index
                                else:
                                    _next_tc_index = max(_next_tc_index, tc_index)

                                current_tool_calls[tc_index] = {
                                    "id": tc.id or "",
                                    "name": "",
                                    "arguments": "",
                                }
                                _next_tc_index = max(_next_tc_index, tc_index)
                            elif tc.id:
                                current_tool_calls[tc_index]["id"] = tc.id

                            if tc.function:
                                if tc.function.name:
                                    current_tool_calls[tc_index]["name"] = tc.function.name
                                if tc.function.arguments:
                                    existing = current_tool_calls[tc_index]["arguments"]
                                    if existing.rstrip().endswith("}") and tc.function.arguments.lstrip().startswith("{"):
                                        # 已有参数已经是完整 JSON 对象结尾，新增量又以 { 开头：
                                        # 判定为粘包出的第二个工具调用，拆分到新 index 而不是拼接到一起
                                        _next_tc_index += 1
                                        new_idx = _next_tc_index
                                        current_tool_calls[new_idx] = {
                                            "id": tc.id or "",
                                            "name": tc.function.name or current_tool_calls[tc_index]["name"],
                                            "arguments": tc.function.arguments,
                                        }
                                        tc_index = new_idx
                                    else:
                                        current_tool_calls[tc_index]["arguments"] += tc.function.arguments

                    if finish_reason:
                        # 流结束，按优先级判定最终结果：
                        # 1) 有结构化 tool_calls：直接聚合产出
                        # 2) 无结构化 tool_calls 但检测到 DSML：对累积正文做 DSML 解析
                        # 3) 都没有：把缓冲区剩余内容（未被判定为 DSML 的部分）作为普通 content 补发
                        has_structured_tc = bool(current_tool_calls)

                        if has_structured_tc:
                            yield StreamChunk(
                                type="tool_calls",
                                tool_calls=self._build_structured_tool_calls(current_tool_calls),
                                finish_reason=finish_reason,
                            )
                        elif _dsml_detected:
                            result = parse_dsml_tool_calls(_content_buf)
                            if result.tool_calls:
                                yield StreamChunk(
                                    type="tool_calls",
                                    tool_calls=result.tool_calls,
                                    finish_reason=finish_reason,
                                )
                            else:
                                # 检测到 DSML 前缀但最终没解析出工具调用（可能只是文本恰好包含该片段）：
                                # 把之前未输出的剩余内容原样吐出，按普通结束处理
                                remaining = _content_buf[_yielded_cursor:]
                                if remaining:
                                    yield StreamChunk(type="content", content=remaining)
                                yield StreamChunk(type="done", finish_reason=finish_reason)
                        else:
                            # 补发因"安全边界"暂缓输出的尾部内容，再发送结束标记
                            remaining = _content_buf[_yielded_cursor:]
                            if remaining:
                                yield StreamChunk(type="content", content=remaining)
                            yield StreamChunk(type="done", finish_reason=finish_reason)

                        return
            except Exception as e:
                # 若本次连接还未产出任何内容，则视为连接阶段失败，允许整体重试；
                # 一旦已经 yield 过内容，为避免调用方收到重复/错乱的流，直接以 error 结束
                if not yielded_any and stream_attempt < self._MAX_STREAM_RETRIES - 1:
                    logger.warning(
                        "OpenAI 流式连接中断 (attempt %d/%d), 重试: %s",
                        stream_attempt + 1,
                        self._MAX_STREAM_RETRIES,
                        e,
                    )
                    continue
                logger.error("OpenAI 流式读取失败: %s", e)
                yield StreamChunk(type="error", error=str(e))
                return

    def get_model_name(self) -> str:
        """获取模型名称

        返回: 当前适配器绑定的模型名
        """
        return self.model

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """将内部消息格式转换为 OpenAI 请求体格式

        输入: messages - 内部统一格式的消息列表
        逻辑: 逐条转换 role/content；content 为多模态列表时逐部分转换（见 _convert_content_part），
              为 None 且角色是 tool 时补空字符串（OpenAI 要求 tool 消息 content 不可省略）；
              有 tool_calls/tool_call_id 时按 OpenAI 结构附加（工具调用参数序列化为 JSON 字符串）
        返回: OpenAI chat.completions 接口所需的 messages 列表
        """
        openai_messages = []

        for msg in messages:
            openai_msg: dict[str, Any] = {"role": msg.role}

            if isinstance(msg.content, list):
                openai_msg["content"] = [
                    self._convert_content_part(part) for part in msg.content
                ]
            elif msg.content is not None:
                openai_msg["content"] = msg.content
            elif msg.role == "tool":
                openai_msg["content"] = ""

            if msg.tool_calls:
                openai_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in msg.tool_calls
                ]

            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id

            openai_messages.append(openai_msg)

        return openai_messages

    def _convert_content_part(self, part: dict) -> dict:
        """将内部格式的单个多模态内容块转换为 OpenAI API 格式

        输入: part - 内部格式的内容块字典（如 {"type": "text", ...} 或 {"type": "image_url", ...}）
        逻辑: 按 type 分派：text 直接透传文本；image_url 兼容内部两种取值路径
              （顶层 url 字段，或嵌套的 image_url.url），转成 OpenAI 期望的嵌套结构；
              未识别的类型直接抛错，避免静默丢数据
        返回: OpenAI 格式的内容块字典
        """
        part_type = part.get("type")
        if part_type == "text":
            return {"type": "text", "text": part.get("text", "")}
        elif part_type == "image_url":
            # 内部格式: {"type": "image_url", "url": "..."} → OpenAI: {"type": "image_url", "image_url": {"url": "..."}}
            url = part.get("url") or part.get("image_url", {}).get("url")
            return {"type": "image_url", "image_url": {"url": url}}
        else:
            raise ValueError(f"未知的内容类型: {part_type}")

    def _convert_tools(self, tools: list[LLMToolDefinition]) -> list[dict[str, Any]]:
        """将内部工具定义列表转换为 OpenAI function-calling 格式

        输入: tools - 内部统一格式的工具定义列表
        逻辑: 逐个包装为 OpenAI 要求的 {"type": "function", "function": {...}} 结构
        返回: OpenAI tools 参数所需的字典列表
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    @staticmethod
    def _split_concatenated_json(raw: str) -> list[str]:
        """拆分被粘连在一起的多个 JSON 对象（如 "}{" 或 "} {" 形式）

        部分 LLM 服务商在多个 tool_calls 共享同一个流式 index 时，会把它们的
        参数 JSON 直接首尾拼接输出，导致一段字符串里包含多个独立 JSON 对象。

        输入: raw - 可能包含多个拼接 JSON 对象的原始字符串
        逻辑: 用花括号深度计数器扫描字符串，配合字符串/转义状态跟踪，
              确保引号内的花括号不会干扰深度计算；每当深度归零即认为
              闭合了一个完整 JSON 对象，切分出来
        返回: 拆分出的 JSON 片段列表；若括号未能配平（解析异常）则原样返回单元素列表兜底
        """
        results: list[str] = []
        depth = 0
        start = -1
        in_string = False
        escape = False

        for i, ch in enumerate(raw):
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    results.append(raw[start:i + 1])
                    start = -1

        if depth != 0:
            results.append(raw)

        return results or [raw]

    def _build_structured_tool_calls(
        self, current_tool_calls: dict[int, dict]
    ) -> list[LLMToolCall]:
        """将流式聚合得到的 tool_call 增量数据组装为最终的 LLMToolCall 列表

        输入: current_tool_calls - stream_complete 中按 index 聚合的 {index: {id, name, arguments(原始JSON字符串)}}
        逻辑: 按 index 升序遍历，逐个尝试将 arguments 解析为 JSON；
              若解析失败，先尝试用 _split_concatenated_json 拆分出多个粘连的 JSON 对象
              （某些服务商会把同一 index 下的多次调用参数拼接在一起），
              首个片段作为当前工具调用的参数，其余片段各自组装成新的 LLMToolCall 追加；
              若拆分后仍无法解析，则降级为携带错误说明的占位参数，保证不中断整个响应
              （携带 __reflexion_parse_error/__reflexion_raw_arguments 便于上层感知并提示模型重试）
        返回: 组装完成的 LLMToolCall 列表
        """
        tool_calls = []
        next_idx = max(current_tool_calls.keys()) + 1 if current_tool_calls else 0

        for idx in sorted(current_tool_calls.keys()):
            tc_data = current_tool_calls[idx]
            raw_args = tc_data["arguments"]

            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                fragments = self._split_concatenated_json(raw_args)
                if len(fragments) > 1:
                    parsed = []
                    for frag in fragments:
                        try:
                            parsed.append(json.loads(frag))
                        except json.JSONDecodeError:
                            parsed.append(None)

                    if parsed[0] is not None:
                        args = parsed[0]
                        for extra_idx, extra_args in enumerate(parsed[1:], start=1):
                            if extra_args is not None:
                                tool_calls.append(
                                    LLMToolCall(
                                        id=tc_data["id"] or f"call_{next_idx}",
                                        name=tc_data["name"],
                                        arguments=extra_args,
                                    )
                                )
                                next_idx += 1
                    else:
                        raw_fragment = raw_args[:200] if raw_args else ""
                        logger.warning(
                            "Streaming tool arguments JSON parse failed for tool=%s, raw fragment: %s",
                            tc_data["name"], raw_fragment,
                        )
                        args = {
                            "__reflexion_parse_error": "Tool arguments JSON parse failed — the model output was malformed. "
                                            "Please retry the tool call with valid parameters.",
                            "__reflexion_raw_arguments": raw_fragment,
                        }
                else:
                    raw_fragment = raw_args[:200] if raw_args else ""
                    logger.warning(
                        "Streaming tool arguments JSON parse failed for tool=%s, raw fragment: %s",
                        tc_data["name"], raw_fragment,
                    )
                    args = {
                        "__reflexion_parse_error": "Tool arguments JSON parse failed — the model output was malformed. "
                                        "Please retry the tool call with valid parameters.",
                        "__reflexion_raw_arguments": raw_fragment,
                    }

            tool_calls.append(
                LLMToolCall(
                    id=tc_data["id"] or f"call_{idx}",
                    name=tc_data["name"],
                    arguments=args,
                )
            )
        return tool_calls

    def _parse_response(self, response) -> LLMResponse:
        """解析非流式 OpenAI 响应为内部统一的 LLMResponse

        输入: response - OpenAI SDK 返回的 ChatCompletion 响应对象
        逻辑: 取第一个 choice；解析结构化 tool_calls（参数 JSON 解析失败时降级为
              携带错误说明的占位参数，不中断整体响应，见内联日志）；提取正文与推理内容
              （字段名不统一，见 _extract_reasoning_message）；若没有结构化 tool_calls
              但正文含 DSML 标记，则走文本解析补充工具调用并清理正文；
              最终按是否有 tool_calls 修正 finish_reason，并对"空响应"场景打日志辅助排查
        返回: 组装完成的 LLMResponse（含 usage token 用量）
        """
        choice = response.choices[0]
        message = choice.message

        # 解析 tool_calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    raw_fragment = tc.function.arguments[:200] if tc.function.arguments else ""
                    logger.warning(
                        "Non-streaming tool arguments JSON parse failed for tool=%s, raw fragment: %s",
                        tc.function.name, raw_fragment,
                    )
                    args = {
                        "_parse_error": "Tool arguments JSON parse failed — the model output was malformed. "
                                        "Please retry the tool call with valid parameters.",
                        "_raw_arguments": raw_fragment,
                    }

                tool_calls.append(LLMToolCall(id=tc.id, name=tc.function.name, arguments=args))

        content = message.content or ""
        reasoning_content = self._extract_reasoning_message(message)

        # 无结构化 tool_calls 时，检查文本中的 DSML 工具调用
        if not tool_calls and content and contains_dsml(content):
            result = parse_dsml_tool_calls(content)
            if result.tool_calls:
                tool_calls = result.tool_calls
                content = result.clean_content

        # 确定 finish_reason
        finish_reason = choice.finish_reason or "stop"
        if tool_calls:
            finish_reason = "tool_calls"

        if not content and not tool_calls:
            logger.warning(
                "OpenAI 返回空响应, model=%s, finish_reason=%s, message_role=%s, "
                "可能是: 1) 模型不支持工具调用但被强制使用 2) max_tokens 不足 3) 代理服务异常",
                response.model,
                choice.finish_reason,
                message.role,
            )
            if choice.finish_reason == "length":
                logger.warning(
                    "finish_reason=length: 模型输出被截断，建议增大 max_tokens (当前: %s)",
                    self.config.max_tokens,
                )

        return LLMResponse(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            if response.usage
            else {},
        )

    @staticmethod
    def _extract_reasoning_delta(delta: Any) -> str:
        """从流式 delta 中提取推理/思维链内容片段

        输入: delta - chunk.choices[0].delta 对象
        逻辑: 不同服务商对推理内容字段命名不一致，依次尝试 reasoning_content/
              reason_content/reasoning 三个候选属性名，取第一个非空结果
              （具体取值/多种数据形态的归一化见 _coerce_reasoning_text）
        返回: 推理内容文本片段；均不存在时返回空字符串
        """
        for attr in ("reasoning_content", "reason_content", "reasoning"):
            value = getattr(delta, attr, None)
            text = OpenAIAdapter._coerce_reasoning_text(value)
            if text:
                return text
        return ""

    @staticmethod
    def _extract_reasoning_message(message: Any) -> str:
        """从非流式响应的 message 对象中提取完整推理/思维链内容

        输入: message - response.choices[0].message 对象
        逻辑: 与 _extract_reasoning_delta 相同的候选字段名兜底策略，
              只是作用对象是完整 message 而非流式 delta
        返回: 推理内容文本；均不存在时返回空字符串
        """
        for attr in ("reasoning_content", "reason_content", "reasoning"):
            value = getattr(message, attr, None)
            text = OpenAIAdapter._coerce_reasoning_text(value)
            if text:
                return text
        return ""

    @staticmethod
    def _coerce_reasoning_text(value: Any) -> str:
        """将推理内容字段的原始取值统一转换为纯文本

        输入: value - 推理字段的原始值，可能是字符串，也可能是结构化列表
              （不同服务商返回形态不一致，如 [{"text": "..."}] 或 [{"content": "..."}]）
        逻辑: 字符串直接返回；列表则逐项尝试取字符串本身、或 .text 属性、
              或 .content 属性，拼接所有能取到的文本片段
        返回: 拼接后的纯文本；无法识别的类型返回空字符串
        """
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
                    continue
                content = getattr(item, "content", None)
                if isinstance(content, str):
                    parts.append(content)
            return "".join(parts)
        return ""
