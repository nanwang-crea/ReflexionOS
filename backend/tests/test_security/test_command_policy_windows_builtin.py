# Windows builtin 命令分类 + runas 注册单测
from app.security.command_effect_registry import CommandEffectRegistry
from app.security.effect_category import EffectCategory


def test_cd_is_read_only():
    """cd 应被识别为 READ_ONLY"""
    registry = CommandEffectRegistry()
    entry = registry.lookup("cd")
    assert entry is not None
    assert entry.category == EffectCategory.READ_ONLY


def test_dir_is_read_only():
    registry = CommandEffectRegistry()
    entry = registry.lookup("dir")
    assert entry is not None
    assert entry.category == EffectCategory.READ_ONLY


def test_copy_is_write_project():
    registry = CommandEffectRegistry()
    entry = registry.lookup("copy")
    assert entry is not None
    assert entry.category == EffectCategory.WRITE_PROJECT


def test_rmdir_is_destructive():
    registry = CommandEffectRegistry()
    entry = registry.lookup("rmdir")
    assert entry is not None
    assert entry.category == EffectCategory.DESTRUCTIVE


def test_runas_is_escalate():
    """runas 必须为 ESCALATE → 任何模式下 DENY"""
    registry = CommandEffectRegistry()
    entry = registry.lookup("runas")
    assert entry is not None
    assert entry.category == EffectCategory.ESCALATE


def test_chdir_alias():
    """chdir 是 cd 的别名，也应为 READ_ONLY"""
    registry = CommandEffectRegistry()
    entry = registry.lookup("chdir")
    assert entry is not None
    assert entry.category == EffectCategory.READ_ONLY


def test_md_alias():
    """md 是 mkdir 的别名，应为 WRITE_PROJECT"""
    registry = CommandEffectRegistry()
    entry = registry.lookup("md")
    assert entry is not None
    assert entry.category == EffectCategory.WRITE_PROJECT


def test_echo_already_registered():
    """echo 已注册，不应重复注册但不应丢失"""
    registry = CommandEffectRegistry()
    entry = registry.lookup("echo")
    assert entry is not None
    assert entry.category == EffectCategory.READ_ONLY
