# Windows 第二阶段沙盒设计文档

## 背景

### 现状（准确描述当前 Windows 行为）

Windows 第一阶段（见 `2026-07-01-windows-subprocess-eventloop-fix-design.md`）解决了"子进程能不能跑起来"的问题。当前 Windows 的命令准入是**分两条路径**的（`command_policy.py:168`）：

1. **shell 模式（`result.has_meta and _is_windows()`）**：命令含 shell 元字符（`&&`/`||`/`|`/`>` 等）时，进入**第一阶段严格白名单**——只放行 4 个纯读 git 子命令（status/log/diff/show）+ 命令链（`&&`/`||`），其余一律 DENY（`command_policy.py:168-259`）。所以 `cd frontend && npm install`、`dir | findstr foo`、`git status > out.txt` 这类**带元字符的命令**今天会被拒绝。
2. **argv 模式（无元字符）**：普通单条命令（`npm install`、`python --version`、`git add .`）**不进白名单**，走 effect registry 分类。`WRITE_PROJECT` 在 `EFFECT_ACTION_MAP` 里仍是 `ALLOW`（`effect_category.py:39-47`），所以这些命令今天在 Windows 上**能跑通**（现有测试 `test_command_policy.py:85-122`、`test_shell_tool.py:61-66` 已覆盖）。

**问题的核心**：无论走哪条路径，Windows 都**没有任何 OS 级隔离**——命令一旦放行就是裸跑，写文件、连网络都不受约束。白名单只是"堵住带元字符的命令"，不是隔离。

而 macOS/Linux 走的是完全不同的路径：通过 `SandboxProvider` 抽象（seatbelt/landlock）提供 **OS 级强隔离**——命令可以是任意的，因为文件写入、网络访问都被内核级沙盒兜住了。

### 问题定义

Windows 缺少两样东西，导致它和 macOS/Linux 的能力与安全模型严重不对等：

1. **没有 OS 级隔离**：Windows 没有 landlock/seatbelt 的现成等价物，命令放行后裸跑。这也是第一阶段只能用白名单"堵住带元字符命令"的原因——没有沙盒兜底，就不敢放开 shell 命令链/重定向/管道。
2. **没有分级权限模型**：用户无法选择"这个会话我要严格审批"还是"完全放开"。现有 `CommandAction`（ALLOW/REQUIRE_APPROVAL/DENY）是按命令危险等级自动判定的，用户不能整体切换基调。

### 参考实现

调研了 OpenAI Codex 的 Windows 原生沙盒方案，它用 **Restricted Token + Synthetic SID + ACL 文件边界 + Windows 防火墙** 实现了不依赖 WSL/虚拟机的原生隔离，分 Elevated（需管理员）和 Unelevated（不需管理员）两档。本设计对齐该方案。

---

## 目标

### 做什么

1. **Windows 原生沙盒**：新增 `WindowsSandbox`，用 pywin32 调 Win32 API 实现文件级 OS 隔离，让 Windows 也能"放开命令 + 沙盒兜底"，能力对齐 macOS/Linux。
   - **文件隔离（真边界，两档均生效）**：Restricted Token + ACL，deny-by-default 写入边界。这是本沙盒对外承诺的核心安全保证。
   - **网络控制（分档，不统一承诺硬隔离）**：网络审批链对 `often_needs_network` 命令（npm/裸 git）做预审批；对 NETWORK_OUT 命令（curl/wget/git push）靠运行期拒绝回执。**Elevated** 档用防火墙按 SID 阻断出站，运行期拒绝可靠（接近硬隔离）；**Unelevated** 档只有 proxy 环境变量辅助，NETWORK_OUT 命令可绕过 → **存在已知网络缺口**（见 3.6）。诚实边界：网络硬隔离仅 Elevated 可靠。
2. **放开 shell 命令**：沙盒可用时，旁路第一阶段 `has_meta` 白名单，让 `cd && npm`、重定向、管道等命令能进入沙盒执行。白名单降级为"沙盒不可用时的兜底边界"（见"边界与降级"）。
   - **前置：补 Windows builtin 分类**。旁路白名单后，`cd`/`dir`/`findstr`/`type`/`copy`/`move`/`cls`/`set` 等 cmd.exe 内建命令会落到分类器，而现有 `command_effect_registry.py` 只登记了 Unix 命令（`ls`/`cat`/`grep`…）+ 少量 Windows 破坏类（`del`/`rd`…），这些 builtin 会被判成 UNKNOWN → AUTO 下走审批，用户故事里"直接执行"失真。必须先给 registry 补齐 Windows builtin 的 `EffectCategory`（见 3.8）。
3. **三类权限模式**：新增全局 `PermissionMode`（ASK / AUTO / YOLO），让用户切换整个会话的审批基调，与命令危险等级兜底结合。**YOLO = 本地操作放开，不等于联网放开**——网络审批链在任何模式下都保留（见方案二）。
4. **跨平台隔离**：所有 Windows 特殊逻辑封装在独立文件 + `if sys.platform == "win32"` 分支内，macOS/Linux 现有代码路径**零改动**。

### 不做什么

1. 不改 macOS/Linux 的 seatbelt/landlock 实现和执行路径。
2. 不引入 Rust helper 子进程（用 pywin32 直接在 Python 内调 API）。
3. 不做进程级资源限制（CPU/内存配额，Job Object）——本阶段只做文件隔离 + 网络审批控制。
4. 不做持久化的跨会话信任规则存储（复用现有 `SessionTrustStore` 的会话内内存存储）。
5. 不改现有网络审批链路的机制（`_needs_network_approval` + elevation 回执 + `sandbox_network` 信任），只复用；PermissionMode 不覆盖网络审批。
6. 不把 PermissionMode 加入 shell tool schema（防止 LLM 自选模式），只做会话级配置。
7. 不承诺 Unelevated 档的网络硬隔离（环境变量仅辅助）。

---

## 用户故事

### 开发者视角

**当前（第一阶段）**：
```
用户输入: cd frontend && npm install
结果: ✗ 白名单拒绝（含 && 走 shell 白名单，cd/npm 非 git → DENY）

用户输入: npm install（无元字符，走 argv）
结果: ✓ 今天已能跑（WRITE_PROJECT → ALLOW），但裸跑无隔离
```

