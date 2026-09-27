# 文件功能：测试 LLMProviderService.list_remote_models —— 拉取远端 API 站点可用模型列表
# 文件描述：覆盖正常拉取、非 OpenAI 兼容供应商拒绝、网络异常向上抛出三种场景。
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.llm_config import ProviderInstanceConfig, ProviderType
from app.services.llm_provider_service import LLMProviderService


def _make_provider(provider_type: ProviderType = ProviderType.OPENAI_COMPATIBLE) -> ProviderInstanceConfig:
    """构造测试用 OpenAI 兼容供应商草稿（含 base_url + api_key，无 models）。"""
    return ProviderInstanceConfig(
        id="provider-test",
        name="测试供应商",
        provider_type=provider_type,
        api_key="sk-test-key",
        base_url="https://example.com/v1",
        models=[],
        default_model_id=None,
        enabled=True,
    )


class TestListRemoteModels:
    """list_remote_models 行为测试"""

    @pytest.fixture
    def service(self):
        # 直接 new 一个 service，避免依赖磁盘配置
        with patch.object(LLMProviderService, "_load_llm_settings", return_value=MagicMock()):
            return LLMProviderService()

    @pytest.mark.asyncio
    async def test_returns_models_from_remote_endpoint(self, service):
        """正常拉取：mock client.models.list() 返回固定列表，断言正确提取 id/owned_by"""
        fake_models = [
            MagicMock(id="glm-4-flash", owned_by="zhipu"),
            MagicMock(id="glm-4-plus", owned_by="zhipu"),
            MagicMock(id="kimi-k3", owned_by="moonshot"),
        ]
        fake_page = MagicMock(data=fake_models)
        fake_client = MagicMock()
        fake_client.models.list = AsyncMock(return_value=fake_page)

        with patch.object(service, "_build_openai_client", return_value=fake_client):
            result = await service.list_remote_models(_make_provider())

        assert result.provider_id == "provider-test"
        assert len(result.models) == 3
        assert result.models[0].id == "glm-4-flash"
        assert result.models[0].owned_by == "zhipu"
        assert result.models[2].id == "kimi-k3"
        assert result.message == "获取成功"

    @pytest.mark.asyncio
    async def test_rejects_non_openai_compatible_provider(self, service):
        """非 OpenAI 兼容供应商（如 anthropic）应抛 ValueError"""
        provider = _make_provider(provider_type=ProviderType.ANTHROPIC)
        with pytest.raises(ValueError, match="OpenAI-compatible"):
            await service.list_remote_models(provider)

    @pytest.mark.asyncio
    async def test_owns_by_defaults_to_none_when_missing(self, service):
        """远端模型对象没有 owned_by 属性时，应归一化为 None 而非报错"""
        # SimpleNamespace 没有 owned_by 属性，触发 getattr 默认值路径
        from types import SimpleNamespace
        fake_page = MagicMock(data=[SimpleNamespace(id="model-x")])
        fake_client = MagicMock()
        fake_client.models.list = AsyncMock(return_value=fake_page)

        with patch.object(service, "_build_openai_client", return_value=fake_client):
            result = await service.list_remote_models(_make_provider())

        assert len(result.models) == 1
        assert result.models[0].id == "model-x"
        assert result.models[0].owned_by is None

    @pytest.mark.asyncio
    async def test_network_error_propagates(self, service):
        """网络/鉴权异常应向上抛出（由路由层兜底转 ValidationError）"""
        fake_client = MagicMock()
        fake_client.models.list = AsyncMock(side_effect=RuntimeError("connection refused"))

        with patch.object(service, "_build_openai_client", return_value=fake_client):
            with pytest.raises(RuntimeError, match="connection refused"):
                await service.list_remote_models(_make_provider())
