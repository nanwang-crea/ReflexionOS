"""
文件功能：沙箱工厂配置覆盖（sandbox.provider）的单元测试
文件描述：验证 create_sandbox 对 config.json 中 sandbox.provider 各取值的
         行为——auto 自动探测（历史行为不回归）、null 强制无沙箱、
         指定后端可用时返回该后端、指定后端不可用时降级 NullSandbox
         并打 warning。配置读取点与后端可用性均用 monkeypatch 控制，
         不触碰真实 config.json 与平台沙箱。
"""

import logging

import pytest

from app.security.sandbox import factory
from app.security.sandbox.factory import NullSandbox, create_sandbox


@pytest.fixture
def set_provider(monkeypatch):
    """把工厂的 _configured_provider 钉为指定返回值的便捷 fixture。

    用法：set_provider("null") 后调用 create_sandbox 即视为配置为该值。
    """

    def _set(value: str) -> None:
        """钉住配置读取点。入参：value（模拟的 provider 配置值）。出参：无。"""
        monkeypatch.setattr(factory, "_configured_provider", lambda: value)

    return _set


@pytest.fixture
def app_log_propagates(monkeypatch):
    """强制 "app" logger 在本用例期间向 root 传播（收尾自动还原）。

    背景：应用日志初始化（app/config/logging_config.py）会把 "app" logger
    的 propagate 置为 False。全量联跑时若此前已有用例触发过日志初始化，
    caplog（handler 挂在 root）将收不到任何 app.* 的日志记录，导致告警
    断言假阴性；单跑本文件时 propagate 默认 True，故单跑能过。
    """
    monkeypatch.setattr(logging.getLogger("app"), "propagate", True)


@pytest.fixture
def all_backends_unavailable(monkeypatch):
    """把三个真实后端的 is_available 全部钉为 False。

    入参：monkeypatch。出参：无。
    """
    for cls in (
        factory.WindowsSandbox,
        factory.SeatbeltSandbox,
        factory.LandlockSandbox,
    ):
        monkeypatch.setattr(cls, "is_available", lambda self: False)


class TestAutoMode:
    """auto（默认）：自动探测行为不回归"""

    def test_auto_falls_back_to_null_when_nothing_available(
        self, set_provider, all_backends_unavailable
    ):
        """auto + 全后端不可用 → 兜底 NullSandbox。

        入参：set_provider / all_backends_unavailable fixtures。出参：无。
        """
        set_provider("auto")

        assert isinstance(create_sandbox(), NullSandbox)

    def test_auto_picks_first_available(self, set_provider, monkeypatch):
        """auto + Seatbelt 可用（macOS 场景模拟）→ 返回 SeatbeltSandbox。

        入参：fixtures。出参：无。
        """
        set_provider("auto")
        monkeypatch.setattr(
            factory.WindowsSandbox, "is_available", lambda self: False
        )
        monkeypatch.setattr(
            factory.SeatbeltSandbox, "is_available", lambda self: True
        )

        assert isinstance(create_sandbox(), factory.SeatbeltSandbox)


class TestNullOverride:
    """provider="null"：强制无沙箱"""

    def test_null_forces_null_sandbox_even_when_backend_available(
        self, set_provider, monkeypatch
    ):
        """即使某后端可用，"null" 也强制返回 NullSandbox。

        入参：fixtures。出参：无。
        """
        set_provider("null")
        monkeypatch.setattr(
            factory.WindowsSandbox, "is_available", lambda self: True
        )

        assert isinstance(create_sandbox(), NullSandbox)


class TestNamedBackendOverride:
    """指定后端：可用返回该后端，不可用降级 + warning"""

    def test_named_backend_returned_when_available(
        self, set_provider, monkeypatch
    ):
        """provider="landlock" 且 Landlock 可用 → 返回 LandlockSandbox 实例。

        入参：fixtures。出参：无。
        """
        set_provider("landlock")
        monkeypatch.setattr(
            factory.LandlockSandbox, "is_available", lambda self: True
        )

        assert isinstance(create_sandbox(), factory.LandlockSandbox)

    def test_named_backend_unavailable_falls_back_with_warning(
        self, set_provider, all_backends_unavailable, app_log_propagates,
        monkeypatch, caplog
    ):
        """provider="seatbelt" 但不可用 → NullSandbox + warning 日志
        （不静默换用其他可用后端）。

        入参：fixtures + monkeypatch + caplog。出参：无。
        """
        set_provider("seatbelt")
        # Windows 后端"可用"——若工厂静默换后端就会选它，断言必须仍是 Null
        monkeypatch.setattr(
            factory.WindowsSandbox, "is_available", lambda self: True
        )

        # logger 指定为 "app"：确保即使应用日志初始化改过该 logger 的
        # 级别，本用例期间也能放行 WARNING
        with caplog.at_level(logging.WARNING, logger="app"):
            provider = create_sandbox()

        assert isinstance(provider, NullSandbox)
        assert any(
            "seatbelt" in r.getMessage() and "不可用" in r.getMessage()
            for r in caplog.records
        )

    def test_named_backend_init_exception_falls_back(
        self, set_provider, app_log_propagates, monkeypatch, caplog
    ):
        """指定后端构造即抛异常 → 视同不可用，降级 NullSandbox。

        入参：fixtures + caplog。出参：无。
        """
        set_provider("windows")

        class _ExplodingWindows(factory.WindowsSandbox):
            """构造即抛异常的替身后端（模拟初始化失败）。"""

            def __init__(self, **kwargs):
                """直接抛错。入参：kwargs（不消费）。出参：无。"""
                raise RuntimeError("init boom")

        monkeypatch.setitem(factory._NAMED_BACKENDS, "windows", _ExplodingWindows)

        with caplog.at_level(logging.WARNING, logger="app"):
            provider = create_sandbox()

        assert isinstance(provider, NullSandbox)
        assert any("初始化失败" in r.getMessage() for r in caplog.records)


class TestConfigReadFailure:
    """配置读取失败：按 auto 处理"""

    def test_config_read_exception_treated_as_auto(
        self, monkeypatch, all_backends_unavailable
    ):
        """_configured_provider 自身抛异常时……注意：真实实现内部已 try/except
        返回 "auto"，此处直接验证真实函数在 config_manager 不可用时返回 "auto"。

        入参：fixtures。出参：无。
        """
        import sys

        # 模拟 config 模块导入失败
        monkeypatch.setitem(sys.modules, "app.config.settings", None)

        assert factory._configured_provider() == "auto"
        assert isinstance(create_sandbox(), NullSandbox)