**第二阶段（期望，沙盒可用）**：
```
# 模式：AUTO（替我审批，默认）
用户输入: cd frontend && dir
结果: ✓ 旁路白名单 → registry 认得 cd(READ_ONLY)/dir(READ_ONLY) → 直接放行进沙盒执行
      （前提：已给 registry 补 Windows builtin 分类；否则 cd/dir 判 UNKNOWN 走审批）

用户输入: npm install（needs network）
结果: ⚠ 弹网络审批（独立链路，不受 mode 影响）→ 批准后沙盒内联网执行
      → 首次批准写入 SessionTrustStore(sandbox_network:*)，后续自动放行

# 模式：YOLO（本地放开，≠ 联网放开）
用户输入: cd frontend && rd /s /q build（本地破坏性操作，cmd.exe 原生）
结果: ✓ 不弹本地审批（DESTRUCTIVE 在 YOLO→ALLOW），直接沙盒内执行（写不出工作区外）

用户输入: npm install（needs network）
结果: ⚠ 仍弹网络审批！YOLO 只旁路本地审批，网络闸门保留
      → 首次批准后写信任，后续自动放行

用户输入: runas / 提权命令
结果: ✗ DENY（ESCALATE 是不可破的底线，任何模式都拒绝）

# 沙盒不可用时（如 Wine 环境，降级到 NullSandbox）
白名单: 恢复生效（作为唯一边界，has_meta 命令重新受限）
模式 YOLO: ✗ 自动禁用并提示（无隔离 + 不审批 = 裸奔，不允许）
模式 AUTO/ASK: ✓ 仍可用（危险命令靠审批兜底 + 白名单）
```

---

## 方案设计

### 一、三个正交维度

本设计涉及三个**互相独立**的维度，必须分清（早先版本只写了两个，漏掉了独立的网络审批链路，导致 YOLO 语义与现有代码冲突）：

| 维度 | 是什么 | 由谁决定 | 作用点 |
|------|-------|---------|-------|
| **本地操作审批**（决策层） | 非网络命令要不要问用户 | `PermissionMode` × `EffectCategory` | `execute()` 的 `decision.action` |
| **网络审批**（独立链路） | 命令要联网时要不要问用户 | `_needs_network_approval()` + 运行期 elevation | `execute()` line 156-158 + 运行期回执 |
| **沙盒隔离**（执行层） | 命令跑起来后能写哪些文件 | 平台自动（Windows→WindowsSandbox） | `_execute_argv/_execute_shell` 的 `run_command` |

**关键点 1**：即使权限模式是 YOLO，沙盒的**文件隔离**依然生效——命令能跑，但写不出工作区外。

**关键点 2（修正）**：`PermissionMode` **只管本地操作审批这一个维度**。网络审批是**独立链路**，`PermissionMode` 不覆盖它——**YOLO 也要走网络审批**（预审批命中的 `often_needs_network`/`requires_network` 命令，YOLO 下仍弹）。产品语义：**YOLO = 本地放开，≠ 联网放开**。理由：网络审批链独立于 `decision.action`，即便 YOLO 把本地动作全放行，预审批和运行期回执仍在。注意这条链对 NETWORK_OUT 命令的实际约束力，两档不同（见 3.6：Elevated 可靠、Unelevated 有缺口）。

#### 现有网络审批链路（必须保留，不被 PermissionMode 改写）

现有 `shell_tool.py` 有一条**独立于 `decision.action`** 的网络审批链路，本设计**原样保留**：

1. **预审批**（`execute()` line 156-158）：`_needs_network_approval()` 命中 → 直接返回 `sandbox_network_elevation`，**不看 `decision.action`**。**命中条件很窄**：仅 `requires_network=true` 或命令 `often_needs_network`（`shell_tool.py:174-180`）。**注意 `effect_category == NETWORK_OUT` 会 `return False`**（`shell_tool.py:168-169`）——`curl`/`git push` 这类不走预审批，靠第 2 步兜。
2. **运行期回执**（`_create_approval_result` line 638-657）：沙盒执行时命中 `NETWORK_DENIED` / 路径拒绝 → 返回 `sandbox_network_elevation` / `sandbox_path_elevation` 二次审批。这是 NETWORK_OUT 命令的**实际**网络闸门（仅 Elevated 档可靠，Unelevated 可被绕过，见 3.6）。
3. **信任放行**（`SessionTrustStore`）：用户批准一次 → 写入 `sandbox_network:*` → 后续 `_needs_network_approval()` 命中 line 170-172 自动返回 False，不再弹窗。

`PermissionMode` 的 `resolve_action` **只作用于第 0 步的 `decision.action`（本地操作），这三条网络链路一行不改**。

#### 三个维度在调用链中的位置

```
execute(args)
  → CommandPolicy 分类命令 → decision（含 EffectCategory）
  → 【本地审批】resolve_action(category, mode, sandbox_available) → decision.action
       ├─ DENY          → 直接拒绝（含 ESCALATE、YOLO+无沙盒）
       ├─ REQUIRE_APPROVAL → 弹本地审批 / 查 SessionTrustStore
       └─ ALLOW         → 继续
  → 【网络审批】_needs_network_approval(decision, requires_network)  ← 独立！任何 mode 都跑
       └─ 命中 → 弹 sandbox_network_elevation（YOLO 也不例外）
  → _execute_decision → _execute_argv/_execute_shell
       → 【沙盒隔离】sandbox.run_command(...)  ← 文件边界在这里
       → 运行期若 NETWORK_DENIED → 弹网络 elevation 回执
```

**本设计的决策层改动仅一处**：把 `execute()` 里决定 `decision.action` 的 `EFFECT_ACTION_MAP` 查表（当前在 `command_policy.py` 内），替换为调用 `resolve_action(category, mode, sandbox_available)`。网络审批链路（`_needs_network_approval` 及 elevation）保持不动。

### 二、本地操作审批（决策层）

#### PermissionMode 枚举

```python
# backend/app/security/permission_mode.py（新增）
class PermissionMode(str, enum.Enum):
    ASK = "ask"      # 请求批准：所有非只读的本地操作都问用户
    AUTO = "auto"    # 替我审批（默认）：按危险等级自动判定 + 会话信任放行
    YOLO = "yolo"    # 本地放开：本地操作直接 ALLOW（提权除外；网络仍走独立审批）
```

#### 三个模式的决策规则（仅本地操作，不含网络审批链路）

