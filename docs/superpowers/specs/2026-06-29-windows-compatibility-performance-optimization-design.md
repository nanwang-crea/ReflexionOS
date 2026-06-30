# Windows 平台兼容性与性能优化设计文档

**文档版本**：v1.0  
**创建日期**：2026-06-29  
**作者**：Claude + Ethan  
**状态**：待审查

---

## 1. 背景

### 1.1 项目现状

ReflexionOS 是基于 Electron + React + FastAPI 的桌面编程 Agent，技术栈如下：

- **桌面壳**：Electron 31
- **前端**：React 18 + TypeScript + Vite 5 + Tailwind CSS 3 + Zustand 4
- **后端**：Python 3.12 + FastAPI
- **实时通信**：WebSocket
- **UI 动画**：Framer Motion
- **虚拟滚动**：react-virtuoso
- **代码编辑器**：Monaco Editor

项目已在 macOS 和 Linux 上验证可用，但 Windows 平台存在明显的兼容性和性能问题。

### 1.2 问题发现

#### 问题来源
- **用户反馈**：Windows 用户报告"感觉在 Windows 系统比较卡，多个方面都卡"
- **实际测试**：2026-06-29 在 Windows 环境下测试发现以下问题

#### 已确认问题

**问题 1：Shell 命令执行失败**
- **现象**：用户在对话中执行 git 命令时，后端返回错误提示：
  ```
  当前环境下的 shell 执行似乎存在兼容性问题，git 命令的输出无法正常捕获，
  Windows shell 模式也尚未完全支持
  ```
- **复现路径**：
  1. 启动 Electron 桌面应用（`pnpm dev`）
  2. 创建或选择一个 Git 项目
  3. 在对话框中发送消息："查看 git 状态"
  4. LLM 调用 shell 工具执行 `git status`
  5. 后端返回上述错误，前端显示 `[User Cancelled]`
- **影响范围**：
  - Git 操作功能不可用（status、log、diff、commit 等）
  - grep/rg 文件搜索可能失败
  - 依赖 shell 的其他工具调用

**问题 2：整体性能卡顿**
- **现象**：用户反馈"多个方面都卡"，包括：
  - 应用启动慢
  - 界面滚动不流畅
  - 输入响应有延迟
  - 对话历史变长后越来越卡
  - LLM 返回大量内容时界面掉帧
- **严重程度**：影响日常使用体验
- **待诊断**：具体的性能瓶颈需通过性能分析工具（Chrome DevTools Performance Monitor）进一步定位

### 1.3 为什么要做

- **功能可用性**：Shell 兼容性问题导致核心功能（Git 集成）在 Windows 上不可用
- **用户体验**：性能问题严重影响日常使用体验，可能导致用户放弃使用
- **跨平台承诺**：项目 README 和 CLAUDE.md 明确声明"该项目跨 Windows 和 macOS 平台"，需兑现承诺
- **市场占有率**：Windows 是桌面操作系统主流（约 70% 市场份额），不能忽视

---

## 2. 目标与非目标

### 2.1 目标

**核心目标**：让 ReflexionOS 在 Windows 平台上达到与 macOS/Linux 相同的功能完整性和性能水平。

**具体指标**：

1. **Shell 兼容性（P0 必须完成）**
   - ✅ git 命令可正常执行并返回正确输出
   - ✅ grep/rg 文件搜索可正常工作
   - ✅ 路径参数自动适配 Windows 风格（`\` 分隔符）
   - ✅ 命令输出编码正确处理（UTF-8 vs GBK）

2. **性能优化（P1 重要）**
   - ✅ 应用启动时间 < 5 秒（从双击到界面可用）
   - ✅ 滚动 100+ 条对话消息时 FPS > 30
   - ✅ 聊天框输入延迟 < 100ms（从按键到显示）
   - ✅ 运行 1 小时后 JS heap size < 300MB（避免内存泄漏）

3. **稳定性（P1 重要）**
   - ✅ 不因 Windows 特殊字符（如路径中的空格、中文）导致崩溃
   - ✅ 长时间运行不出现性能退化

### 2.2 非目标

**明确不做的事情**：

- ❌ 不做 Windows XP/7/8 等旧版本支持（仅支持 Windows 10/11）
- ❌ 不做 ARM64 Windows 适配（仅支持 x64）
- ❌ 不做 UI 风格 Windows 化（保持现有设计语言）
- ❌ 不做 Windows 独占功能（如 WSL 集成、PowerShell 特性）
- ❌ 不优化 Web 模式性能（仅优化 Electron 桌面版）

### 2.3 跨平台兼容性承诺（核心原则）

**铁律**：所有修改必须保证 macOS 和 Linux 现有功能和性能不受影响。

**具体要求**：

1. **代码隔离原则**
   - Windows 特殊逻辑必须放在 `if sys.platform == "win32"` 或 `if platform.system() == "Windows"` 分支内
   - macOS/Linux 保留原有代码路径，零改动
   - 不允许"为了统一而修改所有平台"的做法

2. **性能不退化原则**
   - 前端优化必须基于 profiler 实测数据，不是假设
   - 如果某个优化在某平台有副作用，该平台不采用该优化
   - 不按平台一刀切降级体验（违背一致性原则）

3. **测试覆盖原则（实际可行的）**
   - **代码审查**：每个 PR 人工检查是否修改了 Unix 代码路径
   - **自动化测试**：后端单元测试在开发机（macOS/Windows）上跑过
   - **手工回归测试**：在一台 macOS/Linux 机器上验证核心功能（git、搜索、对话）
   - **发布前验证**：Release 前在三个平台上完整手工测试

**不要求的（当前不具备条件）**：
   - ❌ 每个 PR 都跑三平台 CI（没有 CI 环境）
   - ❌ 每个 PR 都测三平台性能基准（耗时太长，不现实）

---

## 3. 用户故事

### 故事 1：Git 操作正常工作

**角色**：Windows 桌面用户  
**场景**：使用 ReflexionOS 管理一个本地 Git 项目  
**期望行为**：

1. 用户在对话框输入："查看当前分支的 git 状态"
2. LLM 调用 shell 工具执行 `git status`
3. 后端正确捕获命令输出（包含中文文件名）
4. 前端展示 Git 状态信息（staged/unstaged/untracked 文件）
5. 用户继续操作："提交所有更改"
6. LLM 执行 `git add -A && git commit -m "..."` 成功

**当前问题**：步骤 3 失败，返回"Windows shell 模式也尚未完全支持"

### 故事 2：长对话流畅滚动

**角色**：Windows 桌面用户  
**场景**：与 Agent 进行了 50+ 轮对话，消息历史很长  
**期望行为**：

1. 用户在对话区域滚动查看历史消息
2. 滚动流畅，无明显掉帧或卡顿（目测 > 30 FPS）
3. 展开/折叠工具调用卡片响应及时（< 100ms）
4. 新消息到达时自动滚动到底部，无延迟

**当前问题**：对话变长后滚动不流畅，展开卡片有明显延迟

### 故事 3：快速启动应用

**角色**：Windows 桌面用户  
**场景**：双击桌面图标启动 ReflexionOS  
**期望行为**：

1. 用户双击应用图标
2. 3-5 秒内窗口打开并显示可交互界面
3. 后端服务在后台自动启动，无需用户干预
4. 界面加载完成后可立即操作（选择项目、发送消息）

**当前问题**：启动较慢，可能超过 10 秒

### 故事 4：处理包含空格和中文的路径

**角色**：Windows 桌面用户  
**场景**：项目路径包含空格或中文（如 `C:\Users\张三\Documents\My Project\`）  
**期望行为**：

1. 用户选择该路径创建项目
2. 所有文件操作、Git 操作正常工作
3. 路径在命令行参数中正确转义
4. 输出中的中文文件名正确显示（不乱码）

**当前问题**：未测试，存在潜在风险

---

## 4. 技术方案

### 4.1 架构层次

优化涉及三个层次，从下到上依次为：

```
┌─────────────────────────────────────┐
│   Layer 3: Electron 主进程          │  ← 启动优化、进程管理
├─────────────────────────────────────┤
│   Layer 2: 前端渲染层（React）      │  ← 渲染性能、内存优化
├─────────────────────────────────────┤
│   Layer 1: 后端执行层（FastAPI）    │  ← Shell 兼容性、异步 I/O
└─────────────────────────────────────┘
```

### 4.2 Layer 1：后端 Shell 兼容性修复（P0）

#### 4.2.1 问题根因分析（已核实代码）

**真实阻塞点**：策略层和执行层都硬编码拒绝了 Windows shell 模式。

**阻塞点 1**：`backend/app/security/command_policy.py:168`
```python
if result.has_meta and self.shell_security._is_windows():
    return CommandDecision(
        action=CommandAction.DENY,
        command=command,
        execution_mode="shell",
        cwd=resolved_cwd,
        timeout=timeout,
        reasons=["Windows shell 模式尚未支持"],  # ← 策略层直接拒绝
        environment_snapshot=snapshot,
    )
