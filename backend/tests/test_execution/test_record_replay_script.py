"""
文件功能：夹具录制脚本（record_replay_fixture.py）的降级路径测试
文件描述：验证 C-03——无可用 LLM 配置 / 缺 API key 时，脚本以退出码 2 明确
         报错退出，且不产生半成品夹具文件。脚本模块按文件路径动态加载，
         避免对 backend/scripts 目录结构做包化假设。
"""

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = BACKEND_ROOT / "scripts" / "record_replay_fixture.py"


def _load_script_module():
    """按文件路径动态加载录制脚本模块（每次调用返回新模块对象）。

    入参：无。
    出参：module - 加载完成的 record_replay_fixture 模块。
    """
    # backend 根目录需在 sys.path 中，脚本内部的 app.* / tests.* 导入才能解析
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    spec = importlib.util.spec_from_file_location("record_replay_fixture", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(tmp_path) -> Namespace:
    """构造录制脚本的命令行参数命名空间（输出指向临时目录）。

    入参：tmp_path - pytest 临时目录。
    出参：Namespace - 与 parse_args 产出同构的参数对象。
    """
    return Namespace(
        scenario="degradation-test",
        task="任意任务",
        max_steps=10,
        output=str(tmp_path / "should-not-exist.json"),
    )


class TestRecordScriptDegradation:
    """C-03：无 key / 无配置时退出码 2，且不产生夹具文件"""

    @pytest.mark.asyncio
    async def test_unresolvable_config_exits_2(self, tmp_path, capsys):
        """resolve_llm_config 抛 ValueError（未配置默认供应商）时退出码 2。

        入参：tmp_path（检查不产出文件）、capsys（检查提示文案）。
        出参：无。
        """
        module = _load_script_module()
        args = _args(tmp_path)

        with patch.object(
            module.LLMProviderService,
            "resolve_llm_config",
            side_effect=ValueError("未配置默认供应商"),
        ):
            exit_code = await module.record(args)

        assert exit_code == 2
        assert "配置" in capsys.readouterr().out
        assert not (tmp_path / "should-not-exist.json").exists()

    @pytest.mark.asyncio
    async def test_missing_api_key_exits_2(self, tmp_path, capsys):
        """配置可解析但 api_key 为空时退出码 2，且不产出夹具。

        入参：tmp_path、capsys。出参：无。
        """
        module = _load_script_module()
        args = _args(tmp_path)

        fake_resolved = Namespace(api_key=None)
        with patch.object(
            module.LLMProviderService,
            "resolve_llm_config",
            return_value=fake_resolved,
        ):
            exit_code = await module.record(args)

        assert exit_code == 2
        assert "API key" in capsys.readouterr().out
        assert not (tmp_path / "should-not-exist.json").exists()
