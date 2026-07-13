# SandboxProvider 可选方法（run_command/run_shell_command）与 SandboxRunResult 单测
from app.security.sandbox.base import SandboxProvider, SandboxRunResult


def test_run_command_default_none():
    provider = _ConcreteProvider()
    assert provider.run_command(["echo", "hi"], cwd="/tmp") is None


def test_run_shell_command_default_none():
    provider = _ConcreteProvider()
    assert provider.run_shell_command("echo hi", cwd="/tmp") is None


def test_abstract_methods_still_required():
    provider = _ConcreteProvider()
    assert provider.wrap_command(["echo", "hi"], cwd="/tmp") == ["echo", "hi"]
    assert provider.wrap_shell_command("echo hi", cwd="/tmp") == "echo hi"


def test_sandbox_run_result_fields():
    result = SandboxRunResult(success=True, output="hello", error=None, return_code=0)
    assert result.success is True
    assert result.output == "hello"
    assert result.return_code == 0


class _ConcreteProvider(SandboxProvider):
    def is_available(self) -> bool:
        return True

    def wrap_command(self, argv, *, cwd, **kw):
        return list(argv)

    def wrap_shell_command(self, command, *, cwd, **kw):
        return command