```

**阻塞点 2**：`backend/app/tools/shell_tool.py:349`
```python
async def _execute_shell(self, command: str, cwd: str, timeout: int, ...):
    if sys.platform == "win32":
        return ToolResult(success=False, error="Windows shell 模式尚未支持")  # ← 执行层也拒绝
    # ...
```

**核心问题**：`result.has_meta` 表示命令包含 shell 元字符（如 `&&`、`|`、`>`、`;`），Windows 下这类命令被完全禁止。

**次要问题**：
- 路径处理：Unix 风格路径（`/`）在 Windows 上可能不工作
- 编码问题：中文路径/文件名可能乱码（GBK vs UTF-8）
- Shell 语法：`cmd.exe` 和 `bash` 的语法差异（如环境变量 `%VAR%` vs `$VAR`）

#### 4.2.2 修复方案

**核心策略：分层改造，从策略到执行**

修复分为三层，从上到下依次为：
1. **策略层**：`command_policy.py` 放行 Windows shell 模式（有条件地）
2. **执行层**：`shell_tool.py` 实现 Windows shell 执行逻辑
3. **语法层**：确定支持哪些 shell 元字符（`&&`、`|`、`;` 等）

**为了确保不影响 macOS 和 Linux**：
- ✅ Windows 逻辑单独分支，不修改现有 Unix 代码路径
- ✅ 优先保持现有行为，Windows 作为特例处理
- ✅ 所有平台相关代码都有明确的 `sys.platform == "win32"` 判断

---

**第 1 层：策略层放行（command_policy.py）**

决定哪些 shell 元字符在 Windows 上支持：

```python
# backend/app/security/command_policy.py

def evaluate(self, command: str, cwd: str, timeout: int = 30) -> CommandDecision:
    # ... 现有代码 ...
    
    # ❌ 修改前：Windows 一律拒绝
    if result.has_meta and self.shell_security._is_windows():
        return CommandDecision(
            action=CommandAction.DENY,
            command=command,
            execution_mode="shell",
            reasons=["Windows shell 模式尚未支持"],
        )
    
    # ✅ 修改后：Windows 第一阶段白名单 gate
    if result.has_meta and self.shell_security._is_windows():
        # ========== Windows 第一阶段：严格白名单策略 ==========
        # 原因：Windows 无 sandbox.wrap_shell_command，无法约束命令内自由路径参数
        # 策略：(1) 只放行纯读的 git 子命令；(2) 复用 shell_security._validate_path_arguments 校验路径参数
        
        # 检查元字符：第一阶段只支持 && 和 ||（命令链）
        supported_on_windows = {'&&', '||'}
        unsupported_on_windows = {'|', '<', '>', '>>', '2>', '&', ';'}
        
        used_meta = self._extract_meta_chars(command)  # 需实现：quote-aware 元字符提取
        unsupported_used = used_meta & unsupported_on_windows
        
        if unsupported_used:
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                execution_mode="shell",
                reasons=[f"Windows 第一阶段不支持这些 shell 特性：{unsupported_used}"],
            )
        
        # 拆分命令链（按 && 和 || 拆）
        segments = self._split_shell_command(command)  # 需实现：按 &&/|| 拆分
        
        for segment in segments:
            segment_normalized = segment.strip()
            
            # 检查是否是 git 命令
            if not segment_normalized.startswith('git '):
                return CommandDecision(
                    action=CommandAction.DENY,
                    command=command,
                    execution_mode="shell",
                    reasons=[f"Windows 第一阶段只支持 git 命令，不支持: {segment_normalized}"],
                )
            
            # 解析命令为 argv（用于后续路径校验）
            try:
                segment_argv = shlex.split(segment_normalized, posix=False)  # Windows 用非 POSIX 模式
            except ValueError as e:
                return CommandDecision(
                    action=CommandAction.DENY,
                    command=command,
                    execution_mode="shell",
                    reasons=[f"命令解析失败: {e}"],
                )
            
            if len(segment_argv) < 2:
                return CommandDecision(
                    action=CommandAction.DENY,
                    command=command,
                    execution_mode="shell",
                    reasons=["git 命令缺少子命令"],
                )
            
            git_subcommand = segment_argv[1]
            
            # 严格白名单：只允许纯读的子命令（无 -D/-m/add/remove 等写操作）
            # 注意：不允许 branch、remote（它们有写子命令）
            allowed_pure_read_subcommands = {'status', 'log', 'diff', 'show'}
            
            if git_subcommand not in allowed_pure_read_subcommands:
                return CommandDecision(
                    action=CommandAction.DENY,
                    command=command,
                    execution_mode="shell",
                    reasons=[f"Windows 第一阶段只支持纯读 git 命令，不支持: git {git_subcommand}"],
                )
            
            # 路径参数校验：复用 shell_security._validate_path_arguments
            # 这会校验命令中所有看起来像路径的参数（segment_argv[2:] 是 git 子命令的参数）
            try:
                self.shell_security._validate_path_arguments(segment_argv[2:], self.path_security)
            except SecurityError as e:
                return CommandDecision(
                    action=CommandAction.DENY,
                    command=command,
                    execution_mode="shell",
                    reasons=[f"路径参数不在允许范围: {e}"],
                )
        
        # 通过白名单检查：继续走 shell 执行流程
        # 注意：macOS/Linux 的逻辑不修改
    
    # macOS/Linux 保持原有逻辑
    if result.has_meta:
        return self._evaluate_shell_command(command_normalized, ...)
    
    return self._evaluate_argv_command(command_normalized, result.argv, ...)
