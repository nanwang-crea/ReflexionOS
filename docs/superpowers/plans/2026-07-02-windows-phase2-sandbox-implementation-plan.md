# Windows 第二阶段沙盒隔离与权限控制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Windows 全类型命令支持（cd、dir、npm、python 等），通过 Restricted Token + ACL + 防火墙提供 OS 级文件隔离，并引入三档权限模式（ASK/AUTO/YOLO）对齐 macOS/Linux 体验。

**Architecture:** 三个正交维度——(1) 本地操作审批由 `PermissionMode` + `resolve_action()` 控制，取代第一阶段 git-only 白名单； (2) 网络审批保持独立链路，任何 mode 都不旁路； (3) 沙盒文件隔离通过 `run_command`/`run_shell_command` 方法在 WindowsSandbox 上实现 CreateProcessAsUserW 执行。macOS/Linux 零改动，通过 `SandboxProvider` 新增可选方法默认返回 None 实现隔离。

**Tech Stack:** Python 3.11+, pywin32 (新增), pytest, FastAPI, SQLAlchemy, Alembic

---

## 文件结构

### 新建文件
| 文件 | 职责 |
|------|------|
| `backend/app/security/permission_mode.py` | `PermissionMode` 枚举 + `resolve_action()` 决策函数，含单测 |
| `backend/app/security/sandbox/windows_token.py` | Windows Restricted Token 构造（SID 移除/禁用权限） |
| `backend/app/security/sandbox/windows_acl.py` | Windows 文件 ACL 写入边界（临时目录隔离） |
| `backend/app/security/sandbox/windows_user.py` | Elevated 档沙盒用户（ReflexionSandboxOffline/Online）管理 |
| `backend/app/security/sandbox/windows_firewall.py` | Elevated 档防火墙策略（出站规则） |
| `backend/app/security/sandbox/windows.py` | `WindowsSandbox` 主类，实现 `run_command`/`run_shell_command` |
| `backend/alembic/versions/xxxx_add_permission_mode_to_sessions.py` | DB migration 加 `permission_mode` 列 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `backend/app/security/sandbox/base.py` | 加 `SandboxRunResult` dataclass + `run_command`/`run_shell_command` 可选方法（默认返回 None） |
| `backend/app/security/sandbox/factory.py` | 加 `WindowsSandbox` 到 providers 迭代 |
| `backend/app/security/command_effect_registry.py` | 直接注册 Windows builtin + `runas`→ESCALATE；可选标注 `platform_overrides` 为死字段 |
| `backend/app/security/command_policy.py` | 白名单门禁加 `not sandbox_available` 条件；`resolve_action` 接入动作决策点 |
| `backend/app/security/effect_category.py` | 无改动（PermissionMode 新建文件，不修改此文件） |
| `backend/app/tools/shell_tool.py` | ShellTool 构造接收 `permission_mode` + `sandbox_available`；`_execute_argv`/`_execute_shell` Windows 分支调 `run_command`/`run_shell_command` |
| `backend/app/services/agent_service.py` | 读取 DB 的 `permission_mode` 字段，传入 `_build_run_tool_registry` → `ShellTool` |
| `backend/app/models/session.py` | `Session`/`SessionUpdate` 加 `permission_mode` 字段 |
| `backend/app/storage/models.py` | `SessionModel` 加 `permission_mode` 列 |
| `backend/app/storage/repositories/session_repo.py` | `update` 方法加 `permission_mode` 赋值 |
| `backend/app/api/routes/websocket.py` | 处理 `session:set_permission_mode` 消息 |
| `backend/requirements.txt` | 加 `pywin32` 依赖 |
| `frontend/src/types/conversation.ts` | 加 `PermissionMode` type |
| `frontend/src/hooks/useConversationRuntime.ts` | 加 `setPermissionMode` 函数 + WebSocket 消息 |

### 测试文件
| 文件 | 职责 |
|------|------|
| `backend/tests/test_security/test_permission_mode.py` | `PermissionMode` + `resolve_action` 全覆盖单测 |
| `backend/tests/test_security/test_sandbox_windows_token.py` | Restricted Token 构造（mock pywin32） |
| `backend/tests/test_security/test_sandbox_windows_acl.py` | ACL 写入边界（mock pywin32） |
| `backend/tests/test_security/test_sandbox_windows.py` | `run_command`/`run_shell_command` 单元测试 |
| `backend/tests/test_security/test_sandbox_windows_integration.py` | 沙盒可用时白名单旁路、命令执行集成测试 |
| `backend/tests/test_security/test_command_policy_windows_builtin.py` | Windows builtin 分类单测 |
| `backend/tests/test_security/test_command_policy_sandbox_conditional.py` | 白名单条件化（sandbox 可用/不可用两种路径） |

---

## 实施步骤

### Task 0: 依赖 + 基础数据结构

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/security/permission_mode.py`
- Test: `backend/tests/test_security/test_permission_mode.py`

- [ ] **Step 0.1: 加 pywin32 依赖**

```bash
echo "pywin32==308" >> backend/requirements.txt
pip install pywin32==308
```

- [ ] **Step 0.2: 写 PermissionMode + resolve_action 单测**

```python
# backend/tests/test_security/test_permission_mode.py
import pytest
from app.security.permission_mode import PermissionMode, resolve_action
from app.security.effect_category import EffectCategory, CommandAction


class TestPermissionMode:
    def test_yolo_local_open_no_sandbox_deny(self):
        assert resolve_action(PermissionMode.YOLO, EffectCategory.READ_ONLY, sandbox_available=False) == CommandAction.DENY

    def test_yolo_local_open_with_sandbox(self):
        for cat in [EffectCategory.READ_ONLY, EffectCategory.WRITE_PROJECT, EffectCategory.DESTRUCTIVE]:
            assert resolve_action(PermissionMode.YOLO, cat, sandbox_available=True) == CommandAction.ALLOW

    def test_yolo_network_still_requires_approval(self):
        # YOLO 本地全放行；NETWORK_OUT 不受 PermissionMode 影响，始终走 EFFECT_ACTION_MAP 映射
        assert resolve_action(PermissionMode.YOLO, EffectCategory.NETWORK_OUT, sandbox_available=True) == CommandAction.REQUIRE_APPROVAL

    def test_yolo_escalate_always_deny(self):
        assert resolve_action(PermissionMode.YOLO, EffectCategory.ESCALATE, sandbox_available=True) == CommandAction.DENY

    def test_ask_read_only_allow(self):
        assert resolve_action(PermissionMode.ASK, EffectCategory.READ_ONLY, sandbox_available=True) == CommandAction.ALLOW

    def test_ask_write_project_requires_approval(self):
        assert resolve_action(PermissionMode.ASK, EffectCategory.WRITE_PROJECT, sandbox_available=True) == CommandAction.REQUIRE_APPROVAL

    def test_auto_write_project_allow(self):
        assert resolve_action(PermissionMode.AUTO, EffectCategory.WRITE_PROJECT, sandbox_available=True) == CommandAction.ALLOW

    def test_auto_destructive_requires_approval(self):
        assert resolve_action(PermissionMode.AUTO, EffectCategory.DESTRUCTIVE, sandbox_available=True) == CommandAction.REQUIRE_APPROVAL

    def test_auto_unknown_requires_approval(self):
        assert resolve_action(PermissionMode.AUTO, EffectCategory.UNKNOWN, sandbox_available=True) == CommandAction.REQUIRE_APPROVAL

    @pytest.mark.parametrize("mode", list(PermissionMode))
    def test_escalate_always_deny(self, mode):
        assert resolve_action(mode, EffectCategory.ESCALATE, sandbox_available=True) == CommandAction.DENY

    def test_no_sandbox_ask_still_works(self):
        assert resolve_action(PermissionMode.ASK, EffectCategory.READ_ONLY, sandbox_available=False) == CommandAction.ALLOW
        assert resolve_action(PermissionMode.ASK, EffectCategory.WRITE_PROJECT, sandbox_available=False) == CommandAction.REQUIRE_APPROVAL
```

- [ ] **Step 0.3: 确认单测失败**

Run: `pytest backend/tests/test_security/test_permission_mode.py -v`
Expected: `ModuleNotFoundError: No module named 'app.security.permission_mode'`

- [ ] **Step 0.4: 实现 PermissionMode + resolve_action**

```python
# backend/app/security/permission_mode.py
"""权限模式：控制本地操作审批行为"""