给定一条命令的 `EffectCategory`，`decision.action` 由模式决定。**注意：NETWORK_OUT 这行只是本地审批维度的取值；命令实际能否联网由独立的网络审批链路决定，与此表无关。**

| EffectCategory | ASK | AUTO（现状） | YOLO |
|----------------|-----|-------------|------|
| READ_ONLY | ALLOW | ALLOW | ALLOW |
| WRITE_PROJECT | REQUIRE_APPROVAL | ALLOW | ALLOW |
| CODE_GEN | REQUIRE_APPROVAL | REQUIRE_APPROVAL | ALLOW |
| NETWORK_OUT | REQUIRE_APPROVAL | REQUIRE_APPROVAL | ALLOW（本地维度放行，但仍会被网络审批链拦） |
| WRITE_SYSTEM | REQUIRE_APPROVAL | REQUIRE_APPROVAL | ALLOW |
| DESTRUCTIVE | REQUIRE_APPROVAL | REQUIRE_APPROVAL | ALLOW |
| UNKNOWN | REQUIRE_APPROVAL | REQUIRE_APPROVAL | ALLOW |
| **ESCALATE** | **DENY** | **DENY** | **DENY** ← 不可破 |

- **AUTO 列 = 现有 `EFFECT_ACTION_MAP` 的行为**，保持不变，是默认模式。
- **ESCALATE 永远 DENY**，任何模式都不例外——硬编码的安全底线。
- **降级保护**：沙盒降级到 `NullSandbox` 时，YOLO 被禁用（`resolve_action` 检测到无沙盒 + YOLO → DENY + 特殊标记，上层提示切 AUTO/ASK）。
- **YOLO 的 NETWORK_OUT = ALLOW 只影响本地审批维度**；命令真要联网时，`_needs_network_approval()` 仍会拦下弹审批。两者不矛盾——本地放行不代表网络放行。

#### 决策函数

```python
# permission_mode.py
def resolve_action(
    category: EffectCategory,
    mode: PermissionMode,
    sandbox_available: bool,
) -> CommandAction:
    """根据权限模式 + 命令危险等级 + 沙盒可用性，判定【本地操作】动作。

    仅决定 decision.action（本地审批维度）。网络审批由独立链路负责，本函数不涉及。
    ESCALATE 恒为 DENY。YOLO 在沙盒不可用时返回 DENY（上层据此提示 YOLO 已禁用）。
    """
    # 1. 提权命令：任何模式都拒绝（不可破的底线）
    if category == EffectCategory.ESCALATE:
        return CommandAction.DENY

    # 2. YOLO 模式必须有沙盒兜底，否则拒绝
    if mode == PermissionMode.YOLO:
        if not sandbox_available:
            return CommandAction.DENY  # 上层据此提示"沙盒不可用，YOLO 已禁用"
        return CommandAction.ALLOW

    # 3. ASK 模式：非只读一律审批
    if mode == PermissionMode.ASK:
        return (CommandAction.ALLOW if category == EffectCategory.READ_ONLY
                else CommandAction.REQUIRE_APPROVAL)

    # 4. AUTO 模式：沿用现有危险等级映射
    return EFFECT_ACTION_MAP[category]
```

`EFFECT_ACTION_MAP`（`effect_category.py`）保持不变——AUTO 模式直接复用它，避免改动现有行为。

### 三、沙盒隔离（执行层）

#### 3.1 接口扩展：SandboxProvider 新增 run_command

**问题**：现有接口 `wrap_command(argv, ...) -> list[str]` 是"包装器模型"——把命令包成新 argv（如 `bwrap ... git status`），交给上层 `subprocess.run` 执行。这适合 seatbelt/landlock，但**不适合 Windows Restricted Token**：后者必须亲自调 `CreateProcessAsUserW(restricted_token, ...)` 启动进程，无法只返回一个 argv。

**解决**：给 `SandboxProvider` 加一个**可选**方法，语义是"由沙盒自己负责执行"：

```python
# backend/app/security/sandbox/base.py（改：新增方法 + 结果类型）
from dataclasses import dataclass

@dataclass
class SandboxRunResult:
    """沙盒自行执行命令的结果。"""
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False

class SandboxProvider(ABC):
    # ... 现有 is_available / wrap_command / wrap_shell_command 不变 ...

    def run_command(
        self,
        argv: list[str],
        *,
        cwd: str,
        timeout: int,
        env: dict[str, str],
        allowed_paths: list[str] | None = None,
        allow_network: bool = False,
    ) -> SandboxRunResult | None:
        """由沙盒自身执行【argv 模式】命令并返回结果。

        默认返回 None，表示"我不接管执行，请上层走 wrap_command + subprocess 老路径"。
        seatbelt/landlock 不重写此方法（继承默认 None）→ 行为零改动。
        WindowsSandbox 重写此方法 → 用 CreateProcessAsUserW(restricted_token, argv) 亲自执行。
        """
        return None

    def run_shell_command(
        self,
        command: str,
        *,
        cwd: str,
        timeout: int,
        env: dict[str, str],
        allowed_paths: list[str] | None = None,
        allow_network: bool = False,
    ) -> SandboxRunResult | None:
        """由沙盒自身执行【shell 模式】命令（含 &&/||/|/> 等元字符）并返回结果。

        接收原始 shell 命令字符串（不含 cmd.exe /c 包装）。默认返回 None（不接管）。
        WindowsSandbox 重写：内部包装成 `cmd.exe /c "<command>"` 作为 argv，
        再用 CreateProcessAsUserW(restricted_token, ...) 在受限令牌下执行。
        seatbelt/landlock 不重写（继承 None）→ macOS/Linux 零改动。
        """
        return None
```