```

**设计决策（第一阶段白名单策略）**：

**策略层允许的元字符**（`command_policy.py`）：
- `&&` — 命令链（成功才继续），cmd.exe 原生支持
- `||` — 命令链（失败才继续），cmd.exe 原生支持

**策略层拒绝的元字符**（第一阶段）：
- `;` — 顺序执行（转换需 quote-aware 解析，第二阶段支持）
- `|` — 管道（第二阶段考虑）
- `>`、`>>` — 重定向（**第一阶段禁止**，避免路径逃逸到白名单外）
- `<` — 输入重定向（暂不支持）
- `2>` — 错误重定向（暂不支持）
- `&` — 后台执行（cmd.exe 语法不同，暂不支持）

**策略层严格白名单**（`command_policy.py`）：
- **适用范围**：仅对 `has_meta=True` 的命令生效（包含 `&&`/`||` 等元字符）
- **第一阶段只允许纯读 git 子命令**：`git status`、`git log`、`git diff`、`git show`
- **禁止有写能力的子命令**：`git branch`（有 -D/-m）、`git remote`（有 add/remove/set-url）
- **路径参数校验**：复用 `shell_security._validate_path_arguments()` 校验所有路径型参数
- **禁止**：任何非 git 命令（如 `ls && echo`）、任何重定向（`>`、`>>`）
- **注意**：无元字符的命令（如单独的 `git add .`）不经过此白名单，走 argv 路径处理

**执行层实现**（`shell_tool.py`）：
- 第一阶段无需语法转换（支持的元字符都是 cmd.exe 原生语法）
- 直接传给 `cmd.exe /c`

**关键约束**：Windows shell 需尽量接近 Unix 的安全语义，但第一阶段存在**显著差异**：

**Unix shell 的安全机制**（当前代码 shell_tool.py:352-359）：
- `sandbox.wrap_shell_command(command, cwd, allowed_paths, allow_network)` 强制执行
- 命令内的**所有路径参数**都被沙箱限制在 `allowed_paths` 内
- 网络访问被沙箱技术强制隔离（Seatbelt / Landlock）

**Windows 第一阶段的安全机制**（本次实现，部分对齐）：
- **路径限制部分对齐**：策略层通过 `_validate_path_arguments` 校验命令内路径型参数（与 argv 模式等价），但**仍弱于 Unix sandbox.wrap_shell_command 的整命令运行时强制包裹**
- **网络权限不对齐**：无沙箱技术强制，只能策略层拒绝 + 记日志

**第一阶段策略（严格白名单）**：
1. 继续 DENY 网络型 shell 命令（`effect_category == NETWORK_OUT`）
2. **仅放行 4 个纯读 git 子命令**（`status`、`log`、`diff`、`show`）
3. **路径参数强制校验**（通过 `_validate_path_arguments` 校验所有路径型参数）
4. **禁止有写能力的子命令**（`branch`、`remote`、`add`、`commit` 等）
5. 在用户界面提示："Windows 第一阶段 shell 能力受限，复杂操作请在 macOS/Linux 上执行"

**已知残余风险**：
- 路径约束仍弱于 Unix（缺少运行时整命令沙箱包裹）
- 网络隔离弱于 Unix（无技术强制）
- 后续阶段考虑：(1) AppContainer / Job Objects 沙箱实现整命令包裹；(2) 扩展白名单

---

**第 2 层：执行层实现（shell_tool.py）**

**Unix 现有安全机制**（参考 shell_tool.py:352-359）：
```python
# macOS/Linux 路径：通过 sandbox.wrap_shell_command() 强制执行
if self.sandbox.is_available():
    allow_network = sandbox_allow_network or (effect_category == EffectCategory.NETWORK_OUT)
    allowed_paths = list(self.path_security.allowed_base_paths)
    if sandbox_extra_paths:
        allowed_paths.extend(sandbox_extra_paths)
    command = self.sandbox.wrap_shell_command(
        command, cwd=cwd, allowed_paths=allowed_paths, allow_network=allow_network,
    )
```

**Windows 第一阶段实现**（新增，部分安全语义对齐）：
```python
# backend/app/tools/shell_tool.py

async def _execute_shell(
    self, command: str, cwd: str, timeout: int,
    effect_category: EffectCategory | None = None,
    sandbox_allow_network: bool = False,
    sandbox_extra_paths: list[str] | None = None,
) -> ToolResult:
    # ❌ 修改前：Windows 直接拒绝
    if sys.platform == "win32":
        return ToolResult(success=False, error="Windows shell 模式尚未支持")
    
    # ✅ 修改后：Windows 通过白名单 + 执行前校验实现部分安全语义对齐
    # 注意：命令内路径参数校验已在策略层完成（command_policy.py），这里只处理执行层
    if sys.platform == "win32":
        # ========== 1. 路径限制（部分对齐 Unix sandbox） ==========
        # ⚠️ 执行层只校验 cwd 和 sandbox_extra_paths
        # 命令内路径参数已在策略层通过 _validate_path_arguments 校验
        # 仍弱于 Unix sandbox.wrap_shell_command 的整命令运行时强制包裹
        
        # 验证 cwd 在白名单内
        try:
            validated_cwd = self.path_security.validate_path(cwd)
        except ExternalPathError as e:
            return ToolResult(success=False, error=f"工作目录不在允许范围: {e}")
        
        # 验证 sandbox_extra_paths（若有）也在白名单内
        if sandbox_extra_paths:
            for extra_path in sandbox_extra_paths:
                try:
                    self.path_security.validate_path(extra_path)
                except ExternalPathError as e:
                    return ToolResult(success=False, error=f"额外路径 {extra_path} 不在允许范围: {e}")
        
        # ========== 2. 网络权限检查（与 Unix 语义对齐，但无技术强制） ==========
        allow_network = sandbox_allow_network or (effect_category == EffectCategory.NETWORK_OUT)
        
        # ⚠️ Windows 第一阶段：继续拒绝网络型命令（因无沙箱强制）
        if effect_category == EffectCategory.NETWORK_OUT:
            return ToolResult(
                success=False, 
                error="Windows 第一阶段不支持网络型 shell 命令（无沙箱强制），请在 macOS/Linux 上执行"
            )
        
        # 本地命令：记录网络权限标志（供审计，但无技术强制）
        if not allow_network:
            logger.warning(
                "Windows shell 命令未授权网络访问（无沙箱强制）: %s, cwd=%s", 
                command, validated_cwd
            )
        
        # ========== 3. 审计日志（与 Unix 一致） ==========
        logger.info(
            "执行 Windows shell 命令: %s, cwd=%s, network=%s, effect=%s",
            command, validated_cwd, allow_network, effect_category
        )
        
        # 构建 Windows 命令（元字符转换已在策略层完成）
        process = await asyncio.create_subprocess_shell(
            f'cmd.exe /c "{command}"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=validated_cwd,
            env=self._build_env(),
        )
    else:
        # macOS/Linux: 保持现有逻辑（不修改）
        if self.sandbox.is_available():
            allow_network = sandbox_allow_network or (effect_category == EffectCategory.NETWORK_OUT)
            allowed_paths = list(self.path_security.allowed_base_paths)
            if sandbox_extra_paths:
                allowed_paths.extend(sandbox_extra_paths)
            command = self.sandbox.wrap_shell_command(
                command, cwd=cwd, allowed_paths=allowed_paths, allow_network=allow_network,
            )
        
        executable = "/bin/zsh" if sys.platform == "darwin" else "/bin/bash"
        if not os.path.exists(executable):
            executable = "/bin/sh"
        
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            executable=executable,
            env=self._build_env(),
        )
    
    # 读取输出（所有平台通用）
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        process.kill()
        return ToolResult(success=False, error=f"命令超时（{timeout} 秒）")
    
    # 解码输出（Windows 特殊处理编码）
    if sys.platform == "win32":
        # Windows: UTF-8 优先，GBK 回退
        try:
            stdout = stdout_bytes.decode("utf-8")
            stderr = stderr_bytes.decode("utf-8")
        except UnicodeDecodeError:
            stdout = stdout_bytes.decode("gbk", errors="replace")
            stderr = stderr_bytes.decode("gbk", errors="replace")
    else:
        # macOS/Linux: UTF-8（现有逻辑）
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
    
    # 返回结果（所有平台通用）
    return ToolResult(
        success=(process.returncode == 0),
        output=stdout,
        error=stderr if process.returncode != 0 else "",
        data={"return_code": process.returncode},
    )