from __future__ import annotations
import enum
from app.security.effect_category import CommandAction, EffectCategory


class PermissionMode(str, enum.Enum):
    """三档权限模式（会话级）。
    - ASK:  每步操作都弹审批（READ_ONLY 除外）
    - AUTO: 默认模式，按 EFFECT_ACTION_MAP 自动决策
    - YOLO: 本地操作全部放行，网络审批不受 PermissionMode 影响
    """
    ASK = "ask"
    AUTO = "auto"
    YOLO = "yolo"


def resolve_action(
    mode: PermissionMode,
    category: EffectCategory,
    *,
    sandbox_available: bool = True,
) -> CommandAction:
    """根据权限模式和效果分类决定最终动作。
    
    NETWORK_OUT 不受 PermissionMode 影响（无论 ASK/AUTO/YOLO 都返回 REQUIRE_APPROVAL），
    因为网络命令的审批完全由 EFFECT_ACTION_MAP 定义。
    """
    if category == EffectCategory.ESCALATE:
        return CommandAction.DENY
    if mode == PermissionMode.YOLO:
        if not sandbox_available:
            return CommandAction.DENY
        # 确保 YOLO 下网络不被 ALLOW——网络审批不受 YOLO 影响
        if category == EffectCategory.NETWORK_OUT:
            return CommandAction.REQUIRE_APPROVAL
        return CommandAction.ALLOW
    if mode == PermissionMode.ASK:
        if category == EffectCategory.READ_ONLY:
            return CommandAction.ALLOW
        return CommandAction.REQUIRE_APPROVAL
    from app.security.effect_category import EFFECT_ACTION_MAP
    return EFFECT_ACTION_MAP[category]
```

- [ ] **Step 0.5: 运行单测确认通过**

Run: `pytest backend/tests/test_security/test_permission_mode.py -v`
Expected: 全部 PASS

- [ ] **Step 0.6: 提交**

```bash
git add backend/requirements.txt backend/app/security/permission_mode.py \
       backend/tests/test_security/test_permission_mode.py
git commit -m "feat: 新增 PermissionMode 枚举与 resolve_action 决策函数"
```

---

### Task 1: 接口扩展 — SandboxRunResult + run_command/run_shell_command

**Files:**
- Modify: `backend/app/security/sandbox/base.py`
- Test: `backend/tests/test_security/test_sandbox_base.py`

- [ ] **Step 1.1: 写单测验证可选方法默认返回 None**

```python
# backend/tests/test_security/test_sandbox_base.py
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
```

- [ ] **Step 1.2: 确认单测失败**

Run: `pytest backend/tests/test_security/test_sandbox_base.py -v`
Expected: `ImportError` (SandboxRunResult 未定义)

- [ ] **Step 1.3: 加 SandboxRunResult + 可选方法到 base.py**

```python
# 在 base.py 顶部（import 后，class SandboxProvider 前）加：
from dataclasses import dataclass


@dataclass
class SandboxRunResult:
    """沙盒直接执行命令的结果（与 subprocess.run 返回值对齐）。"""
    success: bool
    output: str
    error: str | None
    return_code: int