**为什么区分 argv / shell 两个方法**：
- 真实执行路径本就分两支：argv 模式走 `_sync_subprocess_run`（`subprocess.run(argv, shell=False)`），shell 模式走 `_sync_subprocess_run_shell`（`cmd.exe /c "{command}"`, `shell=True`，见 `shell_tool.py:445-467`）。沙盒必须对应接管这两支，否则 quoting/shell 选择语义会错乱。
- **WindowsSandbox 的 shell 变体**：不复用宿主 `shell=True`，而是自己把 `command` 包成 `["cmd.exe", "/c", command]` 作为 argv，交给 `CreateProcessAsUserW(restricted_token, ...)` 执行——这样 cmd.exe 本身也跑在受限令牌下，builtin（`dir`/`copy`）和链式命令（`&&`）都受同一 ACL 边界约束。
- **为什么不接 raw string 直接 shell=True**：`subprocess.run(shell=True)` 无法指定 token，起不到隔离作用。必须显式包 `cmd.exe /c` 再走 `CreateProcessAsUserW`。
- **为什么不合成一个方法**：合成需要额外传 `is_shell` 标志分流，两个方法更直白，且与上层 `_execute_argv` / `_execute_shell` 的分支一一对应。
- seatbelt/landlock **两个方法都不重写**——继承默认 `None`，上层看到 None 就走现有 `wrap_command` / `wrap_shell_command` 路径，macOS/Linux 零改动。
- 加新方法而非改 `wrap_command`，保证向后兼容。

#### 3.2 上层调用改造（shell_tool.py）

`_execute_argv` 的 Windows 分支改造思路——先问沙盒要不要接管执行：

```python
# _execute_argv 内，Windows 分支（示意）
if sys.platform == "win32":
    # 先尝试让沙盒自己执行（WindowsSandbox 会接管）
    run_result = self.sandbox.run_command(
        argv, cwd=cwd, timeout=timeout, env=self._build_env(),
        allowed_paths=list(self.path_security.allowed_base_paths) + (sandbox_extra_paths or []),
        allow_network=(sandbox_allow_network or effect_category == EffectCategory.NETWORK_OUT),
    )
    if run_result is not None:
        # 沙盒接管了执行 → 用它的结果（编码降级复用 _decode_windows_output）
        return self._build_result_from_sandbox(run_result, argv, timeout)
    # 沙盒没接管（如 NullSandbox 降级）→ 走现有线程池 subprocess 路径
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, self._sync_subprocess_run, argv, cwd, timeout)
else:
    # macOS/Linux：完全不变
    ...
```

- macOS/Linux 分支的 `else` 完全不动。
- Windows 分支：`run_command` 返回 None（NullSandbox 降级场景）时，回落到第一阶段已实现的 `_sync_subprocess_run` 线程池路径，保证降级可用。

`_execute_shell` 的 Windows 分支同理，改调 `run_shell_command`（接管 shell 模式）：

```python
# _execute_shell 内，Windows 分支（示意）
if sys.platform == "win32":
    run_result = self.sandbox.run_shell_command(
        command, cwd=validated_cwd, timeout=timeout, env=self._build_env(),
        allowed_paths=..., allow_network=...,
    )
    if run_result is not None:
        return self._build_result_from_sandbox(run_result, command, timeout)
    # 沙盒没接管 → 回落现有 _sync_subprocess_run_shell（cmd.exe /c 线程池路径）
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, self._sync_subprocess_run_shell, command, validated_cwd, timeout)
else:
    ...  # macOS/Linux 不变
```

注意：第一阶段 `_execute_shell` 的 Windows 分支目前对 `NETWORK_OUT` 硬拒绝（`shell_tool.py:530-534`）。本阶段沙盒可用时，这个硬拒绝应改为交给沙盒 + 网络审批链处理（沙盒不可用降级时保留硬拒绝）。此改动列入 implementation-plan。

#### 3.3 WindowsSandbox 两档

| 档位 | 触发条件 | 文件隔离（真边界） | 网络控制 |
|------|---------|------------------|---------|
| **Unelevated** | 默认（无管理员权限） | Restricted Token + ACL 写入边界 ✓ | 预审批可拦 `often_needs_network` 命令（npm/裸 git）；但 NETWORK_OUT（curl/wget/git push）**既不走预审批、运行期又可绕过 proxy → 无可靠网络闸门**（已知缺口，见 3.6）|
| **Elevated** | 检测到管理员权限 | 同上 + 专用沙盒用户 ACL ✓ | 默认禁网 + 网络审批链；批准后用 Online 用户 + 防火墙按 SID 阻断非授权出站（接近硬隔离） |

运行时通过 `is_elevated()` 检测当前进程是否有管理员权限，自动选档。

**两档的核心区别与相同点**：
- **相同**：文件隔离都是真边界（Token+ACL），两档均可靠。
- **不同（网络）**：Elevated 用防火墙按 SID 阻断出站，运行期拒绝可靠（接近硬隔离）；Unelevated 无防火墙，NETWORK_OUT 命令的运行期拒绝可被 curl/git 绕过。
- **诚实声明**：本沙盒承诺的安全保证是**文件隔离**（两档可靠）；**网络隔离仅 Elevated 档可靠**，Unelevated 对 NETWORK_OUT 存在已知缺口（见 3.6，可选增强列入 plan）。

#### 3.4 文件写入边界（ACL）

```
默认可写（ACL GRANT + sandbox-write SID）：
  1. %TEMP%\reflexion-sandbox\<session_id>\   ← 沙盒临时区（每会话独立）
  2. 工作区目录（path_security.allowed_base_paths）

其余全部 DENY（deny-by-default，靠 Restricted Token 的 sandbox-write Synthetic SID 实现——
  只有 ACL 中显式含 sandbox-write SID 的目录才可写）

额外可写扩展（可选）：
  复用现有 shell_tool.py 的 sandbox_extra_paths 参数通道，追加到 allowed_paths
```

- 读权限：Unelevated 继承当前用户；Elevated 异步授予沙盒用户对常用系统目录（`C:\Windows`、`C:\Program Files` 等）的读/执行权限。
- 写权限：deny-by-default，只有上述白名单目录显式 GRANT。

#### 3.5 专用沙盒用户（仅 Elevated）