```

---

**第 3 层：语法兼容性（具体命令适配）**

cmd.exe 和 bash 的语法差异及第一阶段支持范围：

| 特性 | bash | cmd.exe | 第一阶段支持 | 备注 |
|------|------|---------|-------------|------|
| 命令链（成功继续） | `cmd1 && cmd2` | `cmd1 && cmd2` | ✅ 原生支持 | git 链式操作需要 |
| 命令链（失败继续） | `cmd1 \|\| cmd2` | `cmd1 \|\| cmd2` | ✅ 原生支持 | 容错链需要 |
| 命令链（总是继续） | `cmd1 ; cmd2` | `cmd1 & cmd2` | ❌ 暂不支持 | 转换需 quote-aware |
| 管道 | `cmd1 \| cmd2` | `cmd1 \| cmd2` | ❌ 暂不支持 | 第二阶段考虑 |
| 重定向 | `cmd > file` | `cmd > file` | ❌ **第一阶段禁止** | 避免路径逃逸 |
| 追加重定向 | `cmd >> file` | `cmd >> file` | ❌ **第一阶段禁止** | 避免路径逃逸 |
| 环境变量 | `$VAR` | `%VAR%` | ❌ 不转换 | git 不依赖此语法 |

**第一阶段严格白名单**（仅适用于带元字符的命令）：
- ✅ 允许：`git status`、`git log`、`git diff`、`git show`（**仅这 4 个纯读子命令**）
- ✅ 允许：上述命令的 `&&` 和 `||` 组合（如 `git status && git log`）
- ✅ 路径参数校验：命令内所有路径型参数（如 `git diff file.txt && git log`）通过 `_validate_path_arguments` 校验
- ❌ 禁止：`git branch && echo`、`git remote && echo`（有写能力的子命令，即使在命令链中）
- ❌ 禁止：`git add . && git commit`（写操作命令链）
- ❌ 禁止：任何重定向操作（`git status > file`）
- ❌ 禁止：任何非 git 命令链（`ls && echo`）
- **注意**：无元字符的单个命令（如 `git add .`、`git branch`）不经过此白名单，走 argv 路径

**执行实现**（在 `_execute_shell` 中）：
```python
if sys.platform == "win32":
    # 第一阶段：无需语法转换，直接传给 cmd.exe
    # （白名单已在策略层过滤，这里只处理执行）
    process = await asyncio.create_subprocess_shell(
        f'cmd.exe /c "{command}"',
        ...
    )
```

**关键改进点**：
1. ✅ **策略层严格白名单**（只允许 4 个纯读 git 子命令：status/log/diff/show）
2. ✅ **路径参数校验**（复用 `shell_security._validate_path_arguments` 校验命令内所有路径）
3. ✅ **元字符限制**（第一阶段只支持 `&&` 和 `||`，禁止重定向）
4. ✅ 执行层实现 Windows 分支（cmd.exe，不修改 Unix 代码）
5. ✅ **网络型命令继续拒绝**（第一阶段无沙箱强制）
6. ✅ 编码处理（UTF-8 优先，GBK 回退）
7. ✅ 环境变量传递（使用现有 `_build_env()` 逻辑）

**安全约束落地（与 Unix 的差异）**：
- **路径限制部分对齐**：通过 `_validate_path_arguments` 校验命令内路径型参数（与 argv 模式等价），但**弱于 Unix sandbox.wrap_shell_command 的整命令强制包裹**
- **网络权限不等价**：第一阶段继续 DENY 网络型命令（Unix 有沙箱技术强制，Windows 只能策略层拒绝）
- **审计日志**：命令执行记录（与 Unix 一致）
- 策略层保持一致：Windows 和 Unix 用相同的 `CommandPolicy.evaluate()` 流程

**残余风险声明**：
- **路径约束风险显著降低**：通过白名单（4 个纯读子命令）+ `_validate_path_arguments` 校验，但仍弱于 Unix sandbox 整命令包裹
- **网络隔离不等价**：Windows 无技术强制，只能策略层拒绝
- **第一阶段能力受限**：只支持 4 个纯读 git 子命令（status/log/diff/show），写操作需在 macOS/Linux 执行
- 后续阶段考虑：(1) 扩展白名单（支持 branch -l、remote -v 等只读子命令）；(2) AppContainer / Job Objects 沙箱实现整命令包裹；(3) 支持更多元字符（管道、重定向）

#### 4.2.3 Git 命令特殊处理

Git 在 Windows 上的路径输出可能是 Unix 风格（`/`），需要统一：

```python
def normalize_git_paths(output: str) -> str:
    """将 git 输出中的路径统一为平台风格"""
    if platform.system() == "Windows":
        # Git for Windows 输出用 /，转为 \
        # 但只转路径部分，不转 URL
        # 简化处理：保持原样，Python pathlib 会自动处理
        pass
    return output