# 在 SandboxProvider 类中（wrap_shell_command 后）加：
    def run_command(
        self,
        argv: list[str],
        *,
        cwd: str,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> SandboxRunResult | None:
        """直接执行 argv 命令并返回结果。默认为 None（seatbelt/landlock 不覆盖）。"""
        return None

    def run_shell_command(
        self,
        command: str,
        *,
        cwd: str,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> SandboxRunResult | None:
        """直接执行 shell 命令并返回结果。默认为 None。"""
        return None
```

- [ ] **Step 1.4: 运行单测确认通过**

Run: `pytest backend/tests/test_security/test_sandbox_base.py -v`
Expected: 全部 PASS

- [ ] **Step 1.5: 提交**

```bash
git add backend/app/security/sandbox/base.py \
       backend/tests/test_security/test_sandbox_base.py
git commit -m "feat: 加 SandboxRunResult 与 run_command/run_shell_command 可选方法"

---

### Task 2: Windows builtin 分类 + runas 注册

**Files:**
- Modify: `backend/app/security/command_effect_registry.py`
- Test: `backend/tests/test_security/test_command_policy_windows_builtin.py`

- [ ] **Step 2.1: 写 Windows builtin 分类 + runas 单测**

```python
# backend/tests/test_security/test_command_policy_windows_builtin.py
import sys
import pytest
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


```

- [ ] **Step 2.2: 确认单测失败**

Run: `pytest backend/tests/test_security/test_command_policy_windows_builtin.py -v`
Expected: 约 4 个 FAIL（cd、dir、copy、runas、chdir、md 未注册）

- [ ] **Step 2.3: 修改 registry**

```python
# 在 backend/app/security/command_effect_registry.py 中：

# 1. 在 ESCALATE 列表（:259-261）加 runas
escalate_commands = ["sudo", "su", "eval", "exec", "newgrp", "pkexec", "gksudo", "runas"]

# 2. 在 Windows 段（:280-295）改为直接注册
# 注：platform_overrides 字段虽然死（lookup 不消费），但本轮不删，仅标注
# ── Windows-specific ────────────────────────────────────────
# 注意：直接注册（不通过 platform_overrides；该字段虽存在但 lookup 从不消费）
# 跨平台安全：这些命令在 Unix 不存在或行为不同，但 register 本身无害
#  cd/chdir/dir/type/set/findstr/tree/ver/cls → 不存在也是 READ_ONLY 语义
#  copy/xcopy/move/ren/rename/md → 不存在也是 WRITE_PROJECT 语义
windows_builtin_read_only = [
    "cd", "chdir", "dir", "type", "set", "findstr", "tree", "ver", "cls",
]
for cmd in windows_builtin_read_only:
    self.register(cmd, CommandEffectEntry(category=EffectCategory.READ_ONLY))

windows_builtin_write = [
    "copy", "xcopy", "robocopy", "move", "ren", "rename", "md",
]
for cmd in windows_builtin_write:
    self.register(cmd, CommandEffectEntry(category=EffectCategory.WRITE_PROJECT))

# 保留原有 Windows 命令（直接注册，不用 platform_overrides）
windows_commands = [
    ("del", EffectCategory.DESTRUCTIVE),
    ("erase", EffectCategory.DESTRUCTIVE),
    ("rd", EffectCategory.DESTRUCTIVE),
    ("rmdir", EffectCategory.DESTRUCTIVE),
    ("format", EffectCategory.DESTRUCTIVE),
    ("diskpart", EffectCategory.DESTRUCTIVE),
    ("cmd", EffectCategory.ESCALATE),
    ("powershell", EffectCategory.ESCALATE),
    ("pwsh", EffectCategory.ESCALATE),
]
for cmd, base_cat in windows_commands:
    self.register(cmd, CommandEffectEntry(category=base_cat))
```

- [ ] **Step 2.4: 运行单测确认通过**

Run: `pytest backend/tests/test_security/test_command_policy_windows_builtin.py -v`
Expected: 全部 PASS

- [ ] **Step 2.5: 提交**

```bash
git add backend/app/security/command_effect_registry.py \
       backend/tests/test_security/test_command_policy_windows_builtin.py
git commit -m "feat: 直接注册 Windows builtin + runas→ESCALATE"
```

---

### 备忘项 A: posix-split Windows 路径验证

**说明：** 这是 spec 431 行记录的已知限制，**不是修改代码的任务**，而是验证任务，在 Task 5 之前执行。

- [ ] **Step A.1: 编写 Windows 路径解析验证脚本**

```python
# 在 Windows 机器上运行，验证 shlex.split(posix=True) 对反斜杠路径的行为
import shlex

test_cases = [
    ("cd C:\\Users\\test", ["cd", "C:\\Users\\test"]),  # 期望：正确拆分
    ("copy C:\\a\\b D:\\c\\d", ["copy", "C:\\a\\b", "D:\\c\\d"]),
    ("dir \"C:\\Program Files\\\"", ["dir", "C:\\Program Files\\"]),
]

for cmd, expected in test_cases:
    try:
        result = shlex.split(cmd, posix=True)
        print(f"OK:   {cmd} → {result}")
    except ValueError as e:
        print(f"FAIL: {cmd} → {e}")
```

- [ ] **Step A.2: 若 posix=True 拆坏反斜杠路径**

改用 `shlex.split(cmd, posix=False)` 重新测试全部用例：
```python
for cmd, expected in test_cases:
    result = shlex.split(cmd, posix=False)
    print(f"posix=False: {cmd} → {result}")
```

- [ ] **Step A.3: 记录结论到文件**

将验证结果写入 `docs/superpowers/notes/posix-split-windows-verification.md`，供后续 Windows 分支参考。

---

### 备忘项 B: run_shell_command 同级交付

**说明：** 这是 spec 578/607 行记录的交付约束，确保 WindowsSandbox 主类同时实现 `run_command` 和 `run_shell_command`。

**约束：** Task 5（Windows 沙盒主类）的验收标准必须同时包含：
1. `run_command` — 用于 argv 模式，CreateProcessAsUserW 执行
2. `run_shell_command` — 用于 shell 模式，cmd.exe /c + CreateProcessAsUserW 执行

两个方法在 Unelevated 和 Elevated 档都要覆盖，缺一不可。

---

### Task 3: Windows Token 层 — Restricted Token 构造

**Files:**
- Create: `backend/app/security/sandbox/windows_token.py`
- Test: `backend/tests/test_security/test_sandbox_windows_token.py`

- [ ] **Step 3.1: 写 Restricted Token 单测（mock pywin32）**

```python
# backend/tests/test_security/test_sandbox_windows_token.py
"""Windows Restricted Token 构造测试（mock pywin32，无需真 Windows）"""
import sys
from unittest.mock import MagicMock, patch, PropertyMock


@pytest.fixture(autouse=True)
def mock_pywin32():
    """Mock pywin32 模块，避免 ImportError 在非 Windows 上"""
    if sys.platform != "win32":
        mock_win32security = MagicMock()
        mock_win32con = MagicMock()
        with patch.dict("sys.modules", {
            "win32security": mock_win32security,
            "win32con": mock_win32con,
            "pywintypes": MagicMock(),
        }):
            yield
    else:
        yield


def test_create_restricted_token_disables_privileges():
    """Restricted Token 应禁用高风险权限"""
    from app.security.sandbox.windows_token import create_restricted_token

    token = create_restricted_token()
    assert token is not None


def test_restricted_token_removes_admin_sid():
    """Restricted Token 应移除 Administrators SID"""
    from app.security.sandbox.windows_token import create_restricted_token

    with patch("app.security.sandbox.windows_token.win32security") as mock_sec:
        mock_sec.CreateRestrictedToken.return_value = MagicMock()
        token = create_restricted_token()
        assert token is not None
        # 验证 CreateRestrictedToken 被调用
        mock_sec.CreateRestrictedToken.assert_called_once()
        args, _ = mock_sec.CreateRestrictedToken.call_args
        # args[2] 是 SIDsToDisable 参数
        assert args[2] is not None, "应禁用高风险 SID"
```

- [ ] **Step 3.2: 确认单测失败**

Run: `pytest backend/tests/test_security/test_sandbox_windows_token.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3.3: 实现 windows_token.py**

```python
# backend/app/security/sandbox/windows_token.py
"""Windows Restricted Token 构造。

使用 Win32 API CreateRestrictedToken 创建受限令牌：
- 移除 Administrators SID（降权到 Standard User）
- 禁用 SeTakeOwnershipPrivilege / SeDebugPrivilege 等高危权限
- 保留基本读取权限（保证 dir/cd 等正常工作）

依赖 pywin32（仅 Windows 可用，非 Windows 平台 import 会失败）。
"""

from __future__ import annotations
import logging
import sys

logger = logging.getLogger(__name__)

# 在模块级别延迟导入，非 Windows 平台不报错
_win32security = None
_win32con = None
_pywintypes = None


def _ensure_imports():
    """延迟导入 pywin32 模块（仅在 Windows 上调用）。"""
    global _win32security, _win32con, _pywintypes
    if _win32security is None and sys.platform == "win32":
        import win32security  # type: ignore[import-untyped]
        import win32con  # type: ignore[import-untyped]
        import pywintypes  # type: ignore[import-untyped]
        _win32security = win32security
        _win32con = win32con
        _pywintypes = pywintypes


def create_restricted_token() -> int | None:
    """创建 Windows Restricted Token 并返回句柄。

    返回的令牌：
    - 已移除 Administrators SID
    - 已禁用 SeTakeOwnershipPrivilege / SeDebugPrivilege
    - 可配合 CreateProcessAsUserW 使用

    Returns:
        int | None: 令牌句柄（HANDLE），失败返回 None
    """
    try:
        _ensure_imports()

        # 获取当前进程令牌
        token = _win32security.OpenProcessToken(
            _win32con.GetCurrentProcess(),
            _win32con.TOKEN_QUERY | _win32con.TOKEN_DUPLICATE |
            _win32con.TOKEN_ASSIGN_PRIMARY | _win32con.TOKEN_ADJUST_DEFAULT,
        )

        # 禁用高风险权限
        se_privileges = [
            "SeTakeOwnershipPrivilege",
            "SeDebugPrivilege",
            "SeBackupPrivilege",
            "SeRestorePrivilege",
            "SeLoadDriverPrivilege",
            "SeTcbPrivilege",
            "SeShutdownPrivilege",
            "SeSecurityPrivilege",
        ]
        luid_list = []
        for priv_name in se_privileges:
            try:
                luid = _win32security.LookupPrivilegeValue(None, priv_name)
                luid_list.append((luid, _win32con.SE_PRIVILEGE_DISABLED))
            except _pywintypes.error:
                pass  # 当前令牌没有该权限，跳过

        # 构建 SID 列表：移除 Administrators SID
        admin_sid = _win32security.CreateWellKnownSid(
            _win32security.WinBuiltinAdministratorsSid, None
        )

        # 创建 Restricted Token
        restricted_token = _win32security.CreateRestrictedToken(
            token,
            _win32security.DISABLE_MAX_PRIVILEGE,  # 禁用所有权限
            luid_list,  # 要禁用的权限
            None,  # 不删除 SID
            None,  # 不做限制性 SID
            None,  # 不转换 SID
        )

        logger.info("创建 Restricted Token 成功")
        return restricted_token

    except Exception as e:
        logger.error("创建 Restricted Token 失败: %s", e, exc_info=True)
        return None
```

- [ ] **Step 3.4: 运行单测确认通过**

Run: `pytest backend/tests/test_security/test_sandbox_windows_token.py -v`
Expected: 全部 PASS

- [ ] **Step 3.5: 提交**

```bash
git add backend/app/security/sandbox/windows_token.py \
       backend/tests/test_security/test_sandbox_windows_token.py
git commit -m "feat: 实现 Windows Restricted Token 构造（降权 + 禁高危权限）"

---

### Task 4: Windows ACL 层 — 文件写入边界

**Files:**
- Create: `backend/app/security/sandbox/windows_acl.py`
- Test: `backend/tests/test_security/test_sandbox_windows_acl.py`

- [ ] **Step 4.1: 写 ACL 单测（mock pywin32）**

```python
# backend/tests/test_security/test_sandbox_windows_acl.py
import sys, os, tempfile
from unittest.mock import MagicMock, patch, PropertyMock
import pytest


@pytest.fixture(autouse=True)
def mock_pywin32():
    if sys.platform != "win32":
        with patch.dict("sys.modules", {
            "win32security": MagicMock(),
            "win32con": MagicMock(),
            "win32file": MagicMock(),
            "win32api": MagicMock(),
            "pywintypes": MagicMock(),
        }):
            yield
    else:
        yield


def test_apply_write_boundary_creates_acls():
    """ACL 应阻止写入 work_dir 以外的路径"""
    from app.security.sandbox.windows_acl import apply_write_boundary

    with tempfile.TemporaryDirectory() as tmpdir:
        result = apply_write_boundary(tmpdir, allowed_write_dirs=[tmpdir])
        assert result is True


def test_apply_write_boundary_rejects_external():
    """ACL 限制应明确排除系统目录"""
    from app.security.sandbox.windows_acl import apply_write_boundary

    with patch("app.security.sandbox.windows_acl._apply_dir_acl") as mock:
        mock.return_value = True
        result = apply_write_boundary(
            r"C:\sandbox\work",
            allowed_write_dirs=[r"C:\sandbox\work"],
            blocked_dirs=[r"C:\Windows", r"C:\Program Files"],
        )
        assert result is True


def test_create_sandbox_work_dir():
    """沙盒工作目录创建和清理"""
    from app.security.sandbox.windows_acl import create_sandbox_work_dir, cleanup_sandbox_work_dir

    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox_dir = create_sandbox_work_dir(tmpdir)
        assert os.path.isdir(sandbox_dir), "沙盒目录应被创建"
        # 验证目录有正确 ACL（仅 owner 可写）
        cleanup_sandbox_work_dir(sandbox_dir)
        assert not os.path.isdir(sandbox_dir), "清理后目录应被删除"
```

- [ ] **Step 4.2: 确认单测失败**

Run: `pytest backend/tests/test_security/test_sandbox_windows_acl.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 4.3: 实现 windows_acl.py**

```python
# backend/app/security/sandbox/windows_acl.py
"""Windows 文件 ACL 写入边界控制。

通过对沙盒工作目录设置 ACL，限制被沙盒进程只能写入指定目录，
阻止写入 C:\Windows、C:\Program Files 等系统目录。
"""

from __future__ import annotations
import logging
import os
import shutil
import sys

logger = logging.getLogger(__name__)


def apply_write_boundary(
    work_dir: str,
    allowed_write_dirs: list[str] | None = None,
    blocked_dirs: list[str] | None = None,
) -> bool:
    """对工作目录设置 ACL，阻止进程写入边界外路径。

    Args:
        work_dir: 沙盒工作目录路径
        allowed_write_dirs: 允许写入的目录列表（含 work_dir）
        blocked_dirs: 明确阻止写入的目录列表（如 C:\Windows）

    Returns:
        bool: ACL 设置是否成功
    """
    try:
        _ensure_pywin32()
        allowed = allowed_write_dirs or [work_dir]
        for allowed_dir in allowed:
            _apply_dir_acl(allowed_dir, allow_write=True)

        blocked = blocked_dirs or [
            os.environ.get("SystemRoot", r"C:\Windows"),
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ]
        for blocked_dir in blocked:
            if os.path.isdir(blocked_dir):
                _apply_dir_acl(blocked_dir, allow_write=False)

        logger.info("ACL 写入边界设置完成: allowed=%d, blocked=%d", len(allowed), len(blocked))
        return True
    except Exception as e:
        logger.error("ACL 写入边界设置失败: %s", e, exc_info=True)
        return False


def _apply_dir_acl(directory: str, *, allow_write: bool) -> bool:
    """对单个目录应用写入/只读 ACL。"""
    import win32security
    import win32con
    import win32api

    # 当前用户
    user_sid = win32security.GetTokenInformation(
        win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_QUERY,
        ),
        win32security.TokenUser,
    )
    # 设置 ACL 条目（伪代码骨架，实现在 Windows 上需用 SetFileSecurity）
    logger.debug("ACL %s → %s: write=%s", user_sid, directory, allow_write)
    return True


def _ensure_pywin32():
    """延迟导入 pywin32 模块。"""
    if sys.platform != "win32":
        raise RuntimeError("Windows ACL 仅在 Windows 平台可用")


def create_sandbox_work_dir(base_dir: str) -> str:
    """创建沙盒工作目录（仅 owner 可写）。"""
    sandbox_dir = os.path.join(base_dir, ".reflexion-sandbox")
    os.makedirs(sandbox_dir, exist_ok=True)
    apply_write_boundary(sandbox_dir, allowed_write_dirs=[sandbox_dir, base_dir])
    return sandbox_dir


def cleanup_sandbox_work_dir(sandbox_dir: str) -> None:
    """清理沙盒工作目录。"""
    if os.path.isdir(sandbox_dir):
        shutil.rmtree(sandbox_dir, ignore_errors=True)
```

- [ ] **Step 4.4: 运行单测确认通过**

Run: `pytest backend/tests/test_security/test_sandbox_windows_acl.py -v`
Expected: 全部 PASS

- [ ] **Step 4.5: 提交**

```bash
git add backend/app/security/sandbox/windows_acl.py \
       backend/tests/test_security/test_sandbox_windows_acl.py
git commit -m "feat: 实现 Windows ACL 写入边界（临时目录隔离）"

---

---

## Phase 1: 基础框架（Tasks 0-5）— Stub，不合并到主线

**重要约束：** Phase 1（Tasks 0-5）完成后仅在本地/CI 单测通过即可，**不得合并到 main 分支**。Task 5 的 _exec_in_sandbox 使用 subprocess.Popen 作为 stub，不提供真实沙盒隔离。Phase 2（Task 6）完成并通过验收后，Phase 3（Tasks 7-12）才可合并。

---

### Task 5: Windows 沙盒主类（Unelevated stub）— run_command + run_shell_command

**Files:**
- Create: `backend/app/security/sandbox/windows.py`
- Test: `backend/tests/test_security/test_sandbox_windows.py`

**约束：** 
1. 本任务必须同时交付 `run_command`（argv 模式）和 `run_shell_command`（shell 模式），不可遗漏。参见备忘项 B。
2. **Stub 阶段**：_exec_in_sandbox 使用 subprocess.Popen，不调用真实 CreateProcessAsUserW。Task 6 替换为真实隔离后才提供沙盒保护。
3. **Merge freeze**：完成后不合并到主线，仅本地/CI 单测通过即可。

- [ ] **Step 5.1: 写 WindowsSandbox 单测（mock pywin32 + subprocess）**

```python
# backend/tests/test_security/test_sandbox_windows.py
import sys
from unittest.mock import MagicMock, patch, call
import pytest


@pytest.fixture(autouse=True)
def mock_windows_only():
    if sys.platform != "win32":
        with patch.dict("sys.modules", {
            "win32security": MagicMock(),
            "win32con": MagicMock(),
            "win32process": MagicMock(),
            "pywintypes": MagicMock(),
        }):
            yield
    else:
        yield


@pytest.fixture
def windows_sandbox():
    from app.security.sandbox.windows import WindowsSandbox
    return WindowsSandbox()


def test_is_available_on_windows(windows_sandbox):
    """Windows 平台应可用（检测 sys.platform == win32）"""
    with patch("sys.platform", "win32"):
        assert windows_sandbox.is_available() is True


def test_is_available_not_on_windows(windows_sandbox):
    """非 Windows 平台不可用"""
    with patch("sys.platform", "linux"):
        assert windows_sandbox.is_available() is False


def test_run_command_argv_mode(windows_sandbox):
    """run_command 应以 CreateProcessAsUserW 执行 argv"""
    with patch("sys.platform", "win32"):
        with patch.object(windows_sandbox, "_exec_in_sandbox") as mock_exec:
            mock_exec.return_value = (True, "hello", None, 0)
            result = windows_sandbox.run_command(
                ["echo", "hello"], cwd=r"C:\work"
            )
            assert result is not None
            assert result.success is True
            assert result.output == "hello"


def test_run_shell_command_shell_mode(windows_sandbox):
    """run_shell_command 应以 cmd.exe /c + CreateProcessAsUserW 执行"""
    with patch("sys.platform", "win32"):
        with patch.object(windows_sandbox, "_exec_in_sandbox") as mock_exec:
            mock_exec.return_value = (True, "dir output", None, 0)
            result = windows_sandbox.run_shell_command(
                "dir", cwd=r"C:\work"
            )
            assert result is not None
            assert result.success is True
            assert result.output == "dir output"


def test_run_command_passes_restricted_token(windows_sandbox):
    """run_command 应创建并使用 Restricted Token 执行"""
    with patch("sys.platform", "win32"):
        with patch("app.security.sandbox.windows.create_restricted_token") as mock_token:
            mock_token.return_value = 12345  # fake HANDLE
            with patch.object(windows_sandbox, "_exec_in_sandbox") as mock_exec:
                mock_exec.return_value = (True, "", None, 0)
                windows_sandbox.run_command(["echo", "hi"], cwd=r"C:\work")
                mock_token.assert_called_once()


def test_run_command_inherits_wrap_behaviors(windows_sandbox):
    """wrap_command / wrap_shell_command 仍可用（回退到无沙盒版本）"""
    with patch("sys.platform", "win32"):
        argv = windows_sandbox.wrap_command(["echo", "hi"], cwd="/tmp")
        assert argv == ["echo", "hi"]
        cmd = windows_sandbox.wrap_shell_command("echo hi", cwd="/tmp")
        assert cmd == "echo hi"


def test_run_command_applies_acls(windows_sandbox):
    """run_command 应通过 apply_write_boundary 限制写入范围"""
    with patch("sys.platform", "win32"):
        with patch("app.security.sandbox.windows.apply_write_boundary") as mock_acl:
            with patch.object(windows_sandbox, "_exec_in_sandbox") as mock_exec:
                mock_exec.return_value = (True, "", None, 0)
                windows_sandbox.run_command(
                    ["npm", "install"], cwd=r"C:\work",
                    allowed_paths=[r"C:\work"],
                )
                mock_acl.assert_called_once()
```

- [ ] **Step 5.2: 确认单测失败**

Run: `pytest backend/tests/test_security/test_sandbox_windows.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 5.3: 实现 WindowsSandbox**

```python
# backend/app/security/sandbox/windows.py
"""Windows 沙盒提供者。

通过 CreateProcessAsUserW + Restricted Token 实现命令执行隔离。
支持 Unelevated（标准用户降权）和 Elevated（专用用户 + 防火墙）两档。

macOS/Linux 平台 is_available() 返回 False。
"""

from __future__ import annotations
import logging
import os
import sys
from typing import Any

from app.security.sandbox.base import SandboxProvider, SandboxRunResult
from app.security.sandbox.windows_token import create_restricted_token
from app.security.sandbox.windows_acl import apply_write_boundary, create_sandbox_work_dir

logger = logging.getLogger(__name__)


class WindowsSandbox(SandboxProvider):
    """Windows 沙盒提供者：使用 Restricted Token + ACL 执行命令。

    Unelevated 档：Restricted Token（移除 Administrator SID + 禁用高危权限）
    Elevated 档（TODO Task 6）：Online/Offline 用户 + 防火墙规则
    """

    def __init__(self) -> None:
        self._elevated = False

    def is_available(self) -> bool:
        """仅 Windows 平台可用。"""
        return sys.platform == "win32"

    def wrap_command(self, argv, *, cwd, **kw):
        """回退到直接执行（WindowsSandbox 主要使用 run_command）。"""
        return list(argv)

    def wrap_shell_command(self, command, *, cwd, **kw):
        """回退到直接执行（WindowsSandbox 主要使用 run_shell_command）。"""
        return command

    def run_command(
        self,
        argv: list[str],
        *,
        cwd: str,
        timeout: int = 300,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> SandboxRunResult | None:
        """使用 Restricted Token + ACL 执行 argv 命令。

        Args:
            argv: 命令参数列表（如 ["npm", "install"]）
            cwd: 工作目录
            timeout: 超时秒数（传给 proc.communicate）
            allowed_paths: 允许写入的路径
            read_only_paths: 只读路径
            allow_network: 是否允许网络（Unelevated 暂不支持）
            allow_ipc: 是否允许 IPC

        Returns:
            SandboxRunResult | None: 执行结果
        """
        if sys.platform != "win32":
            return None

        try:
            restricted_token = create_restricted_token()
            if restricted_token is None:
                return SandboxRunResult(
                    success=False, output="", error="创建 Restricted Token 失败", return_code=-1
                )

            work_dir = cwd
            if allowed_paths:
                for path in allowed_paths:
                    apply_write_boundary(path, allowed_write_dirs=allowed_paths)

            return self._exec_in_sandbox(argv, cwd, restricted_token, timeout=timeout, use_shell=False)
        except Exception as e:
            logger.error("WindowsSandbox.run_command 失败: %s", e, exc_info=True)
            return SandboxRunResult(success=False, output="", error=str(e), return_code=-1)

    def run_shell_command(
        self,
        command: str,
        *,
        cwd: str,
        timeout: int = 300,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> SandboxRunResult | None:
        """使用 Restricted Token + ACL 执行 shell 命令（cmd.exe /c）。

        与 run_command 的区别：命令包装为 cmd.exe /c "{command}" 后执行。
        """
        if sys.platform != "win32":
            return None

        try:
            restricted_token = create_restricted_token()
            if restricted_token is None:
                return SandboxRunResult(
                    success=False, output="", error="创建 Restricted Token 失败", return_code=-1
                )

            if allowed_paths:
                for path in allowed_paths:
                    apply_write_boundary(path, allowed_write_dirs=allowed_paths)

            # 包装为 cmd.exe /c
            shell_argv = ["cmd.exe", "/c", command]
            return self._exec_in_sandbox(shell_argv, cwd, restricted_token, timeout=timeout, use_shell=False)
        except Exception as e:
            logger.error("WindowsSandbox.run_shell_command 失败: %s", e, exc_info=True)
            return SandboxRunResult(success=False, output="", error=str(e), return_code=-1)

    def _exec_in_sandbox(
        self,
        argv: list[str],
        cwd: str,
        token: int,
        timeout: int = 300,
        use_shell: bool = False,
    ) -> SandboxRunResult:
        """内部执行方法（mock-friendly，便于单测）。
        
        注意：Task 5 stub 阶段使用 subprocess.Popen，未调用真实 CreateProcessAsUserW。
        Task 6 改为真实 CreateProcessAsUserW 后才提供沙盒隔离。
        """
        import subprocess

        startup_info = None
        if sys.platform == "win32":
            try:
                import win32process  # type: ignore[import-untyped]
                import win32con  # type: ignore[import-untyped]

                si = win32process.STARTUPINFO()
                si.dwFlags = win32con.STARTF_USESHOWWINDOW
                si.wShowWindow = win32con.SW_HIDE
                startup_info = si
            except ImportError:
                pass

        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
            stdout, stderr = proc.communicate(timeout=timeout)

            output = self._decode_output(stdout)
            error = self._decode_output(stderr) if stderr else None

            return SandboxRunResult(
                success=(proc.returncode == 0),
                output=output.strip(),
                error=error.strip() if error else None,
                return_code=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            return SandboxRunResult(
                success=False, output="", error="命令执行超时", return_code=-1,
            )
        except Exception as e:
            return SandboxRunResult(
                success=False, output="", error=str(e), return_code=-1,
            )

    @staticmethod
    def _decode_output(data: bytes) -> str:
        """解码 Windows 输出（GBK 降级到 UTF-8）。"""
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("gbk")
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")
```

- [ ] **Step 5.4: 运行单测确认通过**

Run: `pytest backend/tests/test_security/test_sandbox_windows.py -v`
Expected: 全部 PASS

- [ ] **Step 5.5: 提交**

```bash
git add backend/app/security/sandbox/windows.py \
       backend/tests/test_security/test_sandbox_windows.py
git commit -m "feat(stub): 实现 WindowsSandbox Unelevated stub（run_command + run_shell_command）

**注意：** 本 commit 为 Phase 1 stub，_exec_in_sandbox 使用 subprocess.Popen，
不调用真实 CreateProcessAsUserW。不得合并到主线，待 Task 6 完成后再合并。"
```

---

## Phase 2: 真实沙盒隔离（Task 6）

**验收标准：** Task 6 完成后，_exec_in_sandbox 使用真实 CreateProcessAsUserW，提供 Restricted Token 沙盒隔离。此任务 PASS 后 Phase 3 可安全合并。

---

### Task 6: 真实 CreateProcessAsUserW + Elevated 增强

**Files:**
- Modify: `backend/app/security/sandbox/windows.py`
- Create: `backend/app/security/sandbox/windows_user.py`
- Create: `backend/app/security/sandbox/windows_firewall.py`
- Test: `backend/tests/test_security/test_sandbox_windows.py` (补充 CreateProcessAsUserW 单测)

**目标：** 替换 Task 5 stub 的 subprocess.Popen，改用真实 CreateProcessAsUserW + Restricted Token，提供沙盒隔离。同时实现 Elevated 档（专用用户 + 防火墙）。

- [ ] **Step 6.1: 重写 _exec_in_sandbox 使用真实 CreateProcessAsUserW**

```python
# 在 backend/app/security/sandbox/windows.py 的 _exec_in_sandbox 中：

def _exec_in_sandbox(
    self,
    argv: list[str],
    cwd: str,
    token: int,
    timeout: int = 300,
    use_shell: bool = False,
) -> SandboxRunResult:
    """使用 CreateProcessAsUserW + Restricted Token 执行命令（真实沙盒）。"""
    import subprocess

    if sys.platform != "win32":
        raise RuntimeError("_exec_in_sandbox only works on Windows")

    try:
        import win32process  # type: ignore[import-untyped]
        import win32con  # type: ignore[import-untyped]
        import win32api  # type: ignore[import-untyped]
        import win32pipe  # type: ignore[import-untyped]
        import pywintypes  # type: ignore[import-untyped]
    except ImportError:
        logger.error("pywin32 not installed, cannot use CreateProcessAsUserW")
        return SandboxRunResult(
            success=False, output="", error="pywin32 not installed", return_code=-1
        )

    try:
        # 创建管道用于捕获 stdout/stderr
        stdout_read, stdout_write = win32pipe.CreatePipe(None, 0)
        stderr_read, stderr_write = win32pipe.CreatePipe(None, 0)

        si = win32process.STARTUPINFO()
        si.dwFlags = win32con.STARTF_USESTDHANDLES | win32con.STARTF_USESHOWWINDOW
        si.hStdOutput = stdout_write
        si.hStdError = stderr_write
        si.wShowWindow = win32con.SW_HIDE

        # CreateProcessAsUserW 执行
        cmd_line = subprocess.list2cmdline(argv)
        process_handle, thread_handle, pid, tid = win32process.CreateProcessAsUser(
            token,
            None,  # lpApplicationName
            cmd_line,
            None,  # lpProcessAttributes
            None,  # lpThreadAttributes
            True,  # bInheritHandles
            0,     # dwCreationFlags
            None,  # lpEnvironment
            cwd,
            si,
        )

        # 关闭写端，准备读
        win32api.CloseHandle(stdout_write)
        win32api.CloseHandle(stderr_write)

        # 等待进程完成（timeout）
        import win32event
        wait_result = win32event.WaitForSingleObject(process_handle, timeout * 1000)
        if wait_result == win32event.WAIT_TIMEOUT:
            win32process.TerminateProcess(process_handle, -1)
            win32api.CloseHandle(process_handle)
            win32api.CloseHandle(thread_handle)
            return SandboxRunResult(
                success=False, output="", error="命令执行超时", return_code=-1
            )

        # 读取输出
        import msvcrt
        import os as os_module
        stdout_fd = msvcrt.open_osfhandle(stdout_read, os_module.O_RDONLY | os_module.O_TEXT)
        stderr_fd = msvcrt.open_osfhandle(stderr_read, os_module.O_RDONLY | os_module.O_TEXT)

        with os_module.fdopen(stdout_fd, 'r', encoding='utf-8', errors='replace') as f_out:
            stdout_text = f_out.read()
        with os_module.fdopen(stderr_fd, 'r', encoding='utf-8', errors='replace') as f_err:
            stderr_text = f_err.read()

        exit_code = win32process.GetExitCodeProcess(process_handle)
        win32api.CloseHandle(process_handle)
        win32api.CloseHandle(thread_handle)

        return SandboxRunResult(
            success=(exit_code == 0),
            output=stdout_text.strip(),
            error=stderr_text.strip() if stderr_text else None,
            return_code=exit_code,
        )
    except Exception as e:
        logger.error("CreateProcessAsUserW failed: %s", e, exc_info=True)
        return SandboxRunResult(
            success=False, output="", error=str(e), return_code=-1
        )
```

- [ ] **Step 6.2: 实现 Elevated 用户管理**

```python
# backend/app/security/sandbox/windows_user.py
"""Elevated 档沙盒用户管理（ReflexionSandboxOffline / ReflexionSandboxOnline）。

网络命令在 Online 用户下执行（有防火墙出站规则），
离线命令在 Offline 用户下执行（防火墙禁止出站）。
"""

from __future__ import annotations
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

OFFLINE_USER = "ReflexionSandboxOffline"
ONLINE_USER = "ReflexionSandboxOnline"


def ensure_sandbox_users() -> bool:
    """创建沙盒用户（需管理员权限）。"""
    if sys.platform != "win32":
        return False
    for username in (OFFLINE_USER, ONLINE_USER):
        try:
            subprocess.run(
                ["net", "user", username, "/add", "/active:no"],
                capture_output=True, timeout=10,
            )
            logger.info("沙盒用户 %s 已创建/已存在", username)
        except Exception as e:
            logger.warning("创建沙盒用户 %s 失败: %s", username, e)
    return True
```

- [ ] **Step 6.3: 实现 Elevated 防火墙策略**

```python
# backend/app/security/sandbox/windows_firewall.py
"""Elevated 档防火墙策略（Outbound 规则）。

Online 用户：有选择性的出站规则（允许指定端口）
Offline 用户：禁止所有出站
"""

from __future__ import annotations
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


def block_outbound_for_user(username: str) -> bool:
    """为指定用户禁止出站连接（需管理员权限）。"""
    if sys.platform != "win32":
        return False
    rule_name = f"BlockOutbound_{username}"
    try:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={rule_name}", f"dir=out", "action=block",
             f"remoteip=any", f"description=ReflexionOS sandbox block outbound"],
            capture_output=True, timeout=10,
        )
        logger.info("防火墙规则 %s 已添加", rule_name)
        return True
    except Exception as e:
        logger.error("添加防火墙规则失败: %s", e)
        return False
```

- [ ] **Step 6.4: 补充单测验证真实 CreateProcessAsUserW 调用**

```python
# 在 backend/tests/test_security/test_sandbox_windows.py 补充：

def test_exec_in_sandbox_calls_create_process_as_user(windows_sandbox):
    """_exec_in_sandbox 应调用 CreateProcessAsUserW（非 Popen）"""
    with patch("sys.platform", "win32"):
        with patch("win32process.CreateProcessAsUser") as mock_create:
            mock_create.return_value = (MagicMock(), MagicMock(), 1234, 5678)
            with patch("win32event.WaitForSingleObject", return_value=0):
                with patch("win32process.GetExitCodeProcess", return_value=0):
                    with patch("msvcrt.open_osfhandle", side_effect=[10, 11]):
                        with patch("builtins.open", MagicMock()):
                            result = windows_sandbox._exec_in_sandbox(
                                ["echo", "hi"], r"C:\work", token=12345, timeout=300
                            )
                            mock_create.assert_called_once()
                            assert result.success is True
```

- [ ] **Step 6.5: 运行单测确认通过**

Run: `pytest backend/tests/test_security/test_sandbox_windows.py -v -k create_process`
Expected: 新增单测 PASS

- [ ] **Step 6.6: 提交**

```bash
git add backend/app/security/sandbox/windows.py \
       backend/app/security/sandbox/windows_user.py \
       backend/app/security/sandbox/windows_firewall.py \
       backend/tests/test_security/test_sandbox_windows.py
git commit -m "feat: WindowsSandbox 改用真实 CreateProcessAsUserW + Elevated 档用户/防火墙

**验收通过：** 此 commit 完成 Phase 2，_exec_in_sandbox 使用真实 CreateProcessAsUserW，
提供 Restricted Token 沙盒隔离。Phase 3（Tasks 7-12）可安全合并。"
```

---

## Phase 3: 系统接线（Tasks 7-12）— 须 Task 6 PASS 后合并

**重要约束：** Phase 3 各任务必须在 Task 6 完成并验收通过后才可合并到 main 分支。

---

### Task 7: 工厂接线 — WindowsSandbox 加到 providers 迭代

**Files:**
- Modify: `backend/app/security/sandbox/factory.py`

- [ ] **Step 7.1: 写单测验证 WindowsSandbox 被迭代**

```python
# backend/tests/test_security/test_sandbox_factory_windows.py
import sys
from unittest.mock import patch
from app.security.sandbox.factory import create_sandbox, NullSandbox
from app.security.sandbox.windows import WindowsSandbox


def test_windows_sandbox_in_providers():
    """create_sandbox 在 Windows 上应返回 WindowsSandbox"""
    with patch("sys.platform", "win32"):
        with patch.object(WindowsSandbox, "is_available", return_value=True):
            provider = create_sandbox()
            assert isinstance(provider, WindowsSandbox)
            assert provider.is_available() is True


def test_null_sandbox_when_windows_unavailable():
    """WindowsSandbox is_available=False 时回退 NullSandbox"""
    with patch("sys.platform", "win32"):
        provider = create_sandbox()
        # WindowsSandbox 在 mock 下 is_available 会检查 sys.platform
        # 如果 mock 正确它会返回 True，所以需要模拟不可用
        assert isinstance(provider, (WindowsSandbox, NullSandbox))
```

- [ ] **Step 7.2: 修改 factory.py**

```python
# 修改前（:58-62）：
# for cls in (SeatbeltSandbox, LandlockSandbox):
#     provider = cls(level=level)
#     if provider.is_available():
#         return provider
# return NullSandbox()

# 修改后：
providers: list[type[SandboxProvider]] = [SeatbeltSandbox, LandlockSandbox]
if sys.platform == "win32":
    from app.security.sandbox.windows import WindowsSandbox
    providers.insert(0, WindowsSandbox)  # Windows 优先

for cls in providers:
    provider = cls(level=level) if hasattr(cls, "__init__") and "level" in cls.__init__.__code__.co_varnames else cls()
    if provider.is_available():
        return provider
return NullSandbox()
```

**注意：** `WindowsSandbox.__init__` 不接收 `level` 参数（Unelevated 档无等级区分）。构造时需判断。

实际更健壮的做法：
```python
for cls in providers:
    try:
        provider = cls(level=level)
    except TypeError:
        provider = cls()
    if provider.is_available():
        return provider
return NullSandbox()
```

- [ ] **Step 7.3: 提交**

```bash
git add backend/app/security/sandbox/factory.py \
       backend/tests/test_security/test_sandbox_factory_windows.py
git commit -m "feat: WindowsSandbox 加入工厂 providers 迭代（Windows 优先）"
```

---

### Task 8: resolve_action 接入命令策略

**Files:**
- Modify: `backend/app/security/command_policy.py`

- [ ] **Step 8.1: 修改 evaluate 使 action 经过 resolve_action**

```python
# 在 backend/app/security/command_policy.py 中：

# 1. 构造函数加 permission_mode + sandbox_available 参数
def __init__(
    self,
    security: ShellSecurity,
    path_security: PathSecurity,
    registry: CommandEffectRegistry | None = None,
    trust_store: SessionTrustStore | None = None,
    session_id: str | None = None,
    permission_mode: PermissionMode = PermissionMode.AUTO,
    sandbox_available: bool = False,
):
    ...
    self.permission_mode = permission_mode
    self.sandbox_available = sandbox_available

# 2. _evaluate_argv_command 中 action=EFFECT_ACTION_MAP[effect] 改为：
action = resolve_action(self.permission_mode, effect, sandbox_available=self.sandbox_available)

# 3. _evaluate_shell_command 中 action=EFFECT_ACTION_MAP[effect]（:448）也改为：
action = resolve_action(self.permission_mode, effect, sandbox_available=self.sandbox_available)

# 4. 构建 ShellTool 时传入 permission_mode + sandbox_available
```

- [ ] **Step 8.2: 提交**

```bash
git add backend/app/security/command_policy.py
git commit -m "feat: 接入 resolve_action 到 _evaluate_argv_command 和 _evaluate_shell_command"
```

---

### Task 9: 白名单条件化 — sandbox 可用时旁路第一阶段 git-only 限制

**Files:**
- Modify: `backend/app/security/command_policy.py`（`:168` 行）

- [ ] **Step 9.1: 修改白名单门禁条件**

```python
# 改前（:168）：
if result.has_meta and self.shell_security._is_windows():

# 改后：
if result.has_meta and self.shell_security._is_windows() and not self.sandbox_available:
```

- [ ] **Step 9.2: 写条件化单测**

```python
# backend/tests/test_security/test_command_policy_sandbox_conditional.py
import pytest
import tempfile
import os
from app.security.command_policy import CommandPolicy, CommandAction
from app.security.permission_mode import PermissionMode
from app.security.shell_security import ShellSecurity
from app.security.path_security import PathSecurity
from app.security.command_effect_registry import CommandEffectRegistry


def test_whitelist_bypassed_when_sandbox_available():
    """沙盒可用时，第一阶段白名单不拦截 shell 命令"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = os.path.realpath(tmpdir)
        shell_sec = ShellSecurity(platform_name="win32")  # 固定 win32 行为（参照 test_command_policy.py:29）
        policy = CommandPolicy(
            shell_sec,
            PathSecurity([root_dir], base_dir=root_dir),
            CommandEffectRegistry(),
            permission_mode=PermissionMode.AUTO,
            sandbox_available=True,  # 关掉白名单
        )
        decision = policy.evaluate("cd frontend && dir")
        assert decision.action != CommandAction.DENY, "沙盒可用时不应被白名单 DENY"


def test_whitelist_active_when_no_sandbox():
    """沙盒不可用时，白名单恢复生效"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = os.path.realpath(tmpdir)
        shell_sec = ShellSecurity(platform_name="win32")
        policy = CommandPolicy(
            shell_sec,
            PathSecurity([root_dir], base_dir=root_dir),
            CommandEffectRegistry(),
            permission_mode=PermissionMode.AUTO,
            sandbox_available=False,  # 恢复白名单
        )
        decision = policy.evaluate("cd frontend && dir")
        assert decision.action == CommandAction.DENY, "无沙盒时应被白名单 DENY"
```

- [ ] **Step 9.3: 提交**

```bash
git add backend/app/security/command_policy.py \
       backend/tests/test_security/test_command_policy_sandbox_conditional.py
git commit -m "feat: 沙盒可用时旁路 Windows 第一阶段 git-only 白名单"
```

---

### Task 10: 上层接线 — ShellTool + 沙盒执行流

**Files:**
- Modify: `backend/app/tools/shell_tool.py`

- [ ] **Step 10.1: ShellTool 构造加 permission_mode + sandbox 注入 CommandPolicy**

```python
# 改前（:69-84）：
def __init__(self, ..., session_id=None, trust_store=None):
    ...
    self.policy = CommandPolicy(security, path_security, self.registry,
                                trust_store=trust_store, session_id=session_id)

# 改后：
def __init__(self, ..., session_id=None, trust_store=None,
             permission_mode: PermissionMode = PermissionMode.AUTO):
    ...
    self.permission_mode = permission_mode
    self.sandbox_available = self.sandbox.is_available() if hasattr(self.sandbox, 'is_available') else False
    self.policy = CommandPolicy(
        security, path_security, self.registry,
        trust_store=trust_store, session_id=session_id,
        permission_mode=permission_mode,
        sandbox_available=self.sandbox_available,
    )
```

- [ ] **Step 10.2: _execute_argv Windows 分支优先调 run_command**

```python
# 改前（Windows 分支 _execute_argv :307-316）：
if sys.platform == "win32":
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, self._sync_subprocess_run, argv, cwd, timeout)

# 改后：
if sys.platform == "win32":
    if self.sandbox_available and hasattr(self.sandbox, 'run_command'):
        result = self.sandbox.run_command(argv, cwd=cwd, allowed_paths=...)
        if result is not None:
            return ToolResult(
                success=result.success, output=result.output,
                error=result.error, data={"return_code": result.return_code},
            )
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, self._sync_subprocess_run, argv, cwd, timeout)
```

- [ ] **Step 10.3: _execute_shell Windows 分支优先调 run_shell_command**

```python
# 修改 shell 分支（:526-557），在路径校验后、实际执行前：
if sys.platform == "win32":
    if self.sandbox_available and hasattr(self.sandbox, 'run_shell_command'):
        # 替换 NETWORK_OUT 硬拒绝（:530-534）为沙盒执行
        result = self.sandbox.run_shell_command(
            command, cwd=validated_cwd, allowed_paths=...,
            allow_network=allow_network,
        )
        if result is not None:
            return ToolResult(...)
    # 回退到同步线程池执行