- **固定两个复用账户**：`ReflexionSandboxOffline`（无网络）/ `ReflexionSandboxOnline`（有网络），不带 session_id。
- **幂等创建**：服务启动时检测账户是否存在，不存在才创建；用完**不删**（长期账户）。
- **清理策略**：不扫描/清理残留用户（账户固定复用，不存在残留问题）。真正需要清理的是 `%TEMP%\reflexion-sandbox\<session_id>\` 临时目录——在会话结束 / 服务启动时扫描清理。

#### 3.6 网络控制（审批链为主，隔离手段为辅）

**网络审批不是单一"前置闸门"，而是两段机制**（对齐 `_needs_network_approval()` 的真实逻辑，`shell_tool.py:165-182`）：

**第一段——预审批（前置，仅覆盖显式/启发式联网）**：
- 触发条件（`shell_tool.py:174-180`）：调用方显式传 `requires_network=true`，**或**命令的 registry entry 标了 `often_needs_network`（如裸 `git`、`npm`）。命中 → `execute()` 直接返回 `sandbox_network_elevation` 审批请求。
- **关键：`effect_category == NETWORK_OUT` 时 `_needs_network_approval()` 直接 `return False`（`shell_tool.py:168-169`）**。也就是说 `curl`/`wget`/`git push`（被分类成 NETWORK_OUT）**不走预审批**。这是现有代码的真实行为，不是笔误。

**第二段——运行期拒绝回执（NETWORK_OUT 命令的实际闸门）**：
- NETWORK_OUT 命令直接进入执行，由**沙盒在运行期拒绝联网**（Elevated 防火墙 SID 阻断 / Unelevated 无联网上下文）→ 命中 `NETWORK_DENIED` → `_create_approval_result` 返回 `sandbox_network_elevation` 二次审批（`shell_tool.py:638-657`）。
- 用户批准 → 写 `SessionTrustStore(sandbox_network:*)` → 重试时联网上下文放行。

**批准后的隔离手段（两档不同）**：
- **Elevated**：用 `ReflexionSandboxOnline` 用户执行 + 防火墙规则精确控制，未授权出站被 SID 级阻断（接近硬隔离），运行期拒绝是**可靠**的。
- **Unelevated**：无防火墙，只注入 `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` 环境变量作辅助，`curl`/`git` 等可绕过——**运行期拒绝不可靠**。

**诚实边界（本设计明确承认的缺口）**：
- Unelevated 档**既没有网络预审批（NETWORK_OUT 被 `return False` 跳过），运行期拒绝又能被绕过**——所以 Unelevated 对 `curl http://...` 这类命令**没有可靠的网络闸门**。这是已知限制，不能宣称"默认禁网"。
- 若要在 Unelevated 也堵住 NETWORK_OUT，需要**新增专门策略**（例如：在 `resolve_action` 之外，Windows Unelevated + NETWORK_OUT + 未信任 → 强制预审批），此增强列入 implementation-plan 评估，本阶段先如实标注为缺口。
- 本沙盒对外承诺的安全保证是**文件隔离**（两档均可靠）；网络隔离仅 Elevated 档可靠。

#### 3.7 白名单旁路（沙盒可用时）

第一阶段的 `has_meta` 白名单（`command_policy.py:168-259`）在**沙盒可用时旁路**，让 shell 命令链/重定向/管道能进入沙盒执行；沙盒不可用时**恢复生效**作为兜底边界。

改造 `command_policy.py:168` 的条件判断：

```python
# 当前：
if result.has_meta and self.shell_security._is_windows():
    # ... 第一阶段严格白名单 ...

# 改造后：白名单仅在"Windows + has_meta + 沙盒不可用"时生效
if result.has_meta and self.shell_security._is_windows() and not sandbox_available:
    # ... 保留第一阶段严格白名单（作为无沙盒时的兜底边界）...
# 沙盒可用时：has_meta 命令跳过白名单，走 effect registry 分类 → shell 模式进沙盒
```

- `sandbox_available` 由 `CommandPolicy` 从注入的 sandbox provider（`sandbox.is_available()`）获得，或由上层传入。
- 旁路后，`has_meta` 的 shell 命令按 effect registry 分类（`most_dangerous`，需先补 Windows builtin，见 3.8），再经 `resolve_action` 判本地审批，最后进沙盒 `run_shell_command`（shell 模式，见 3.1）执行。
- **对现有测试的影响**：`TestWindowsShellWhitelistDenied`（`test_command_policy.py:683-718`）等钉死"非 git → DENY"的用例，只在 `sandbox_available=False` 时成立。需改写为条件化：沙盒不可用路径断言 DENY，沙盒可用路径断言进入 effect registry 分类。详见"测试计划"。

#### 3.8 Windows builtin 命令分类（旁路白名单的前置）

**问题**：旁路白名单后，`has_meta` 的 shell 命令会按 segment 拆开，逐段过 `_classify_shell_command()`（`command_policy.py:680-713`）——每段 `shlex.split(posix=True)` 后查 `command_effect_registry`。但现有 registry（`command_effect_registry.py:52-295`）只登记了 Unix 命令（`ls`/`cat`/`grep`…）和少量 Windows 破坏/提权类（`del`/`rd`/`format`/`cmd`/`powershell`）。cmd.exe 的常用内建命令**一个都没有**，会被 `_classify_argv_command` 判成 UNKNOWN。

**后果**：`cd`/`dir`/`type`/`findstr` 在 AUTO 下被判 UNKNOWN → REQUIRE_APPROVAL，用户故事里"直接执行"落空；`copy`/`move`/`mkdir` 写操作也无法正确归到 WRITE_PROJECT。

**关键约束（对齐现有代码）**：分类器 `_classify_argv_command()`（`command_policy.py:617-649`）只消费 `entry.category` + `flag_overrides` + `subcommand_overrides`（+ shell interpreter override），**完全不读 `platform_overrides` 字段**——该字段虽在 `CommandEffectEntry`（`command_effect_registry.py:18`）定义、现有 Windows 段（`:291-295`）也传了，但 `lookup()`（`:43-46`）和分类器都没有任何解析逻辑，它是**当前未被消费的死字段**（现有 Windows 段传的值恰好等于 `category`，所以没暴露问题）。

因此本设计**不使用 `platform_overrides`**，直接用 `register(cmd, CommandEffectEntry(category=...))` 注册（与现有 Windows 段 `:280-295` 的实际生效方式一致——真正生效的是 `category`，不是 `platform_overrides`）。