```

#### 4.2.4 测试用例

需要验证的命令：
- `git status`
- `git log --oneline -10`
- `git diff HEAD`
- `ls` 或 `dir`（跨平台文件列表）
- `grep` 或 `rg`（文件内容搜索）

测试场景：
- ✅ 正常路径（无空格、纯英文）
- ✅ 包含空格的路径（`C:\Program Files\...`）
- ✅ 包含中文的路径（`C:\Users\张三\...`）
- ✅ 文件名包含中文（`测试.py`）

### 4.3 Layer 2：前端渲染性能优化（P1）

#### 4.3.1 问题诊断方法

在优化前，先用工具定位瓶颈：

**工具 1：Chrome DevTools Performance Monitor**
- 打开方式：DevTools → 右上角三个点 → More tools → Performance monitor
- 关注指标：
  - CPU usage（CPU 使用率）
  - JS heap size（内存占用）
  - Layouts/sec（布局计算频率，越低越好）
  - DOM Nodes（DOM 节点数）

**工具 2：React DevTools Profiler**
- 打开方式：React DevTools → Profiler 标签
- 操作：点击 Record → 执行卡顿操作 → Stop
- 关注：哪些组件渲染耗时最长、渲染次数最多

**工具 3：Chrome DevTools Performance 录制**
- 打开方式：DevTools → Performance 标签 → Record
- 查看：Flame Chart（火焰图），找出耗时最长的函数

#### 4.3.2 优化策略矩阵

| 优化类型 | 优化手段 | 适用场景 | 预期效果 |
|---------|---------|---------|---------|
| **减少渲染** | React.memo | 子组件 props 不变时避免重新渲染 | 减少 30-50% 无效渲染 |
| **减少渲染** | useCallback | 缓存事件处理函数，避免子组件重新渲染 | 减少 20-30% 无效渲染 |
| **减少渲染** | useMemo | 缓存复杂计算结果 | 减少 CPU 占用 |
| **虚拟化** | 调优 Virtuoso 参数 | 长列表（100+ 项） | DOM 节点数减少 90% |
| **动画降级** | 关闭 Framer Motion | Windows 性能差时 | FPS 提升 10-20 |
| **延迟加载** | Monaco Editor 懒加载 | 首次打开编辑器 | 启动时间减少 1-2 秒 |
| **代码分割** | React.lazy + Suspense | 非首屏页面 | 首屏加载时间减少 |

#### 4.3.3 具体优化措施

**前端优化说明**：以下优化基于性能分析工具的实际测量，而非假设。

**现状核实**（已检查代码）：
- ✅ `AssistantMessageItem.tsx:39` 已经用 `memo`
- ✅ `UserMessageItem.tsx:27` 已经用 `memo`
- ✅ `ActionReceipt.tsx:346` 已经用 `memo`
- ✅ `WorkspaceTranscript.tsx:670` 已经配置 Virtuoso（稳定 key、firstItemIndex、followOutput）
- ✅ `animation.store.ts:15` 已经监听 `prefers-reduced-motion`

**结论**：常规的 React 性能优化已经做了，不能盲目地"再加一遍 memo"。

**正确流程**：
1. **先用 Performance Monitor 定位真实热点**：
   - 在 Windows 实际环境下用 Chrome DevTools Performance Monitor 记录
   - 找出哪些操作导致 FPS 下降、CPU 飙高
   - 用 React DevTools Profiler 找出渲染最慢的组件

2. **基于热点数据决定优化方向**：
   - 如果热点是 Monaco Editor：优化编辑器配置或延迟加载
   - 如果热点是 Framer Motion：考虑动画降级
   - 如果热点是某个未 memo 的组件：加 memo
   - 如果热点是 Virtuoso overscan 不够：调整参数

3. **优化后对比验证**：
   - 同样场景下再次测量 FPS、CPU、内存
   - 确认性能提升明显（如 FPS 从 20 提升到 40）

**避免无效劳动**：
- ❌ 不要"看起来应该优化"就动手（可能已经优化过或不是瓶颈）
- ✅ 基于 profiler 数据，针对性优化真正的热点

**优化 2：事件处理函数用 useCallback**

```tsx
// frontend/src/components/workspace/WorkspaceTranscript.tsx

// ❌ 修改前：每次渲染都创建新函数，导致子组件重新渲染
function WorkspaceTranscript() {
  const handleApprove = (id: string) => {
    approveAction(id)
  }
  
  return <ToolTraceCard onApprove={handleApprove} />
}

// ✅ 修改后：缓存函数引用
function WorkspaceTranscript() {
  const handleApprove = useCallback((id: string) => {
    approveAction(id)
  }, []) // 依赖为空，函数永远不变
  
  return <ToolTraceCard onApprove={handleApprove} />
}
```

**优化 3：复杂计算用 useMemo**

```tsx
// ❌ 修改前：每次渲染都重新计算
function MessageList({ messages }) {
  const sortedMessages = messages
    .filter(m => !m.deleted)
    .sort((a, b) => a.timestamp - b.timestamp)
  
  return <div>{sortedMessages.map(...)}</div>
}

// ✅ 修改后：只在 messages 变化时重新计算
function MessageList({ messages }) {
  const sortedMessages = useMemo(() => {
    return messages
      .filter(m => !m.deleted)
      .sort((a, b) => a.timestamp - b.timestamp)
  }, [messages])
  
  return <div>{sortedMessages.map(...)}</div>
}
```

**优化 4：Virtuoso 虚拟滚动调优**

```tsx
// frontend/src/components/workspace/WorkspaceTranscript.tsx

// 当前配置（需检查）
<Virtuoso
  data={transcriptItems}
  itemContent={(index, item) => <TranscriptItemRenderer item={item} />}
  // 可能缺少的优化参数
/>

// 优化后配置
<Virtuoso
  data={transcriptItems}
  itemContent={(index, item) => <TranscriptItemRenderer item={item} />}
  overscan={200}  // 预渲染上下 200px，减少滚动时的白屏
  increaseViewportBy={{ top: 200, bottom: 200 }}  // 增加视口范围
  components={{
    Scroller: TranscriptScroller,  // 自定义滚动容器
  }}
  followOutput="smooth"  // 新消息到达时平滑滚动到底部
/>
```

**可选优化：Framer Motion 动画降级（需慎重）**

**现状**：`animation.store.ts:15` 已经监听 `prefers-reduced-motion`，用户可在系统设置中关闭动画。

**问题**：文档之前建议"Windows 自动降级动画"，但这违背了跨平台一致性原则。

**更稳妥的方案**：

**方案 A（推荐）**：基于实测阈值降级
```tsx
// 仅在实测证明动画是瓶颈时才启用
export const shouldReduceMotion = () => {
  // 1. 用户系统设置（所有平台）
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return true
  }
  
  // 2. 用户手动设置（添加到 UI settings）
  if (useSettingsStore.getState().reduceMotionManually) {
    return true
  }
  
  // 3. 不要按平台一刀切降级（违背一致性原则）
  return false
}
```

**方案 B**：添加用户设置
- 在 Settings 页面添加"减少动画"开关
- 让用户自己决定是否关闭动画（而非代码强制）
- Windows 用户如果觉得卡，可以手动关闭

**不采用的方案**：
- ❌ `navigator.platform.includes('Win')` 自动降级 — 破坏跨平台一致性
- ❌ 没有实测数据就预设 Windows 动画慢 — 可能是过度优化

**结论**：
- 先用 Performance Monitor 测试动画是否真的是瓶颈
- 如果是，优先让用户手动控制（添加设置项）
- 如果实测证明某个特定动画在 Windows 上严重掉帧，才考虑针对性降级该动画

或在关键动画组件中添加条件：

```tsx
// frontend/src/components/animations/SlideIn.tsx