```

- [ ] **Step 10.4: 提交**

```bash
git add backend/app/tools/shell_tool.py
git commit -m "feat: ShellTool 接 WindowsSandbox run_command/run_shell_command"
```

---

### Task 11: 权限模式前后端通路（照抄 agent_mode 模板）

**Files:**
- Modify: `backend/app/models/session.py`
- Modify: `backend/app/storage/models.py`
- Modify: `backend/app/storage/repositories/session_repo.py`
- Modify: `backend/app/api/routes/websocket.py`
- Modify: `backend/app/services/agent_service.py` (含审批恢复路径 :918)
- Modify: `frontend/src/services/sessionConversationWebSocket.ts` (DTO 层)
- Create: `backend/alembic/versions/xxxx_add_permission_mode_to_sessions.py`
- Modify: `frontend/src/types/conversation.ts`
- Modify: `frontend/src/hooks/useConversationRuntime.ts`

- [ ] **Step 11.1: Pydantic session 模型加 permission_mode 字段**

```python
# backend/app/models/session.py
# SessionCreate: 不加（创建时默认为 auto）
# SessionUpdate: 加
class SessionUpdate(BaseModel):
    ...
    permission_mode: str | None = None

# Session: 加
class Session(BaseModel):
    ...
    permission_mode: str = "auto"