**跨平台安全性说明**：直接注册会让这些命令名在所有平台的 registry 里可 lookup。逐一确认对 macOS/Linux 无害：
- `dir` 在 GNU coreutils 中确实存在，语义就是列目录 → 归 READ_ONLY，与 Unix 语义一致，不会误放行。
- `copy`/`move`/`xcopy`/`robocopy`/`ren`/`md`/`cls`/`chdir`/`findstr` 在标准 Unix 环境非标准命令，注册后只是多一条 lookup 命中，归类合理，不改变 Unix 上任何现有命令的判定。
- `cd`/`type`/`set`/`echo`/`mkdir`/`find`/`where`：`echo`/`find`/`where`/`mkdir` 现有 registry 已注册（READ_ONLY / WRITE_PROJECT），此处不重复注册以免覆盖；`cd`/`type`/`set`/`chdir` 为新增（Unix 下 `cd`/`type`/`set` 是 shell builtin，独立进程调用少见，归 READ_ONLY 无副作用）。
- 若后续担心污染 Unix registry，可在 `register` 前加 `if sys.platform == "win32"` 守卫（本阶段评估认为归类本身无害，不强制守卫；最终取舍在 implementation-plan 定）。

**解决**：给 `command_effect_registry.py` 的 `_register_defaults()` 直接注册一组 Windows builtin（跳过已注册的 `echo`/`find`/`where`/`mkdir`），按语义归类：

| builtin | EffectCategory | 是否新增 | 说明 |
|---------|---------------|---------|------|
| `cd` / `chdir` | READ_ONLY | **新增** | 切目录（cwd 由执行层校验，分类层视为只读）|
| `dir` / `type` / `findstr` / `tree` / `ver` / `cls` | READ_ONLY | **新增** | 列目录/看文件/查找/显示 |
| `set` | READ_ONLY | **新增** | 无参列变量视为只读（带 `=` 赋值仅影响子进程环境，不落盘，仍归 READ_ONLY）|
| `copy` / `xcopy` / `robocopy` / `move` / `ren` / `rename` / `md` | WRITE_PROJECT | **新增** | 写文件/目录（路径边界由沙盒 ACL 兜底）；`md` 是 `mkdir` 的 cmd 别名 |
| `echo` / `find` / `where` | READ_ONLY | 已注册（`:53-54`）| 不重复注册；cmd 下 `find`=文件搜串（类 grep），仍只读，语义兼容 |
| `mkdir` | WRITE_PROJECT | 已注册（`:88`）| 不重复注册 |
| `del` / `erase` / `rd` / `rmdir` / `format` | DESTRUCTIVE | 已登记（`:282-285`，`rmdir` 需补）| `del`/`erase`/`rd`/`format` 已有；`rmdir`（`rd` 全名）建议补 |

**注意事项**：
- `_classify_shell_command` 用的是 `shlex.split(..., posix=True)`——对 Windows 反斜杠路径（`cd C:\foo`）可能拆坏。本阶段先只保证 builtin **命令名**能被识别归类（`argv[0]`），参数层的 Windows 路径解析问题记为已知限制，若实测有误判在 implementation-plan 阶段处理（可能需要在 Windows 分支改用非 posix 拆分）。
- 归类只影响**本地审批维度**；实际写文件仍被沙盒 ACL 边界兜底，分类偏松不等于能越权写盘。
- 这组 builtin 用 `register(cmd, CommandEffectEntry(category=...))` 直接注册（**不用** `platform_overrides`——该字段无消费逻辑，见上）。跨平台无害性已逐条论证（见"跨平台安全性说明"）。
- **顺带修死字段（可选）**：现有 Windows 段（`:291-295`）传的 `platform_overrides={"win32": base_cat}` 是死代码，可在本次一并删除以免误导后人；若担心影响面，也可只加注释标注"未消费"。取舍在 implementation-plan 定。

**必须补 `runas` 为 ESCALATE**：用户故事和测试矩阵都要求 `runas`（Windows 提权命令）被 DENY，但现有 registry 的 ESCALATE 集合（`:259` sudo/su/eval/exec/…）和 Windows 段（`:281-290` 只有 cmd/powershell/pwsh）**都没有 `runas`**——不补的话它会 lookup 到 None → 判 UNKNOWN，AUTO 下走审批而非 DENY，安全承诺落空。需在 Windows 段（`:281-290`）加：

```python
("runas", EffectCategory.ESCALATE),   # 补：Windows 提权命令，必须 DENY
```

（`resolve_action` 对 ESCALATE 恒返回 DENY，见"二、决策函数"，任何模式不可破。）

### 四、文件结构

#### 新增（全部 Windows-only，不影响其他平台）

```
backend/app/security/
├── permission_mode.py              # 新增：PermissionMode 枚举 + resolve_action 决策函数
└── sandbox/
    ├── windows.py                  # 新增：WindowsSandbox(SandboxProvider) 主类，重写 run_command
    ├── windows_token.py            # 新增：Restricted Token 构造（pywin32 封装）
    ├── windows_acl.py              # 新增：ACL 文件写入边界设置
    ├── windows_firewall.py         # 新增：防火墙规则（仅 Elevated）
    └── windows_user.py             # 新增：专用沙盒用户幂等创建（仅 Elevated）
```

#### 修改

```
backend/app/security/sandbox/base.py       # 加 run_command 默认实现 + SandboxRunResult（不影响现有子类）
backend/app/security/sandbox/factory.py    # create_sandbox 加 Windows 分支（优先 WindowsSandbox，失败降级 NullSandbox）
backend/app/security/command_policy.py     # (1) has_meta 白名单加 not sandbox_available 条件（沙盒可用时旁路）
                                           # (2) 决定 decision.action 处调 resolve_action（传入 mode + sandbox_available）
backend/app/tools/shell_tool.py            # (1) _execute_argv/_execute_shell 的 Windows 分支加 run_command 调用（else 分支不动）
                                           # (2) ShellTool 构造/上下文接收会话级 permission_mode，传给 policy.evaluate
backend/app/security/effect_category.py    # 不改逻辑，仅可能新增 ESCALATE 相关注释
backend/app/security/command_effect_registry.py  # (1) 直接注册 Windows builtin（cd/dir/copy/...，不用死字段 platform_overrides，见 3.8）
                                           # (2) 补注册 runas → ESCALATE、rmdir → DESTRUCTIVE；不影响非 win32
```

#### PermissionMode 参数通道（会话级，不进 tool schema）

`PermissionMode` **不加入 shell 工具的 tool schema**——避免 LLM 自己选 YOLO 架空权限控制。改为**会话级配置**，由前端 UI（人）设置，经后端注入到 `ShellTool`：

```
前端 UI（模式下拉框）
  → 会话级配置 API / WebSocket 参数（新增 permission_mode 字段）
  → agent_service 创建 ShellTool 时注入（构造参数 permission_mode，默认 AUTO）
  → ShellTool.execute() 内 policy.evaluate(..., mode=self._permission_mode)
  → resolve_action 消费
```