export function SlideIn({ children }: Props) {
  const shouldAnimate = !shouldReduceMotion()
  
  if (!shouldAnimate) {
    // 不使用动画，直接渲染
    return <>{children}</>
  }
  
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
    >
      {children}
    </motion.div>
  )
}
```

**优化 6：Monaco Editor 延迟加载**

```tsx
// frontend/src/components/workspace/CodeEditor.tsx

import { lazy, Suspense } from 'react'

// ❌ 修改前：立即加载 Monaco（打包体积大）
import MonacoEditor from '@monaco-editor/react'

// ✅ 修改后：懒加载
const MonacoEditor = lazy(() => import('@monaco-editor/react'))

export function CodeEditor({ code, language }: Props) {
  return (
    <Suspense fallback={<div>加载编辑器中...</div>}>
      <MonacoEditor
        value={code}
        language={language}
        theme="vs-dark"
        options={{
          minimap: { enabled: false },  // 关闭缩略图（性能优化）
          folding: false,  // 关闭代码折叠
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
        }}
      />
    </Suspense>
  )
}
```

### 4.4 Layer 3：Electron 主进程优化（P2）

#### 4.4.1 启动流程分析

**当前启动流程**（已确认 `main.cjs:148`）：

```
用户双击图标
  ↓
Electron app.whenReady()
  ↓
bootstrap() 函数
  ↓
await backendManager.start()  ← 阻塞在这里（可能 5-10 秒）
  ↓
createWindow({ route: '/agent' })
  ↓
加载 Vite dev server / dist/index.html
  ↓
渲染进程初始化（React 应用启动）
  ↓
界面可用
```

**问题**：`await backendManager.start()` 是同步等待，窗口创建被延迟。

**优化点**：后端启动和窗口显示并行，不阻塞界面

#### 4.4.2 优化方案

**关键问题**：如果先开窗再拉后端，前端需要处理"后端未就绪"的各种状态。

**前端 UX 设计**：

1. **启动阶段**：显示"后端启动中..."加载状态
2. **API 调用失败**：重试 + 降级（显示"后端未就绪，请稍候"）
3. **WebSocket 连接失败**：自动重连 + 提示用户
4. **超时处理**：超过 30 秒仍未就绪，提示用户检查环境

**实现方案（需三处改动）**：

**改动 1：主进程发送状态事件（main.cjs）**

```javascript
// frontend/electron/main.cjs

async function bootstrap() {
  // ✅ 先创建窗口（不等后端）
  createWindow({ route: '/agent' })
  
  // ✅ 后端启动改为后台任务，通过 IPC 通知前端状态
  if (!captureMode) {
    // 启动前通知前端
    mainWindow.webContents.send('backend:status', { status: 'starting' })
    
    backendManager.start()
      .then(() => {
        // 启动成功通知
        mainWindow.webContents.send('backend:status', { status: 'ready' })
      })
      .catch((error) => {
        // 启动失败通知
        mainWindow.webContents.send('backend:status', { 
          status: 'failed', 
          error: error.message 
        })
        
        // 同时显示错误对话框
        dialog.showErrorBox(
          'Backend Startup Failed',
          error instanceof Error ? error.message : '未知后端启动错误',
        )
      })
  }
}
```

**改动 2：preload 暴露事件订阅接口（preload.cjs）**

```javascript
// frontend/electron/preload.cjs

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  selectDirectory: () => ipcRenderer.invoke('dialog:select-directory'),
  getBackendStatus: () => ipcRenderer.invoke('backend:get-status'),
  
  // ✅ 新增：订阅后端状态变化
  onBackendStatus: (callback) => {
    const handler = (_event, status) => callback(status)
    ipcRenderer.on('backend:status', handler)
    // 返回取消订阅函数
    return () => ipcRenderer.removeListener('backend:status', handler)
  },
  
  terminal: {
    // ... 现有终端接口 ...
  },
})
```

**改动 3：类型定义（electron.d.ts）**

```typescript
// frontend/src/types/electron.d.ts

// 后端状态通知（新增，用于启动流程优化）
interface BackendStatus {
  status: 'starting' | 'ready' | 'failed'
  error?: string
}

// 现有后端状态查询接口（保持兼容，来自 main.cjs:258 + electron.d.ts:8）
interface BackendFullStatus {
  state: string          // 'starting' | 'ready' | 'failed'
  url: string            // 后端 URL
  pid: number | null     // 后端进程 PID
  managed: boolean       // 是否由 Electron 管理
  error: string | null   // 错误信息
}

interface ElectronAPI {
  isElectron: boolean
  selectDirectory: () => Promise<string | null>
  
  // 现有接口：查询后端状态（保持不变）
  getBackendStatus: () => Promise<BackendFullStatus>
  
  // ✅ 新增：后端状态订阅（用于启动流程优化）
  onBackendStatus?: (callback: (status: BackendStatus) => void) => () => void
  
  terminal: {
    // ...
  }
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}
```
```

**前端监听后端状态**：

```tsx
// frontend/src/App.tsx（或某个全局组件）

function App() {
  const [backendStatus, setBackendStatus] = useState<'starting' | 'ready' | 'failed'>('starting')
  
  useEffect(() => {
    // 监听后端状态变化
    const unsubscribe = window.electronAPI?.onBackendStatus?.((status) => {
      setBackendStatus(status.status)
    })
    
    return unsubscribe
  }, [])
  
  if (backendStatus === 'starting') {
    return <div>后端启动中，请稍候...</div>
  }
  
  if (backendStatus === 'failed') {
    return <div>后端启动失败，请检查环境配置</div>
  }
  
  // backendStatus === 'ready'，正常渲染应用
  return <RouterProvider router={router} />
}
```

**API 调用降级**：

```ts
// frontend/src/services/apiClient.ts

// 在 axios interceptor 中处理后端未就绪
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.code === 'ECONNREFUSED') {
      // 后端未就绪，显示友好提示
      useToastStore.getState().addToast('warning', '后端服务尚未就绪，请稍候...')
      
      // 可选：自动重试
      return retryRequest(error.config)
    }
    
    return Promise.reject(error)
  }
)
```

**优化效果**：
- ✅ 窗口立即打开（用户感知快）
- ✅ 后端启动中有明确提示（不是白屏等待）
- ✅ 启动失败有清晰的错误信息
- ✅ 自动重连机制（后端延迟启动也能正常工作）

