from fastapi import APIRouter
from app.models.llm_config import LLMConfig, LLMProvider
from app.services.agent_service import agent_service

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/config")
async def get_llm_config():
    """获取 LLM 配置"""
    config = agent_service.get_llm_config()
    if not config:
        return {"configured": False}
    return {
        "configured": True,
        "provider": config.provider.value,
        "model": config.model,
        "base_url": config.base_url
    }


@router.post("/config")
async def set_llm_config(config: LLMConfig):
    """设置 LLM 配置"""
    agent_service.set_llm_config(config)
    return {"message": "配置已保存"}


@router.get("/providers")
async def list_providers():
    """获取支持的 LLM 提供商"""
    return [
        {
            "id": LLMProvider.OPENAI.value,
            "name": "OpenAI",
            "models": ["gpt-4-turbo-preview", "gpt-4", "gpt-3.5-turbo"]
        },
        {
            "id": LLMProvider.CLAUDE.value,
            "name": "Claude",
            "models": ["claude-3-opus", "claude-3-sonnet"],
            "status": "coming_soon"
        },
        {
            "id": LLMProvider.OLLAMA.value,
            "name": "Ollama",
            "models": ["llama2", "codellama"],
            "status": "coming_soon"
        }
    ]