涉及改动（跨前后端，需列入 plan）：
- 后端：`ShellTool.__init__` 加 `permission_mode` 参数；`agent_service` 传入；会话配置结构加字段。
- 前端：模式切换 UI 控件；把选择存入会话配置并随请求发送。
- **具体前后端接线点在 implementation-plan 阶段勘定**（本 spec 不臆测前端文件路径，实现时先探再改）。

#### factory.py 改造

```python
# create_sandbox 内新增（在 seatbelt/landlock 尝试之前或之后，仅 Windows 走此分支）
if sys.platform == "win32":
    try:
        provider = WindowsSandbox(level=level)
        if provider.is_available():   # 内部探测 pywin32 可用 + API 可调
            return provider
    except Exception as e:
        logger.error("WindowsSandbox 初始化失败，降级到 NullSandbox: %s", e)
    return NullSandbox()   # pywin32 缺失 / Wine / API 不可用 → 透传不隔离
```

---

## 边界与降级

### 沙盒不可用降级

| 场景 | 行为 |
|------|------|
| pywin32 导入失败 | `is_available()` 返回 False → 降级 NullSandbox |
| Wine / 非真实 Windows | API 调用抛异常 → 降级 NullSandbox |
| 构造 WindowsSandbox 抛异常 | 捕获 → 降级 NullSandbox |
| 降级后 + YOLO 模式 | **禁用 YOLO**，提示用户切 AUTO/ASK（无隔离+不审批=裸奔） |
| 降级后 + AUTO/ASK 模式 | 正常可用，危险命令靠审批兜底 + 回落到第一阶段线程池执行路径 |

### Elevated → Unelevated 降级

- 服务启动时无管理员权限 → 直接用 Unelevated（不尝试创建用户/防火墙）。
- Elevated 下创建沙盒用户失败（如策略限制）→ 降级 Unelevated，打警告日志。

### 异常场景

| 场景 | 处理 |
|------|------|
| Restricted Token 创建失败 | `run_command` 返回 None → 上层回落线程池执行（无隔离，打警告） |
| ACL 设置失败 | 同上，回落 + 警告 |
| 子进程超时 | `SandboxRunResult(timed_out=True)` → 上层返回超时错误 |
| 中文路径/输出编码 | 复用现有 `_decode_windows_output`（GBK/UTF-8 降级） |
| 临时目录清理失败 | 打警告日志，不阻塞（下次启动重试） |

### 性能考虑

- `CreateProcessAsUserW` 比 `subprocess.run` 略重（token 构造 + ACL 检查），但相比子进程启动本身可忽略。
- 沙盒用户和 ACL 是幂等/复用的，不在每条命令上重复设置账户，只在会话初始化时设临时目录 ACL。

### 跨平台隔离约束（硬性要求）

1. Windows 特殊逻辑全部在独立文件 + `if sys.platform == "win32"` 分支内。
2. macOS/Linux 保留原有代码路径，**零改动**——`base.py` 的 `run_command` 是新增默认方法，seatbelt/landlock 不重写，行为不变。
3. `shell_tool.py` 的 `else`（非 Windows）分支一行不改。

---

## 测试计划

### 单元测试

| 模块 | 测试点 |
|------|-------|
| `permission_mode.py` | `resolve_action` 在 ASK/AUTO/YOLO × 各 EffectCategory 的输出矩阵；ESCALATE 恒 DENY；YOLO+无沙盒→DENY；**AUTO 列输出 == 现有 EFFECT_ACTION_MAP（回归保护）** |
| `windows_token.py` | Restricted Token 构造（mock pywin32，验证参数）|
| `windows_acl.py` | ACL GRANT/DENY 逻辑（mock，验证 SID 和路径）|
| `base.py` | `run_command` / `run_shell_command` 默认返回 None；seatbelt/landlock 不受影响 |
| `command_effect_registry.py`（builtin）| win32 下 `cd`→READ_ONLY、`copy`→WRITE_PROJECT、`findstr`→READ_ONLY、**`runas`→ESCALATE→经 resolve_action 恒 DENY**、`rmdir`→DESTRUCTIVE；**非 win32 平台 lookup 行为不变（回归保护）** |
| `command_policy.py`（白名单条件化）| `sandbox_available=True` 时 `has_meta` 命令旁路白名单，走 effect registry；`sandbox_available=False` 时保留白名单 DENY（原行为）|

### 现有测试改写（P1(1) 引发）

第一阶段钉死白名单行为的测试，需条件化：

| 测试 | 现状 | 改写 |
|------|------|------|
| `TestWindowsShellWhitelistDenied`（`test_command_policy.py:683-718`）| 无条件断言"非 git/写 git/管道/重定向 → DENY" | 拆两组：`sandbox_available=False` 断言 DENY（保留）；`sandbox_available=True` 断言旁路白名单、走 effect registry 分类 |
| `TestWindowsShellWhitelistAllowed`（`:657-680`）| 断言纯 git 链 ALLOW | 沙盒可用路径下仍应可执行（现在经 effect registry 而非白名单），断言不被 DENY |

### 集成测试（Windows 真机）

| 编号 | 模式 | 输入 | 预期 |
|------|------|------|------|
| 1 | AUTO | `dir`（cmd 原生列目录） | ✓ 直接执行（READ_ONLY）|
| 2 | AUTO | `cd frontend && dir`（含 &&，旁路白名单） | ✓ 进沙盒执行（不再被白名单 DENY）|
| 3 | AUTO | `npm install`（needs network） | ⚠ 网络审批 → 批准后沙盒内联网执行 |
| 4 | AUTO | 写工作区外（`echo x > C:\Windows\y`）| ✗ 沙盒 ACL 拦截（写边界 DENY）|
| 5 | YOLO | `cd x && rd /s /q build`（本地破坏性，cmd 原生） | ✓ 不弹本地审批（DESTRUCTIVE→ALLOW），沙盒内执行（写不出工作区）|
| 6 | **YOLO** | `npm install`（`often_needs_network`） | ⚠ **仍弹网络审批**（预审批命中，YOLO 不旁路网络链）→ 批准后执行 |
| 6b | AUTO Unelevated | `curl http://x`（NETWORK_OUT） | ⚠ 不走预审批（`return False`）；运行期 proxy 可能被绕过 → **验证已知缺口存在**，确认 plan 里的增强需求（非本阶段硬保证）|
| 2b | AUTO | `dir | findstr foo`（builtin + 管道） | ✓ registry 认得 dir/findstr（补 builtin 后）→ READ_ONLY 放行进沙盒 |
| 7 | YOLO | 提权命令（`runas`）| ✗ DENY（ESCALATE 底线）|
| 8 | YOLO + 沙盒不可用 | 任意命令 | ✗ 提示 YOLO 已禁用；has_meta 命令恢复白名单限制 |
| 9 | AUTO Elevated | 网络命令批准后 | ✓ Online 用户联网；未授权出站被防火墙阻断 |
| 10 | AUTO | 中文路径工作区 | ✓ 编码正确 |
| 11 | 沙盒不可用降级 | `git status && dir`（has_meta） | ✗ 白名单恢复生效 → DENY（验证兜底）|