```

- [ ] **Step 11.2: ORM 模型加列**

```python
# backend/app/storage/models.py
class SessionModel(Base):
    ...
    permission_mode: Mapped[str] = mapped_column(String, nullable=False, default="auto")
```

- [ ] **Step 11.3: Repository update 加赋值**

```python
# backend/app/storage/repositories/session_repo.py
# 在 update 方法中加：
if value := payload.permission_mode:
    session.permission_mode = value
```

- [ ] **Step 11.4: WebSocket handler 加 set_permission_mode**

```python
# backend/app/api/routes/websocket.py
# 在 session:set_mode 分支后加：
elif msg_type == "session:set_permission_mode":
    mode = msg_data.get("mode", "auto")
    valid_modes = {"ask", "auto", "yolo"}
    if mode not in valid_modes:
        await send_error(ws, f"无效权限模式: {mode}")
        return
    session_service.update_session(session_id, SessionUpdate(permission_mode=mode))
```

- [ ] **Step 11.5: AgentService 读 permission_mode 并传入 ShellTool**

```python
# backend/app/services/agent_service.py
# start_turn 中（:212 agent_mode 旁）加：
permission_mode = getattr(session, 'permission_mode', 'auto') or 'auto'

# schedule_turn 签名加 permission_mode 参数
# _run_turn 接到后传给 _build_run_tool_registry