// ✅ 优化 3：窗口创建时设置 show: false，加载完成后再显示
function createWindow(options = {}) {
  const route = options.route || '/agent'

  mainWindow = new BrowserWindow({
    width: options.width || 1440,
    height: options.height || 920,
    minWidth: 1180,
    minHeight: 760,
    title: 'ReflexionOS',
    backgroundColor: '#f8fafc',
    show: false,  // ← 先不显示
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  // 加载完成后再显示（避免白屏）
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  // ...
}
```

#### 4.4.3 硬件加速

确保启用硬件加速（默认已开启，但可能被意外关闭）：

```javascript
// frontend/electron/main.cjs

// 确保不要调用这个（会关闭硬件加速）
// app.disableHardwareAcceleration()

// 检查硬件加速状态
console.log('Hardware acceleration enabled:', !app.commandLine.hasSwitch('disable-hardware-acceleration'))
```

### 4.5 跨平台测试策略

#### 4.5.1 测试矩阵

**优先级说明**：
- **P0（必须）**：Windows 功能验证 + macOS/Linux 回归测试
- **P1（推荐）**：性能基准对比（确保 macOS/Linux 性能不降）

| 平台 | 版本 | 测试环境 | 测试内容 | 优先级 |
|------|------|---------|---------|--------|
| Windows 10 | 22H2 | 物理机 / VM | 完整功能 + 性能测试 | P0 |
| Windows 11 | 23H2 | 物理机 / VM | 完整功能 + 性能测试 | P0 |
| macOS | 13+ | 物理机 | **回归测试（确保功能和性能不受影响）** | P0 |
| Linux | Ubuntu 22.04 | VM | **回归测试（确保功能和性能不受影响）** | P0 |

#### 4.5.2 测试用例

**Shell 兼容性测试**：
1. ✅ `git status` 输出正确
2. ✅ `git log --oneline -10` 输出正确
3. ✅ `git diff HEAD` 输出正确
4. ✅ 包含空格的路径（`C:\Program Files\...`）
5. ✅ 包含中文的路径和文件名
6. ✅ `rg` 或 `grep` 搜索中文内容

**性能基准测试**：
1. ✅ 启动时间：从双击到界面可用 < 5 秒
2. ✅ 滚动性能：滚动 100 条消息，FPS > 30
3. ✅ 输入延迟：聊天框输入 < 100ms
4. ✅ 内存占用：运行 1 小时 < 300MB

**回归测试（重点：macOS/Linux 不受影响）**：

**自动化测试（开发机）**：
1. ✅ 后端单元测试在开发机（Windows + macOS 或 Linux）上通过（`pytest`）
2. ✅ 前端单元测试通过（`vitest`）

**手工回归测试（在一台 macOS 或 Linux 机器上）**：
3. ✅ git 命令正常（status、log、commit）
4. ✅ 文件搜索正常（grep/rg）
5. ✅ 对话功能正常（发送消息、查看回复）
6. ✅ 代码编辑正常（Monaco Editor）
7. ✅ 主观感受：启动速度、滚动流畅度、输入响应与之前无明显差异

**代码审查（人工）**：
8. ✅ 检查 `command_policy.py`、`shell_tool.py` 的改动：Windows 逻辑在单独分支
9. ✅ 检查前端组件改动：没有"Windows 专属降级"逻辑
10. ✅ 确认没有"为了统一而修改 Unix 代码路径"的改动

---

## 5. 实现计划

### 5.1 阶段划分

#### 阶段 1：Shell 兼容性修复（1-2 天，P0）

**目标**：让 git 命令在 Windows 上可用

**任务**：
1. 修改 `backend/app/security/command_policy.py:268` — 实现 Windows shell 严格白名单 gate
2. 实现 `_extract_meta_chars()` — quote-aware 元字符提取
3. 实现 `_split_shell_command()` — 按 `&&` / `||` 拆分命令链
4. 实现 git 子命令白名单检查 — 只允许 status/log/diff/show（4 个纯读子命令）
5. 集成路径参数校验 — 调用 `shell_security._validate_path_arguments(argv[2:], path_security)`
6. 修改 `backend/app/tools/shell_tool.py:349` — 实现 Windows cmd.exe 执行分支
7. 路径校验 — 使用 `path_security.validate_path(cwd)` 检查工作目录
8. 网络命令拒绝 — 继续 DENY `effect_category == NETWORK_OUT`
9. 审计日志 — 记录 Windows shell 命令执行
10. 编码处理 — UTF-8 优先，GBK 回退
11. 编写单元测试 — 跨平台测试 + 白名单测试 + 路径参数测试
12. 手工测试 git 命令（status、log、diff、show 及它们的命令链）
13. 验证拒绝场景（带元字符的写命令链、重定向、路径逃逸、非 git 命令链）

**验收标准**（本阶段范围：Windows shell 带元字符命令）：
- ✅ Windows 上执行 `git status && git log` 命令链成功
- ✅ Windows 上执行 `git diff README.md && git show HEAD` 命令链成功
- ✅ Windows 上执行 `git diff README.md && git log` 路径参数通过校验（在白名单内）
- ✅ Windows 上执行 `git diff C:\evil\path && echo test` 被正确拒绝（路径不在白名单）
- ✅ Windows 上执行 `git branch && echo test` 被正确拒绝（有写能力子命令）
- ✅ Windows 上执行 `git add . && git commit -m "test"` 被正确拒绝（写操作命令链）
- ✅ Windows 上执行 `git status > output.txt` 被正确拒绝（禁止重定向）
- ✅ Windows 上执行 `ls && echo test` 被正确拒绝（非 git 命令链）
- ✅ 包含中文文件名的项目路径可正常工作
- ✅ **macOS/Linux 回归测试通过（功能零破坏）**
- ✅ 代码审查确认：Windows 逻辑在单独分支，未修改 Unix 代码路径
- **注意**：无元字符命令（如单独的 `git add .`、`git branch`）不在本阶段范围，继续走原有 Windows argv hard deny

#### 阶段 2：前端性能优化（1-2 天，P1）

**目标**：消除卡顿，提升渲染流畅度

**任务**：
1. **Profiling 先行（必须第一步）**：
   - 用 Chrome DevTools Performance Monitor 记录滚动/输入场景的帧率和 CPU 时间
   - 用 React DevTools Profiler 记录组件渲染次数和耗时
   - 列出 Top 5 热点组件/函数（按耗时排序）
2. **针对性优化（基于 profiling 结果）**：
   - **仅对 Top 5 热点组件**添加 `React.memo` / `useCallback` / `useMemo`
   - 若 Virtuoso 出现在热点中，调优其参数（overscan、increaseViewportBy）
   - 若 Framer Motion 出现在热点中，评估性能影响（但不搞"Windows 专属降级"）
   - 若 Monaco Editor 加载阻塞渲染，改为懒加载
3. **验证优化效果（用相同 profiling 工具再测一遍）**

**验收标准**：
- ✅ Profiling 结果显示：滚动 100 条消息时 FPS > 30（DevTools 测量）
- ✅ Performance Monitor 显示 JS heap size 稳定（无泄漏）
- ✅ React DevTools Profiler 显示 Top 5 热点组件渲染次数减少 30%+
- ✅ 优化前后有对比数据（截图/JSON 报告）

#### 阶段 3：Electron 优化 + 全面测试（1 天，P2）

**目标**：提升启动速度，全面验证

**任务**：
1. 优化 Electron 启动流程（窗口和后端并行启动）
2. 确保硬件加速开启
3. 编写性能基准测试脚本（自动化测量启动时间、FPS）
4. 在 Windows 10/11 上全面测试
5. macOS/Linux 回归测试
6. 文档更新（README、troubleshooting）

**验收标准**：
- ✅ 启动时间 < 5 秒
- ✅ 所有测试用例通过
- ✅ 无新增 bug

### 5.2 时间估算

| 阶段 | 工作量 | 时间 |
|------|--------|------|
| 阶段 1：Shell 兼容性 | 1-2 人天 | 1-2 天 |
| 阶段 2：前端性能优化 | 1-2 人天 | 1-2 天 |
| 阶段 3：Electron 优化 + 测试 | 0.5-1 人天 | 1 天 |
| **总计** | **2.5-5 人天** | **3-5 天** |

---

## 6. 风险与降级方案

### 6.1 风险识别

#### 风险 1：Shell 适配可能破坏现有功能（最高风险）

**概率**：中  
**影响**：高（可能导致 macOS/Linux 用户无法使用）  
**为什么是最高风险**：Shell 工具是核心功能，任何破坏都会导致 git、搜索等功能失效

**缓解措施（强化）**：
1. **代码隔离铁律**：
   - macOS/Linux 代码路径零修改
   - Windows 逻辑必须在 `if platform.system() == "Windows":` 分支内
   - 代码审查时重点检查：是否有"统一所有平台"的改动
2. **测试先行**：
   - 写代码前先写跨平台测试用例
   - 每个 commit 都在 macOS/Linux 上验证
3. **单元测试覆盖**：
   - 为 `execute_command` 添加 mock 测试
   - 验证不同 `platform.system()` 返回值下的行为
4. **人工回归测试**：
   - 在 macOS 物理机上手工测试 git 命令
   - 在 Linux VM 上手工测试 git 命令

**降级方案**：
- 如果 macOS/Linux 出现问题，立即回滚该 commit
- 通过环境变量 `REFLEXION_DISABLE_WINDOWS_SHELL_COMPAT=1` 关闭 Windows 特殊逻辑（应急开关）

#### 风险 2：性能优化引入新 bug

**概率**：中  
**影响**：中（可能导致 UI 渲染错误、内存泄漏）  
**缓解措施**：
- 每个优化独立提交（小步快跑）
- 用 React DevTools 和单元测试验证
- 在开发环境充分测试后再合并

**降级方案**：
- 每个优化是独立的 commit，出问题可单独 revert
- 保留性能测试脚本，随时验证是否退化

#### 风险 3：时间估算不准

**概率**：高  
**影响**：低（延期但不影响质量）  
**缓解措施**：
- 按优先级分阶段（P0 > P1 > P2）
- P0 完成即可先发布，P1/P2 后续迭代

**降级方案**：
- 如果时间紧张，P2 阶段可推迟到下个版本

#### 风险 4：Windows 路径特殊字符问题

**概率**：中  
**影响**：中（某些特殊路径无法使用）  
**缓解措施**：
- 测试用例覆盖特殊字符（空格、中文、`&`、`()`）
- cmd.exe 路径转义：用双引号包裹 `"C:\path with spaces"`，不使用 shlex.quote（POSIX 语义）

**降级方案**：
- 对无法处理的特殊字符，在 UI 提示用户避免使用

### 6.2 监控与回滚

**监控指标**：
- 后端：Shell 命令成功率（通过日志统计）
- 前端：FPS（通过 Performance API 采集）
- 前端：内存占用（定期采样 `performance.memory`）
- 用户反馈：通过 GitHub Issues 收集

**回滚策略**：
- 每个阶段独立提交到 Git
- 发现严重问题时，`git revert` 回滚对应 commit
- 保留性能测试基准，确保回滚后性能不退化

---

## 7. 验收标准

### 7.1 功能验收

**Shell 兼容性**：
- ✅ Windows 上执行 `git status` 返回正确输出
- ✅ Windows 上执行 `git log` 返回正确输出
- ✅ Windows 上执行 `rg` 或 `grep` 返回正确结果
- ✅ 包含空格的路径正常工作（如 `C:\Program Files\Project\`）
- ✅ 包含中文的路径和文件名正常工作（如 `C:\Users\张三\项目\测试.py`）
- ✅ **（关键）macOS 和 Linux 上现有功能不受影响（回归测试通过）**
- ✅ **（关键）macOS 和 Linux 代码路径未被修改（代码审查确认）**

### 7.2 性能验收

**量化指标**：
- ✅ 启动时间：从双击到界面可用 < 5 秒（当前未知，目标减少 30%）
- ✅ 滚动性能：滚动 100 条消息时 FPS > 30（用 Chrome DevTools 测量）
- ✅ 输入延迟：聊天框输入到显示 < 100ms（用户感知流畅）
- ✅ 内存占用：运行 1 小时后 JS heap size < 300MB（避免泄漏）

**主观评价**：
- ✅ 用户反馈"不卡了"或"明显变快了"

### 7.3 稳定性验收

- ✅ 长时间运行（2 小时+）无崩溃
- ✅ 快速连续操作（快速滚动、快速切换标签）无卡死
- ✅ 特殊字符路径不导致错误

### 7.4 测试覆盖

- ✅ 后端单元测试通过率 100%（新增 Shell 相关测试）
- ✅ 前端单元测试通过率 100%（现有测试不受影响）
- ✅ 手工测试通过（测试用例见第 4.5 节）

---

## 8. 后续优化方向（本期不做）

虽然不在本次范围，但记录未来可优化的点：

1. **更深入的性能监控**：集成 Sentry 或类似工具，采集真实用户的性能数据
2. **离线缓存**：Service Worker 缓存静态资源，加快启动速度
3. **WebAssembly**：将部分计算密集型操作（如 Markdown 解析、Diff 计算）迁移到 WASM
4. **多进程架构**：Electron 主进程、渲染进程、后端进程的进一步优化
5. **增量渲染**：对话历史超长时（1000+ 条），只渲染可见部分 + 最近 100 条
6. **Windows 原生体验**：UI 风格更接近 Windows 11（Fluent Design）

---

## 9. 参考资料

### 9.1 技术文档

- [Electron Performance Guide](https://www.electronjs.org/docs/latest/tutorial/performance)
- [React Performance Optimization](https://react.dev/learn/render-and-commit#optimizing-performance)
- [Python asyncio subprocess](https://docs.python.org/3/library/asyncio-subprocess.html)
- [pathlib — Object-oriented filesystem paths](https://docs.python.org/3/library/pathlib.html)
- [react-virtuoso Documentation](https://virtuoso.dev/)

### 9.2 项目内部文档

- [项目状态文档](../../PROJECT_STATUS.md)
- [目录结构](../../DIRECTORY_TREE.md)
- [已知问题报告](../../../项目问题报告.md)

### 9.3 相关 Issue

（待补充 GitHub Issues 链接）

---

## 10. 变更记录

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|---------|
| v1.0 | 2026-06-29 | Claude + Ethan | 初始版本，包含 Shell 兼容性修复和性能优化方案 |

---

**文档结束**
