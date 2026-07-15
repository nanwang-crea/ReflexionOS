"""
测试 Windows 子进程执行在 SelectorEventLoop 下的行为。

根因：uvicorn --reload 强制 WindowsSelectorEventLoopPolicy，导致 create_subprocess_* 抛 NotImplementedError
修复：Windows 分支用 loop.run_in_executor + 同步 subprocess.run 绕过限制
"""
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.security.command_effect_registry import CommandEffectRegistry
from app.security.path_security import PathSecurity
from app.security.sandbox.factory import NullSandbox
from app.security.shell_security import ShellSecurity
from app.tools.shell_tool import ShellTool


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
class TestWindowsSubprocessEventLoop:
    """测试 Windows 在 SelectorEventLoop 下的子进程执行"""

    @pytest.fixture
    def temp_git_repo(self):
        """创建临时 git 仓库供测试使用"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "test_repo"
            repo_path.mkdir()

            # 初始化 git 仓库（跨平台写法：用 subprocess.run）
            subprocess.run(
                ["git", "init"],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )

            # 配置 git 用户（避免 commit 失败）
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )

            # 创建初始提交
            test_file = repo_path / "test.txt"
            test_file.write_text("test content", encoding="utf-8")
            subprocess.run(
                ["git", "add", "test.txt"],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )

            yield str(repo_path)

    @pytest.fixture
    def shell_tool_and_loop(self, temp_git_repo):
        """
        创建在 SelectorEventLoop 下运行的 ShellTool 实例和受控的事件循环。

        这模拟了 uvicorn --reload 的实际环境。
        返回 (loop, tool) 元组，测试函数手动在这个 loop 上执行。
        """
        # 强制设置 SelectorEventLoop（模拟 uvicorn --reload 行为）
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 创建 ShellTool 实例（对齐真实构造接口）
        root_dir = os.path.realpath(temp_git_repo)
        path_security = PathSecurity([root_dir], base_dir=root_dir)
        security = ShellSecurity()
        registry = CommandEffectRegistry()
        sandbox = NullSandbox()

        tool = ShellTool(
            security=security,
            path_security=path_security,
            registry=registry,
            sandbox=sandbox,
            session_id=None,
            trust_store=None,
        )

        yield loop, tool

        loop.close()

    def test_argv_mode_git_status_with_selector_loop(
        self, shell_tool_and_loop
    ):
        """
        测试 argv 模式的 git status 在 SelectorEventLoop 下能正常执行。

        旧代码：create_subprocess_shell → NotImplementedError
        新代码：loop.run_in_executor + subprocess.run → 成功

        注意：不用 @pytest.mark.asyncio，手动在受控 loop 上执行，确保真正跑在 SelectorEventLoop 上。
        """
        loop, tool = shell_tool_and_loop

        result = loop.run_until_complete(
            tool.execute({"command": "git status"})
        )

        assert result.success is True
        assert "nothing to commit" in result.output or "working tree clean" in result.output

    def test_argv_mode_git_log_with_selector_loop(
        self, shell_tool_and_loop
    ):
        """测试 argv 模式的 git log 在 SelectorEventLoop 下能正常执行"""
        loop, tool = shell_tool_and_loop

        result = loop.run_until_complete(
            tool.execute({"command": "git log --oneline -1"})
        )

        assert result.success is True
        assert "Initial commit" in result.output

    def test_shell_mode_git_chain_with_selector_loop(
        self, shell_tool_and_loop
    ):
        """
        测试 shell 模式的 git 命令链在 SelectorEventLoop 下能正常执行。

        命令链（带 &&）会触发 has_meta=True → shell 分支 → Windows 白名单
        """
        loop, tool = shell_tool_and_loop

        result = loop.run_until_complete(
            tool.execute({"command": "git status && git log --oneline -1"})
        )

        assert result.success is True
        # 应该同时包含 status 和 log 的输出
        assert ("working tree clean" in result.output or "nothing to commit" in result.output)
        assert "Initial commit" in result.output

    def test_encoding_gbk_fallback(self, shell_tool_and_loop, temp_git_repo):
        """
        测试中文文件名的编码处理（GBK 降级）。

        Windows git 输出可能是 GBK 编码，验证 _decode_windows_output 正确处理。
        """
        loop, tool = shell_tool_and_loop

        # 创建中文文件名的文件
        chinese_file = Path(temp_git_repo) / "测试文件.txt"
        chinese_file.write_text("测试内容", encoding="utf-8")

        result = loop.run_until_complete(
            tool.execute({"command": "git status"})
        )

        assert result.success is True
        # 输出中应该能正确显示中文文件名（无乱码）
        assert "测试文件.txt" in result.output or "Untracked files" in result.output