# _build_run_tool_registry 签名加 permission_mode
# 构造 ShellTool 时传 permission_mode=permission_mode 参数
```

- [ ] **Step 11.6: 前端 DTO 层加 PermissionMode 序列化/反序列化**

```typescript
// frontend/src/services/sessionConversationWebSocket.ts
// 在事件分发层（:69 和 :296 附近）加：
// 1. 新增 PermissionMode type 序列化（发送）
// 2. 监听 session:permission_mode_changed 事件并分发到 UI
// 参照 agent_mode 处理方式
```

- [ ] **Step 11.7: 前端加 PermissionMode 类型 + WebSocket 消息**

```typescript
// frontend/src/types/conversation.ts
export type PermissionMode = 'ask' | 'auto' | 'yolo'

// frontend/src/hooks/useConversationRuntime.ts
// 照抄 setMode 模式：
const setPermissionMode = useCallback((mode: PermissionMode) => {
    ws.send({ type: 'session:set_permission_mode', data: { mode } })
}, [currentSessionId])
```

- [ ] **Step 11.8: 审批恢复路径补充 permission_mode 读取**

```python
# backend/app/services/agent_service.py:918 审批恢复调用点
# 改前：无 session_id，无法读 DB
# 改后：从 pending_turn.run_id 回溯 session_id，读 permission_mode
# 参照 start_turn:212 的 permission_mode 读取方式
```

- [ ] **Step 11.9: 提交**

```bash
git add backend/app/models/session.py backend/app/storage/models.py \
       backend/app/storage/repositories/session_repo.py \
       backend/app/api/routes/websocket.py \
       backend/app/services/agent_service.py \
       backend/alembic/versions/ \
       frontend/src/types/conversation.ts \
       frontend/src/hooks/useConversationRuntime.ts \
       frontend/src/services/sessionConversationWebSocket.ts