### 回归测试（macOS/Linux + Windows 现状）

- 现有 sandbox 测试（seatbelt/landlock）全部通过，无新增失败。
- `run_command` 新增后，确认 seatbelt/landlock 仍走 `wrap_command` 路径（验证默认 None 生效）。
- **Windows argv 现状回归**：`test_command_policy.py:85-122`、`test_shell_tool.py:61-66`（npm install/git add/python --version 等 WRITE_PROJECT→ALLOW）在 AUTO 模式下行为不变。
- 网络审批链路回归：`_needs_network_approval` 相关现有测试不受 PermissionMode 影响。
- 性能无明显下降。

---

## 实施步骤（概要）

1. **权限模式层**：`permission_mode.py`（PermissionMode + resolve_action）+ 单测。
2. **接口扩展**：`base.py` 加 `run_command` / `run_shell_command` 默认实现 + `SandboxRunResult` + 单测（验证默认 None）。
2.5. **Windows builtin 分类**：`command_effect_registry.py` **直接注册**（非 `platform_overrides`）`cd`/`chdir`/`dir`/`type`/`set`/`findstr`/`tree`/`ver`/`cls`/`copy`/`xcopy`/`robocopy`/`move`/`ren`/`rename`/`md`（跳过已注册的 `echo`/`find`/`where`/`mkdir`）；补 `runas`→ESCALATE、`rmdir`→DESTRUCTIVE（见 3.8）+ 单测（win32 下 `cd`→READ_ONLY / `copy`→WRITE_PROJECT / `runas`→ESCALATE→DENY；非 win32 lookup 行为回归不变）。
3. **Windows Token 层**：`windows_token.py`（Restricted Token 构造）+ 单测（mock）。
4. **Windows ACL 层**：`windows_acl.py`（文件写入边界）+ 单测（mock）。
5. **Windows 沙盒主类（Unelevated）**：`windows.py` 重写 `run_command`，串联 Token + ACL + 临时目录，先只做 Unelevated 档。
6. **Elevated 增强**：`windows_user.py`（沙盒用户）+ `windows_firewall.py`（防火墙）+ `windows.py` 加 Elevated 分支。
7. **工厂接线**：`factory.py` 加 Windows 分支 + 降级逻辑。
8. **白名单条件化**：`command_policy.py:168` 加 `not sandbox_available` 条件，旁路白名单；改写 `TestWindowsShellWhitelist*` 测试为条件化。
9. **上层接线**：`shell_tool.py` 的 `_execute_argv` Windows 分支调 `run_command`、`_execute_shell` Windows 分支调 `run_shell_command`；沙盒可用时把 `_execute_shell` 现有的 `NETWORK_OUT` 硬拒绝（`shell_tool.py:530-534`）改为交沙盒 + 网络审批链处理（沙盒不可用降级时保留硬拒绝）。
10. **权限模式接入**：`command_policy.py` 决定 `decision.action` 处调 `resolve_action`；`ShellTool` 接收会话级 `permission_mode`。**验证网络审批链路（`_needs_network_approval` + elevation）不受 mode 影响**。
11. **前端模式通道**：模式切换 UI + 会话配置字段 + 后端注入（实现时先勘定前后端接线点）。
12. **集成测试**：Windows 真机跑测试矩阵；macOS/Linux + Windows 现状回归。

（详细分步 + 代码由后续 implementation-plan 文档给出。）

---

## 总结

**核心决策（含审查修正）**：
1. **三个正交维度**：本地操作审批（PermissionMode）/ 网络审批（独立链路，任何 mode 都保留）/ 沙盒文件隔离。**YOLO = 本地放开，≠ 联网放开**。
2. **白名单降级为兜底**：沙盒可用时旁路 `has_meta` 白名单（放开 shell 命令链/重定向/管道）；沙盒不可用时恢复生效。**前置**：需先给 registry **直接注册**（非死字段 `platform_overrides`）Windows builtin（`cd`/`dir`/`copy`…），并补 `runas`→ESCALATE，否则旁路后这些命令判 UNKNOWN、runas 不落 DENY（见 3.8）。
3. **接口按 argv/shell 两支闭合**：`SandboxProvider` 新增 `run_command`（argv）+ `run_shell_command`（shell 模式，内部包 `cmd.exe /c` 交 `CreateProcessAsUserW`）两个可选方法，与上层 `_execute_argv`/`_execute_shell` 一一对应，Windows 重写、其他平台继承默认 None，macOS/Linux 零改动。
4. Windows 原生沙盒 = pywin32 调 Restricted Token + ACL（文件隔离，两档均为真边界）+ 专用用户 + 防火墙（Elevated 网络增强）。
5. **网络闸门分两段且分档诚实**：预审批只覆盖 `often_needs_network`（NETWORK_OUT 被 `return False` 跳过）；NETWORK_OUT 靠运行期拒绝回执。**仅 Elevated 档网络可靠**；Unelevated 对 NETWORK_OUT 存在已知缺口，可选增强列入 plan。
6. 降级安全 = 沙盒不可用时禁用 YOLO，AUTO/ASK 靠审批 + 白名单兜底。
7. PermissionMode 为**会话级配置**（人设，不进 tool schema），跨前后端接线列入 plan。

**跨平台保证**：Windows 逻辑全隔离在独立文件 + 平台分支，macOS/Linux 代码路径一行不改。
