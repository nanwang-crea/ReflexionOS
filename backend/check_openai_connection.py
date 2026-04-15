import asyncio

from app.config import settings
from app.llm.base import Message
from app.llm.openai_adapter import OpenAIAdapter
from app.models.llm_config import LLMConfig, LLMProvider


async def main() -> None:
    if not settings.llm_api_key:
        raise SystemExit("未检测到 LLM_API_KEY，请先在 backend/.env 中配置真实 API Key。")

    config = LLMConfig(
        provider=LLMProvider.OPENAI,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.3,
        max_tokens=64,
    )

    adapter = OpenAIAdapter(config)
    messages = [
        Message(
            role="user",
            content="你好，介绍一下你自己",
        )
    ]

    response = await adapter.complete(messages)

    print("LLM 连接成功")
    print(f"provider: {config.provider}")
    print(f"model: {response.model}")
    print(f"content: {response.content!r}")
    if not response.content.strip():
        print("note: 模型已连接成功，但本次返回的文本内容为空。")
    print(f"usage: {response.usage}")


if __name__ == "__main__":
    asyncio.run(main())