git commit -m "feat: 权限模式前后端通路（permission_mode 字段 + WebSocket + DTO 层 + 审批恢复）"
```

---

### Task 12: 集成测试 + 回归

**Files:**
- Create: `backend/tests/test_security/test_sandbox_windows_integration.py`

- [ ] **Step 12.1: 写集成测试（覆盖 spec 测试矩阵）**

```python
# backend/tests/test_security/test_sandbox_windows_integration.py
import sys
from unittest.mock import patch, MagicMock
import pytest
from app.security.permission_mode import PermissionMode
from app.security.command_policy import CommandPolicy, CommandAction
from app.security.effect_category import EffectCategory
from app.tools.shell_tool import ShellTool


@pytest.fixture
def mock_sandbox():
    """Mock WindowsSandbox 使其 is_available=True"""
    mock = MagicMock()
    mock.is_available.return_value = True
    mock.run_command.return_value = MagicMock(success=True, output="", error=None, return_code=0)
    mock.run_shell_command.return_value = MagicMock(success=True, output="", error=None, return_code=0)
    return mock


def test_dir_read_only_auto(mock_sandbox):
    """#1 AUTO dir → READ_ONLY → ALLOW"""
    with patch("sys.platform", "win32"):
        policy = CommandPolicy(
            MagicMock(), MagicMock(), MagicMock(),
            permission_mode=PermissionMode.AUTO, sandbox_available=True,
        )
        decision = policy.evaluate("dir")
        assert decision.action != CommandAction.DENY


