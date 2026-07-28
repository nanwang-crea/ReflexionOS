# Windows cmd 内部命令降级执行设计

## 背景

Windows Phase 2 沙箱已上线，`shell_tool` 的 argv 模式在 Windows 上优先走
`WindowsSandbox.run_command`（`CreateProcessAsUser` 直接启动 .exe）。

但 Windows 有大量 **cmd 内部命令**（`if`/`for`/`mkdir`/`copy`/`move`/`dir`/`type`/`echo`/`set`/`cd`…）
没有对应的独立 .exe，`CreateProcess` 找不到可执行文件必然失败。

线上日志复现：

```
argv=['if','not','exist','"docs\plans\features"','mkdir','docs\plans\features']
→ 未知命令: if（if 未注册到效果表）
→ ACL 阶段因 allowed_paths 含不存在的 .reflexion/skills 目录而失败
→ 即便 ACL 修好，CreateProcessAsUser 也找不到 if.exe，命令必败
```

argv 模式刻意不走 `cmd.exe /c` 是为了防 shell 注入（参数按数组传、无解释）。
但 cmd 内部命令**必须**经过 `cmd.exe` 解释才能执行，这是 Windows 独有的矛盾。

## 目标 / 非目标

### 目标
argv 模式在 Windows 上检测到「首个 token 是 cmd 内部命令」时，
**仅对这种情况**降级走 shell 模式（`cmd.exe /c` + 沙箱 `run_shell_command`），
真 .exe 命令仍走 `CreateProcess` 保安全。

### 非目标
- 不改 `command_policy` 的 argv/shell 分发语义（保持跨平台纯净）。
- 不把所有 argv 命令都改走 `cmd.exe /c`（保 argv 注入防护）。
- 不处理 cmd 内部命令的效果分类问题（`if` 仍按 UNKNOWN 走审批，这是策略层既有行为）。
- 不改 ACL / 网络 / Elevated 档。

## 方案

**实现位置：`shell_tool._execute_decision`**（不在沙箱层、不在 command_policy）。

理由（关键约束）：
- argv→command 字符串重建不可靠。实测 `subprocess.list2cmdline` 对带引号的
  `"docs\plans\features"` 会吃掉反斜杠，破坏路径。因此**必须复用 `decision.command` 原始字符串**。
- 只有 `shell_tool` 同时持有 `decision.command`（原始字符串）和 `decision.argv`，
  且能决定走 `_execute_shell` 还是 `_execute_argv`。
- `command_policy` 是跨平台核心，不掺 Windows 特定执行逻辑。

改动点（`shell_tool._execute_decision` argv 分支头部）：Windows 且 `argv[0]` 是 cmd 内部命令时，
改走 `_execute_shell(decision.command, ...)`，复用原始命令字符串。

`_execute_shell` 的 Windows 分支已具备：沙箱可用走 `run_shell_command`（`cmd.exe /c` +
`CreateProcessAsUser` + Restricted Token + ACL），不可用回退线程池。无需改动。

## cmd 内部命令清单

新建 `backend/app/security/sandbox/windows_cmd.py`，纯数据 + 纯函数，无 win32 依赖。

包含：`if`/`for`/`call`/`goto`/`shift`/`setlocal`/`endlocal`/`rem`/`pause`/`exit`/`start`/
`mkdir`/`md`/`rmdir`/`rd`/`pushd`/`popd`/`mklink`/
`copy`/`xcopy`/`move`/`ren`/`rename`/`del`/`erase`/`type`/
`echo`/`set`/`dir`/`cd`/`chdir`/`cls`/`ver`/`vol`/`prompt`/`title`/`color`/`path`/`assoc`/`ftype`/
`date`/`time`/`break`/`verify`/`dpath`/`keys`/`chcp`。

**明确排除**（System32 下有独立 .exe，argv 能跑，不降级）：
`find`、`findstr`、`robocopy`、`where`、`tasklist`、`taskkill`、`reg`、`sc`、`net`、`wmic`、`ping`、`ipconfig`。

清单可后续按需扩展。

## 边界与降级

- `argv[0]` 为空 / None → 不降级，走原 argv 流程。
- `decision.command` 为空但 argv 非空（理论不会发生）→ 走原 argv 流程，由 `run_command` 自行失败。
- 非 Windows → 完全不触发（`sys.platform == "win32"` 守卫）。
- effect_category 沿用 argv 决策结果（如 `mkdir`→WRITE_PROJECT），审批/信任逻辑不变。
- 安全语义：被降级的命令经过 `cmd.exe` 解释，等于这批命令接受 shell 语义。
  但这些命令**本就是 cmd 语法**，不经过 cmd.exe 无法执行，
  降级是必要且无新增注入面（命令仍经策略层审批/校验后才到执行层）。

## 验收

- `argv[0]` 是 cmd 内部命令（如 `mkdir`/`if`）→ Windows 沙箱下走 `run_shell_command`（cmd.exe /c）成功执行。
- `argv[0]` 是真 .exe（如 `git`/`python`）→ 仍走 `run_command`（CreateProcess）。
- 有独立 .exe 的命令（`findstr`/`robocopy`）不误降级。
- 非 Windows 平台行为不变。
