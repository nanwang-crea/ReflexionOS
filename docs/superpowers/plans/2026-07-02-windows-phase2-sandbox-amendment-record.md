# 实现计划修正记录（v2）

基于 Codex 审查 6 条意见，对 `2026-07-02-windows-phase2-sandbox-implementation-plan.md` 的修正方向纪录。本文件是 **修正记录**，不是重写后的 plan；每项修正需用户按"方向成立 / 与仓库一致 / 能落地"三维确认后，再统一回写到 plan。

---

## 修正 1：Task 0 — resolve_action 对 NETWORK_OUT 的真实职责

**对应问题:** [P1] 修正记录之前说 "_needs_network_approval 先截住"，但真实代码正好相反。

**链路澄清：**

当前网络审批真实链路（已验证 [shell_tool.py:165-182](backend/app/tools/shell_tool.py#L165-L182)）：

```
1. command.effect_category = NETWORK_OUT
2. evaluate() 调 resolve_action(..., NETWORK_OUT) → 返回 EFFECT_ACTION_MAP[NETWORK_OUT] = REQUIRE_APPROVAL
3. decision.action = REQUIRE_APPROVAL
4. execute() 先调 _needs_network_approval(decision)：
   判断 effect_category == NETWORK_OUT → 直接 return False（不是"截住"，是"跳过前置网络审批"）
5. 继续走 decision.action == REQUIRE_APPROVAL → 走本地审批链
```

所以 NETWORK_OUT 命令**不是**被独立审批截住的，它走的就是 `decision.action == REQUIRE_APPROVAL` 这条通用审批链。

**PermissionMode 的真实职责边界：**

- PermissionMode 仅控制**本地操作审批**（READ_ONLY / WRITE_PROJECT / DESTRUCTIVE 等），**不涉及网络命令**。
- NETWORK_OUT 不受 PermissionMode 影响：无论在 ASK/AUTO/YOLO 下，都返回 REQUIRE_APPROVAL（来自 EFFECT_ACTION_MAP）。
- resolve_action 中 YOLO 分支对 NETWORK_OUT 的 `return REQUIRE_APPROVAL` **必须保留**，否则 YOLO 下 NETWORK_OUT 会被 ALLOW。

**Task 0 改动：** 代码不动，只改注释。

- `permission_mode.py:resolve_action` 文档改为：
  ```python
  """根据权限模式和效果分类决定最终动作。

  NETWORK_OUT 不受 PermissionMode 影响（无论 ASK/AUTO/YOLO
  都返回 REQUIRE_APPROVAL），因为网络命令的审批完全由 EFFECT_ACTION_MAP 定义。
  """
  ```
- YOLO 分支里的 `if category == EffectCategory.NETWORK_OUT: return CommandAction.REQUIRE_APPROVAL` **保留**，但加注释说明："确保 YOLO 下网络不被 ALLOW——网络审批不受 YOLO 影响"。
- 单测注释改为："YOLO 本地全放行；NETWORK_OUT 不受 PermissionMode 影响，始终走 EFFECT_ACTION_MAP 映射。"

---

## 修正 2：Task 5/6 顺序安全 — stub 阶段不得触发真实接线

**对应问题:** [P1] Task 5 降成 stub 后，若 Task 7/9/10 先接线，系统会进入"有沙盒但无真实隔离"的中间态。

**修复：硬性约束：Task 7/9/10 必须延后到 Task 6 完成后。**

修改后任务顺序：

```
Phase 1（可独立完成，不合并到主线）：
  Task 0: PermissionMode + resolve_action
  Task 1: SandboxRunResult + run_command/run_shell_command 框架
  Task 2: Windows builtin 分类 + runas
  Task 3: Restricted Token
  Task 4: Windows ACL
  Task 5: WindowsSandbox Unelevated stub（subprocess.Popen，不调真实 Win32 API）

Phase 2（真实隔离）：
  Task 6: WindowsSandbox Elevated + real CreateProcessAsUserW

Phase 3（须 Task 6 PASS 后才可合并）：
  Task 7:  工厂接线（WindowsSandbox 加入 providers）
  Task 8:  resolve_action 接入 CommandPolicy
  Task 9:  白名单条件化（sandbox_available）
  Task 10: ShellTool 接线（run_command/run_shell_command）
  Task 11: 前后端通路
  Task 12: 集成测试 + 回归
```

**验收标准补充：**

- Task 5："stub 阶段。完成后不合并到主线，仅本地/CI 单测通过即可。"
- Task 6："CreateProcessAsUserW 真实隔离已验证。此任务 PASS 后 Phase 3 可安全合并。"

---

## 修正 3：Task 5/10 — timeout 正确 API + 责任边界

**对应问题:** [P2] 之前写 `Popen(argv, ..., timeout=timeout)` —— Popen 构造器无 timeout 参数。

**落地方案：**

```python
# Task 5: _exec_in_sandbox 接收 timeout，传给 proc.communicate(timeout=timeout)
def _exec_in_sandbox(self, argv, cwd, token, timeout=300, use_shell=False):
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate(timeout=timeout)  # timeout 在这里
    ...

# Task 10: ShellTool 调 run_command 时传入 timeout
if self.sandbox_available and hasattr(self.sandbox, 'run_command'):
    result = self.sandbox.run_command(
        argv, cwd=cwd, timeout=timeout, allow_network=allow_network,
    )
```

**run_command/run_shell_command 签名加 `timeout: int = 300` 参数。**

**Task 6 的 CreateProcessAsUserW：** pywin32 本身无 timeout 参数，需 `WaitForSingleObject(process_handle, timeout_ms)`。

**影响 Task:** 5（加 timeout 参数到 _exec_in_sandbox）、10（调用时传 timeout）

---

## 修正 4：Task 9 — 测试代码改为显式构造 + win32 平台固定

**对应问题:** [P2] _make_policy 不存在、from conftest import 也不存在、默认 ShellSecurity() 不稳定。

**改法：**

在 `backend/tests/test_security/test_command_policy_sandbox_conditional.py` 中显式构造 CommandPolicy，并按照现有 `test_command_policy.py:29` 的模式指定 `platform_name="win32"` 来稳定白名单行为：

```python
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

**注意：** 白名单门禁是 `result.has_meta and self.shell_security._is_windows() and not self.sandbox_available`。`_is_windows()` 检查 `self.shell_security.platform == "win32"`。因此当 `platform_name="win32"` 时此分支才会触发；Non-Windows 宿主机上 `ShellSecurity()` 默认平台不是 win32，白名单门禁不会进入，测试会跳过该分支。

**影响 Task:** 9（仅测试代码）

---

## 修正 5：Task 11 — 前端 DTO 层 + 审批恢复路径

**对应问题:** [P2] 漏了 `sessionConversationWebSocket.ts` 的 DTO 转发层和 `agent_service.py:918` 的审批恢复路径。

**需要补：**

```
前端：
- frontend/src/services/sessionConversationWebSocket.ts
    - DTO 层：新增 PermissionMode type 序列化/反序列化
    - 事件处理：session:permission_mode_changed → 通知 UI
    - 消息发送：setPermissionMode 走 WebSocket

后端：
- agent_service.py:918 审批恢复路径
    - 该调用点缺 session_id → 无法读 DB
    - 从 pending_turn 的 run_id 回溯到 session_id，再读 permission_mode
```

**明确不改：** 不走 REST PATCH；不做全局状态管理；不做独立前端 store。

**影响 Task:** 11（加 1 个前端文件 + 1 个后端调用点）

---

## 修正 6：Task 2 — platform_overrides 清理降级

**对应问题:** [P3] 强制删 platform_overrides 字段是额外 churn。

**改动：** 从"强制删除"降级为"可选清理"，标注为死字段。

```python
# Step 2.3 的 registry 改动改为：
#
# 1. ESCALATE 命令列表加 "runas"
# 2. 新增 Windows builtin 直接注册（register 调用，不改 platform_overrides）
# 3. platform_overrides 保持不动（死字段，但不影响正确性，本轮不拆）
```

**影响 Task:** 2（删 delete_platform_overrides 的单测用例）

---

## 改动影响总表

| 修正 | 原 Task | 操作 | 说明 |
|------|---------|------|------|
| 1 | Task 0 | 改注释/文档 | 代码不动；澄清 NETWORK_OUT 走的是本地审批链而非独立审批链 |
| 2 | Task 5 | 标 stub + 冻结合并 | 降为 Phase 1 stub，不合并到主线 |
| 2 | Task 6 | 重写 | 真实 CreateProcessAsUserW，补用户分流 |
| 2 | Task 7-12 | 延后 | 改为 Phase 3，必须 Task 6 通过后合并 |
| 3 | Task 5 | _exec_in_sandbox 加 timeout | 传给 proc.communicate()，非 Popen 构造器 |
| 3 | Task 10 | 调用时传 timeout | 同步 run_command 的超时由 sandbox 内部处理 |
| 4 | Task 9 | 测试代码重写 | 显式构造 + ShellSecurity(platform_name="win32") |
| 5 | Task 11 | 加 2 个接线点 | 前端 DTO 层 + 后端审批恢复路径 |
| 6 | Task 2 | 降级 | platform_overrides 从删除改为标注死字段 |

---

## 三维审查要点

1. **方向成立？** stub → task6 再接线的三阶段拆分是否可行？Task 0 的 NETWORK_OUT 描述是否准确？
2. **与仓库一致？** ShellSecurity(platform_name="win32") 是否稳定覆盖白名单分支？_needs_network_approval(NETWORK_OUT)→False 后 decision.action 路径是否正确？
3. **能落到 plan？** 上述每项是改 task 的 step 还是改 task 的 scope？以当前 Plan 逐 task 回写是否可行？