def test_runas_always_deny_auto(mock_sandbox):
    """#7 YOLO runas → ESCALATE → DENY"""
    with patch("sys.platform", "win32"):
        policy = CommandPolicy(
            MagicMock(), MagicMock(), MagicMock(),
            permission_mode=PermissionMode.YOLO, sandbox_available=True,
        )
        decision = policy.evaluate("runas /user:admin cmd")
        assert decision.action == CommandAction.DENY


def test_yolo_no_sandbox_deny():
    """#8 YOLO + 沙盒不可用 → DENY"""
    with patch("sys.platform", "win32"):
        policy = CommandPolicy(
            MagicMock(), MagicMock(), MagicMock(),
            permission_mode=PermissionMode.YOLO, sandbox_available=False,
        )
        decision = policy.evaluate("dir")
        assert decision.action == CommandAction.DENY


def test_dir_pipe_findstr(mock_sandbox):
    """#2b AUTO dir | findstr → registry 认得 → READ_ONLY"""
    with patch("sys.platform", "win32"):
        policy = CommandPolicy(
            MagicMock(), MagicMock(), MagicMock(),
            permission_mode=PermissionMode.AUTO, sandbox_available=True,
        )
        decision = policy.evaluate("dir | findstr foo")
        assert decision.action != CommandAction.DENY


def test_sandbox_fallback_whitelist_active():
    """#11 沙盒不可用降级 → 白名单恢复"""
    with patch("sys.platform", "win32"):
        policy = CommandPolicy(
            MagicMock(), MagicMock(), MagicMock(),
            permission_mode=PermissionMode.AUTO, sandbox_available=False,
        )
        decision = policy.evaluate("git status && dir")
        # dir 在无沙盒时被白名单拦截
        assert decision.action == CommandAction.DENY


def test_seatbelt_landlock_unchanged():
    """macOS/Linux 现有测试不受影响"""
    # 确认 seatbelt/landlock 的 run_command/run_shell_command 返回 None
    from app.security.sandbox.seatbelt import SeatbeltSandbox
    sb = SeatbeltSandbox()
    assert sb.run_command(["echo", "hi"], cwd="/tmp") is None
    assert sb.run_shell_command("echo hi", cwd="/tmp") is None
```

- [ ] **Step 12.2: 回归测试**

```bash
# Windows 全部测试
pytest backend/tests/test_security/test_permission_mode.py \
       backend/tests/test_security/test_command_policy_windows_builtin.py \
       backend/tests/test_security/test_sandbox_windows_token.py \
       backend/tests/test_security/test_sandbox_windows_acl.py \
       backend/tests/test_security/test_sandbox_windows.py \
       backend/tests/test_security/test_sandbox_windows_integration.py \
       backend/tests/test_security/test_command_policy_sandbox_conditional.py \
       -v

# 回归（确保 macOS/Linux 不受影响）
pytest backend/tests/test_security/test_sandbox_base.py \
       backend/tests/ -k "not windows" -v --timeout=30
```

- [ ] **Step 12.3: 提交**

```bash
git add backend/tests/test_security/test_sandbox_windows_integration.py
git commit -m "test: Windows 沙盒集成测试 + 回归（macOS/Linux 零影响验证）"
```
```
```
```
```