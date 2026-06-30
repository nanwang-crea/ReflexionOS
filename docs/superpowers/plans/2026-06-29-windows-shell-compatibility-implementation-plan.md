# Windows Shell 兼容性实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Windows 平台支持**带元字符的 git 命令链**（如 `git status && git log`），通过严格白名单和路径参数校验实现部分安全语义对齐

**Architecture:** 在策略层（command_policy.py）添加 Windows shell 白名单 gate（仅对 `has_meta=True` 命令生效），只允许 4 个纯读 git 子命令的 `&&`/`||` 组合，复用 shell_security._validate_path_arguments 校验路径参数；在执行层（shell_tool.py）实现 cmd.exe 执行分支

**重要约束**：本计划只处理带元字符（`&&`/`||`）的命令，无元字符的单个命令（如 `git add .`、`git branch`）不在本计划范围，走 argv 路径在 Windows 上可以正常执行

**Tech Stack:** Python 3.12, shlex, asyncio, cmd.exe

---

## 前置说明

### 设计约束

1. **跨平台隔离**：所有 Windows 特殊逻辑必须在 `if sys.platform == "win32"` 分支内，macOS/Linux 代码路径零改动
2. **安全语义部分对齐**：路径参数通过 `_validate_path_arguments` 校验（与 argv 模式等价），但仍弱于 Unix sandbox 整命令包裹
3. **保守白名单策略**：第一阶段只支持 4 个纯读 git 子命令（status/log/diff/show），禁止 branch/remote/add/commit 等

### 关键文件

**策略层**：
- `backend/app/security/command_policy.py:168` — 当前 Windows shell hard deny 位置
- `backend/app/security/shell_security.py:108` — 可复用的路径参数校验

**执行层**：
- `backend/app/tools/shell_tool.py:349` — 当前 Windows shell hard deny 位置

**测试**：
- `backend/tests/test_security/test_command_policy.py` — 策略层单元测试
- `backend/tests/test_tools/test_shell_tool.py` — 执行层单元测试

---

## Task 1: 实现元字符提取工具（quote-aware）

**Files:**
- Modify: `backend/app/security/command_policy.py`

**目标**：实现 `_extract_meta_chars()` 方法，能够识别命令中的 shell 元字符（忽略引号内的字符）

- [ ] **Step 1: 添加 _extract_meta_chars 方法框架**

在 `CommandPolicy` 类中添加方法（在 `_evaluate_shell_command` 方法之前）：

```python
def _extract_meta_chars(self, command: str) -> set[str]:
    """
    提取命令中的 shell 元字符（quote-aware，忽略引号内的字符）
    
    Args:
        command: shell 命令字符串
        
    Returns:
        使用的元字符集合（如 {'&&', '||', '>'}）
    """
    meta_chars = set()
    
    # 使用 shlex 解析，识别引号边界
    # 注意：这里只是找元字符，不完全解析命令
    in_single_quote = False
    in_double_quote = False
    i = 0
    
    while i < len(command):
        char = command[i]
        
        # 跟踪引号状态
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            i += 1
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            i += 1
            continue
        
        # 在引号内，跳过
        if in_single_quote or in_double_quote:
            i += 1
            continue
        
        # 检查双字符元字符（&&、||、>>、2>）
        if i + 1 < len(command):
            two_char = command[i:i+2]
            if two_char in {'&&', '||', '>>', '2>'}:
                meta_chars.add(two_char)
                i += 2
                continue
        
        # 检查单字符元字符
        if char in {'|', '<', '>', ';', '&'}:
            meta_chars.add(char)
        
        i += 1
    
    return meta_chars
```

- [ ] **Step 2: 编写测试用例**

在 `backend/tests/test_security/test_command_policy.py` 末尾添加：

```python
def test_extract_meta_chars_basic():
    """测试基本元字符提取"""
    policy = CommandPolicy(...)  # 使用现有 fixture
    
    # 测试双字符元字符
    assert policy._extract_meta_chars("git status && git log") == {'&&'}
    assert policy._extract_meta_chars("cmd1 || cmd2") == {'||'}
    assert policy._extract_meta_chars("echo test >> file.txt") == {'>>'}
    
    # 测试单字符元字符
    assert policy._extract_meta_chars("echo test > file.txt") == {'>'}
    assert policy._extract_meta_chars("cmd1 ; cmd2") == {';'}
    assert policy._extract_meta_chars("cmd1 | cmd2") == {'|'}
    
    # 测试混合
    assert policy._extract_meta_chars("cmd1 && cmd2 || cmd3") == {'&&', '||'}


def test_extract_meta_chars_quote_aware():
    """测试引号内元字符忽略"""
    policy = CommandPolicy(...)
    
    # 单引号内的元字符应该被忽略
    assert policy._extract_meta_chars("echo 'a && b'") == set()
    assert policy._extract_meta_chars("git commit -m 'fix: issue || bug'") == set()
    
    # 双引号内的元字符应该被忽略
    assert policy._extract_meta_chars('echo "a && b"') == set()
    
    # 引号外的元字符应该被识别
    assert policy._extract_meta_chars("echo 'test' && git status") == {'&&'}
    assert policy._extract_meta_chars('git log && echo "done"') == {'&&'}
```

- [ ] **Step 3: 运行测试验证失败**

```bash
cd backend
pytest tests/test_security/test_command_policy.py::test_extract_meta_chars_basic -v
pytest tests/test_security/test_command_policy.py::test_extract_meta_chars_quote_aware -v
```

预期：两个测试都 PASS（方法已在 Step 1 实现）

- [ ] **Step 4: 提交**

```bash
git add backend/app/security/command_policy.py backend/tests/test_security/test_command_policy.py
git commit -m "feat(security): 添加 quote-aware 元字符提取方法

- 实现 CommandPolicy._extract_meta_chars() 方法
- 支持识别 &&、||、>、>>、2>、|、<、;、& 元字符
- 忽略单引号和双引号内的元字符
- 添加单元测试覆盖基本场景和引号场景

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: 实现命令链拆分工具

**Files:**
- Modify: `backend/app/security/command_policy.py`

**目标**：实现 `_split_shell_command()` 方法，按 `&&` 和 `||` 拆分命令链

- [ ] **Step 1: 添加 _split_shell_command 方法**

在 `CommandPolicy` 类中添加方法（在 `_extract_meta_chars` 之后）：

```python
def _split_shell_command(self, command: str) -> list[str]:
    """
    按 && 和 || 拆分命令链（quote-aware）
    
    Args:
        command: shell 命令字符串
        
    Returns:
        命令片段列表
    """
    segments = []
    current_segment = []
    in_single_quote = False
    in_double_quote = False
    i = 0
    
    while i < len(command):
        char = command[i]
        
        # 跟踪引号状态
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current_segment.append(char)
            i += 1
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current_segment.append(char)
            i += 1
            continue
        
        # 在引号内，直接添加
        if in_single_quote or in_double_quote:
            current_segment.append(char)
            i += 1
            continue
        
        # 检查 && 或 ||
        if i + 1 < len(command):
            two_char = command[i:i+2]
            if two_char in {'&&', '||'}:
                # 保存当前片段
                segment_str = ''.join(current_segment).strip()
                if segment_str:
                    segments.append(segment_str)
                current_segment = []
                i += 2
                continue
        
        # 普通字符
        current_segment.append(char)
        i += 1
    
    # 保存最后一个片段
    segment_str = ''.join(current_segment).strip()
    if segment_str:
        segments.append(segment_str)
    
    return segments
```

- [ ] **Step 2: 编写测试用例**

在 `backend/tests/test_security/test_command_policy.py` 末尾添加：

```python
def test_split_shell_command_basic():
    """测试基本命令链拆分"""
    policy = CommandPolicy(...)
    
    # 单个命令
    assert policy._split_shell_command("git status") == ["git status"]
    
    # && 拆分
    assert policy._split_shell_command("git status && git log") == [
        "git status",
        "git log"
    ]
    
    # || 拆分
    assert policy._split_shell_command("cmd1 || cmd2") == ["cmd1", "cmd2"]
    
    # 混合拆分
    assert policy._split_shell_command("cmd1 && cmd2 || cmd3") == [
        "cmd1",
        "cmd2",
        "cmd3"
    ]


def test_split_shell_command_quote_aware():
    """测试引号内操作符不拆分"""
    policy = CommandPolicy(...)
    
    # 单引号内的 && 不应拆分
    assert policy._split_shell_command("echo 'a && b'") == ["echo 'a && b'"]
    
    # 双引号内的 || 不应拆分
    assert policy._split_shell_command('echo "a || b"') == ['echo "a || b"']
    
    # 引号外的操作符应拆分
    assert policy._split_shell_command("echo 'test' && git status") == [
        "echo 'test'",
        "git status"
    ]
```

- [ ] **Step 3: 运行测试验证**

```bash
pytest tests/test_security/test_command_policy.py::test_split_shell_command_basic -v
pytest tests/test_security/test_command_policy.py::test_split_shell_command_quote_aware -v
```

预期：所有测试 PASS

- [ ] **Step 4: 提交**

```bash
git add backend/app/security/command_policy.py backend/tests/test_security/test_command_policy.py
git commit -m "feat(security): 添加 quote-aware 命令链拆分方法

- 实现 CommandPolicy._split_shell_command() 方法
- 按 && 和 || 拆分命令链
- 忽略引号内的操作符
- 添加单元测试覆盖基本场景和引号场景

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: 实现 Windows shell 白名单 gate（策略层核心）

**Files:**
- Modify: `backend/app/security/command_policy.py:168`

**目标**：替换 Windows shell hard deny，实现严格白名单检查（元字符 + 子命令 + 路径参数）

- [ ] **Step 1: 替换 hard deny 为白名单检查**

找到 `backend/app/security/command_policy.py:168` 的代码块：

```python
if result.has_meta and self.shell_security._is_windows():
    return CommandDecision(
        action=CommandAction.DENY,
        command=command,
        execution_mode="shell",
        cwd=resolved_cwd,
        timeout=timeout,
        reasons=["Windows shell 模式尚未支持"],
        environment_snapshot=snapshot,
    )
```

替换为：

```python
if result.has_meta and self.shell_security._is_windows():
    # ========== Windows 第一阶段：严格白名单策略 ==========
    # 原因：Windows 无 sandbox.wrap_shell_command，无法约束命令内自由路径参数
    # 策略：(1) 只放行纯读的 git 子命令；(2) 复用 shell_security._validate_path_arguments 校验路径参数
    
    # 检查元字符：第一阶段只支持 && 和 ||（命令链）
    supported_on_windows = {'&&', '||'}
    unsupported_on_windows = {'|', '<', '>', '>>', '2>', '&', ';'}
    
    used_meta = self._extract_meta_chars(command_normalized)
    unsupported_used = used_meta & unsupported_on_windows
    
    if unsupported_used:
        return CommandDecision(
            action=CommandAction.DENY,
            command=command,
            execution_mode="shell",
            cwd=resolved_cwd,
            timeout=timeout,
            reasons=[f"Windows 第一阶段不支持这些 shell 特性：{', '.join(unsupported_used)}"],
            environment_snapshot=snapshot,
        )
    
    # 拆分命令链（按 && 和 || 拆）
    segments = self._split_shell_command(command_normalized)
    
    for segment in segments:
        segment_normalized = segment.strip()
        
        # 检查是否是 git 命令
        if not segment_normalized.startswith('git '):
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                execution_mode="shell",
                cwd=resolved_cwd,
                timeout=timeout,
                reasons=[f"Windows 第一阶段只支持 git 命令，不支持: {segment_normalized}"],
                environment_snapshot=snapshot,
            )
        
        # 解析命令为 argv（用于后续路径校验）
        try:
            segment_argv = shlex.split(segment_normalized, posix=False)  # Windows 用非 POSIX 模式
        except ValueError as e:
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                execution_mode="shell",
                cwd=resolved_cwd,
                timeout=timeout,
                reasons=[f"命令解析失败: {e}"],
                environment_snapshot=snapshot,
            )
        
        if len(segment_argv) < 2:
            return CommandDecision(
                action=CommandAction.DENY,
                command=command,
                execution_mode="shell",
                cwd=resolved_cwd,
                timeout=timeout,
                reasons=["git 命令缺少子命令"],
                environment_snapshot=snapshot,
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
                cwd=resolved_cwd,
                timeout=timeout,
                reasons=[f"Windows 第一阶段只支持纯读 git 命令，不支持: git {git_subcommand}"],
                environment_snapshot=snapshot,
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
                cwd=resolved_cwd,
                timeout=timeout,
                reasons=[f"路径参数不在允许范围: {e}"],
                environment_snapshot=snapshot,
            )
    
    # 通过白名单检查：继续走 shell 执行流程
    # 注意：macOS/Linux 的逻辑不修改
```

- [ ] **Step 2: 添加 shlex 导入**

在文件顶部导入区域添加：

```python
import shlex
```

- [ ] **Step 3: 编写白名单测试用例**

在 `backend/tests/test_security/test_command_policy.py` 末尾添加：

```python
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
def test_windows_shell_whitelist_allowed():
    """测试 Windows shell 白名单允许的命令链（带元字符）"""
    policy = CommandPolicy(...)
    
    # 允许的纯读 git 命令链（只有这些走 Windows shell 白名单分支）
    result = policy.evaluate("git status && echo 'done'")
    assert result.action != CommandAction.DENY
    
    result = policy.evaluate("git log --oneline -5 && echo 'done'")
    assert result.action != CommandAction.DENY
    
    result = policy.evaluate("git diff HEAD~1 && echo 'done'")
    assert result.action != CommandAction.DENY
    
    result = policy.evaluate("git show HEAD && echo 'done'")
    assert result.action != CommandAction.DENY
    
    # 允许多个纯读 git 子命令链接
    result = policy.evaluate("git status && git log --oneline -3")
    assert result.action != CommandAction.DENY


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
def test_windows_shell_whitelist_denied():
    """测试 Windows shell 白名单拒绝的命令（仅测试带元字符的）"""
    policy = CommandPolicy(...)
    
    # 拒绝有写能力的 git 子命令链
    result = policy.evaluate("git branch && echo test")
    assert result.action == CommandAction.DENY
    assert "只支持纯读 git 命令" in result.reasons[0]
    
    result = policy.evaluate("git remote && echo test")
    assert result.action == CommandAction.DENY
    
    result = policy.evaluate("git add . && git commit -m 'test'")
    assert result.action == CommandAction.DENY
    
    # 拒绝非 git 命令链
    result = policy.evaluate("ls && echo test")
    assert result.action == CommandAction.DENY
    assert "只支持 git 命令" in result.reasons[0]
    
    # 拒绝不支持的元字符
    result = policy.evaluate("git status > output.txt")
    assert result.action == CommandAction.DENY
    assert "不支持这些 shell 特性" in result.reasons[0]
    
    result = policy.evaluate("git status | grep test")
    assert result.action == CommandAction.DENY
```

- [ ] **Step 4: 运行测试**

```bash
# 如果在 Windows 上：
pytest tests/test_security/test_command_policy.py::test_windows_shell_whitelist_allowed -v
pytest tests/test_security/test_command_policy.py::test_windows_shell_whitelist_denied -v

# 如果在 macOS/Linux 上（测试会被跳过）：
pytest tests/security/test_command_policy.py -k windows_shell -v
```

预期：Windows 上测试 PASS，macOS/Linux 上测试被跳过

- [ ] **Step 5: 提交**

```bash
git add backend/app/security/command_policy.py backend/tests/test_security/test_command_policy.py
git commit -m "feat(security): 实现 Windows shell 严格白名单 gate

- 替换 Windows shell hard deny 为白名单检查
- 只允许 4 个纯读 git 子命令（status/log/diff/show）
- 元字符限制：只支持 && 和 ||
- 复用 _validate_path_arguments 校验路径参数
- 拒绝 branch/remote/add/commit 等写操作
- 拒绝重定向（>、>>）和管道（|）
- 添加 Windows 特定单元测试

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: 实现 Windows shell 执行层（cmd.exe）

**Files:**
- Modify: `backend/app/tools/shell_tool.py:349`

**目标**：替换执行层的 Windows hard deny，实现 cmd.exe 执行 + 路径校验 + 网络拒绝

**注意**：文件开头已有 `import sys` 和 `import asyncio`，无需重复添加

- [ ] **Step 1: 替换执行层 hard deny**

找到 `backend/app/tools/shell_tool.py:349` 的代码块：

```python
if sys.platform == "win32":
    return ToolResult(success=False, error="Windows shell 模式尚未支持")
```

替换为：

```python
if sys.platform == "win32":
    # ========== Windows 第一阶段执行分支 ==========
    # 注意：命令内路径参数校验已在策略层完成（command_policy.py）
    #       这里只处理执行层的 cwd 和 sandbox_extra_paths 校验
    
    # 1. 路径限制（部分对齐 Unix sandbox）
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
    
    # 2. 网络权限检查（不对齐，策略层已拒绝）
    allow_network = sandbox_allow_network or (effect_category == EffectCategory.NETWORK_OUT)
    
    # Windows 第一阶段：继续拒绝网络型命令（因无沙箱强制）
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
    
    # 3. 审计日志（与 Unix 一致）
    logger.info(
        "执行 Windows shell 命令: %s, cwd=%s, network=%s, effect=%s",
        command, validated_cwd, allow_network, effect_category
    )
    
    # 构建 Windows 命令（无需语法转换，策略层只允许 && 和 ||）
    process = await asyncio.create_subprocess_shell(
        f'cmd.exe /c "{command}"',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=validated_cwd,
        env=self._build_env(),
    )
    
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        logger.error("Windows shell 命令执行超时: %s", command)
        return ToolResult(success=False, error=f"命令执行超时 ({timeout}秒)")
    
    # 编码处理：UTF-8 优先，GBK 回退
    try:
        stdout_str = stdout.decode('utf-8')
    except UnicodeDecodeError:
        try:
            stdout_str = stdout.decode('gbk')
        except UnicodeDecodeError:
            stdout_str = stdout.decode('utf-8', errors='replace')
    
    try:
        stderr_str = stderr.decode('utf-8')
    except UnicodeDecodeError:
        try:
            stderr_str = stderr.decode('gbk')
        except UnicodeDecodeError:
            stderr_str = stderr.decode('utf-8', errors='replace')
    
    return ToolResult(
        success=(process.returncode == 0),
        output=stdout_str,
        error=stderr_str if process.returncode != 0 else "",
        data={"return_code": process.returncode},
    )
```

- [ ] **Step 2: 添加必要的导入**

确保文件顶部有：

```python
import sys
import asyncio
from ..security.path_security import ExternalPathError
from ..security.effect_category import EffectCategory
```

- [ ] **Step 3: 编写执行层测试**

在 `backend/tests/test_tools/test_shell_tool.py` 末尾添加：

```python
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
@pytest.mark.asyncio
async def test_windows_shell_execute_git_chain(tmp_path):
    """测试 Windows shell 执行 git 命令链"""
    # 准备：在 tmp_path 下初始化一个 git 仓库
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    (tmp_path / "test.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)
    
    # 构造 shell_tool（允许 tmp_path）
    path_security = PathSecurity([str(tmp_path)], base_dir=str(tmp_path))
    shell_security = ShellSecurity()
    registry = CommandEffectRegistry()
    sandbox = NullSandbox()
    shell_tool = ShellTool(shell_security, path_security, registry, sandbox)
    
    # 执行命令链
    result = await shell_tool._execute_shell(
        command="git status && git log --oneline -3",
        cwd=str(tmp_path)
        timeout=30,
        effect_category=EffectCategory.READ_ONLY,
        sandbox_allow_network=False,
        sandbox_extra_paths=None,
    )
    
    assert result.success
    assert "On branch" in result.output or "位于分支" in result.output


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
@pytest.mark.asyncio
async def test_windows_shell_path_validation(tmp_path):
    """测试 Windows shell 路径校验"""
    # 构造 shell_tool（只允许 tmp_path）
    path_security = PathSecurity([str(tmp_path)], base_dir=str(tmp_path))
    shell_security = ShellSecurity()
    registry = CommandEffectRegistry()
    sandbox = NullSandbox()
    shell_tool = ShellTool(shell_security, path_security, registry, sandbox)
    
    # 尝试使用白名单外的 cwd
    result = await shell_tool._execute_shell(
        command="git status && echo test",
        cwd="C:\\Windows\\System32",  # 明确不在允许范围
        timeout=30,
        effect_category=EffectCategory.READ_ONLY,
        sandbox_allow_network=False,
        sandbox_extra_paths=None,
    )
    
    assert not result.success
    assert "工作目录不在允许范围" in result.error


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
@pytest.mark.asyncio
async def test_windows_shell_network_denied(tmp_path):
    """测试 Windows shell 拒绝网络型命令"""
    # 构造 shell_tool（允许 tmp_path）
    path_security = PathSecurity([str(tmp_path)], base_dir=str(tmp_path))
    shell_security = ShellSecurity()
    registry = CommandEffectRegistry()
    sandbox = NullSandbox()
    shell_tool = ShellTool(shell_security, path_security, registry, sandbox)
    
    result = await shell_tool._execute_shell(
        command="curl http://example.com && echo test",
        cwd=str(tmp_path),
        timeout=30,
        effect_category=EffectCategory.NETWORK_OUT,
        sandbox_allow_network=False,
        sandbox_extra_paths=None,
    )
    
    assert not result.success
    assert "不支持网络型 shell 命令" in result.error
```

- [ ] **Step 4: 运行测试**

```bash
# 如果在 Windows 上：
pytest tests/test_tools/test_shell_tool.py::test_windows_shell_execute_git_chain -v
pytest tests/test_tools/test_shell_tool.py::test_windows_shell_path_validation -v
pytest tests/test_tools/test_shell_tool.py::test_windows_shell_network_denied -v

# 如果在 macOS/Linux 上（测试会被跳过）：
pytest tests/tools/test_shell_tool.py -k windows_shell -v
```

预期：Windows 上测试 PASS，macOS/Linux 上测试被跳过

- [ ] **Step 5: 提交**

```bash
git add backend/app/tools/shell_tool.py backend/tests/test_tools/test_shell_tool.py
git commit -m "feat(tools): 实现 Windows shell cmd.exe 执行分支

- 替换执行层 Windows hard deny
- 校验 cwd 和 sandbox_extra_paths 在白名单内
- 继续拒绝网络型命令（第一阶段无沙箱强制）
- 使用 cmd.exe /c 执行命令
- UTF-8 优先，GBK 回退编码处理
- 添加审计日志
- 添加 Windows 特定单元测试

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: 跨平台回归测试

**Files:**
- Run existing tests

**目标**：确保 Windows 改动不影响 macOS/Linux 功能

- [ ] **Step 1: 运行完整测试套件（macOS/Linux）**

```bash
cd backend
pytest tests/test_security/test_command_policy.py -v
pytest tests/test_security/test_sandbox.py -v
pytest tests/test_tools/test_shell_tool.py -v
```

预期：所有测试 PASS，无新增失败

- [ ] **Step 2: 手工测试 git 命令（macOS/Linux）**

在实际的 Electron 应用中测试（走完整的 Agent/会话入口）：

```bash
# 启动开发环境
cd frontend
pnpm dev
```

在对话框中发送以下消息，验证 git 命令执行正常：
- "查看 git 状态" → 应执行 `git status` 并返回正确输出
- "显示最近 5 条 git 日志" → 应执行 `git log --oneline -5` 并返回正确输出
- "先查看状态再查看日志" → 应执行 `git status && git log -5` 并返回两个命令的输出

预期：所有命令成功执行，返回正确的 git 输出

- [ ] **Step 3: 验证 macOS/Linux 代码路径未被修改**

```bash
# 检查 shell_tool.py 中 Unix 分支是否保持原样
git diff HEAD~5 backend/app/tools/shell_tool.py | grep -A 20 "if self.sandbox.is_available()"
```

预期：Unix 分支代码（352-373 行附近）无任何改动

- [ ] **Step 4: 记录回归测试结果**

在 `docs/superpowers/specs/2026-06-29-windows-compatibility-performance-optimization-design.md` 末尾添加：

```markdown
## 回归测试记录（阶段 1 完成后）

**测试日期**：2026-06-29  
**测试平台**：macOS / Linux  
**测试结果**：

- ✅ 所有单元测试通过（0 failures）
- ✅ git status 手工测试通过
- ✅ git log 手工测试通过
- ✅ 命令链（&&）手工测试通过
- ✅ Unix 代码路径零改动（git diff 确认）
- ✅ 性能基准无退化（FPS / 启动时间 / 内存占用）
```

- [ ] **Step 5: 提交测试记录**

```bash
git add docs/superpowers/specs/2026-06-29-windows-compatibility-performance-optimization-design.md
git commit -m "docs: 添加阶段 1 macOS/Linux 回归测试记录

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Windows 端到端测试

**Files:**
- Manual testing on Windows

**目标**：在实际 Windows 环境中验证功能完整性

- [ ] **Step 1: 启动 Windows 开发环境**

```bash
cd frontend
pnpm dev
```

预期：后端和前端都正常启动，无错误日志

- [ ] **Step 2: 测试允许的 git 命令链**

在对话框中依次发送以下消息，验证响应：

1. "先查看状态再查看日志" → 应执行 `git status && git log -5` 并返回两个命令的输出
2. "查看修改并显示最近提交" → 应执行 `git diff && git show HEAD` 并返回两个命令的输出
3. "查看 README.md 修改并显示状态" → 应执行 `git diff README.md && git status` 并返回两个命令的输出

预期：所有命令链成功执行，返回正确的 git 输出

- [ ] **Step 3: 测试拒绝的命令链（白名单外）**

在对话框中依次发送以下消息，验证拒绝行为：

1. "查看分支并显示状态" → 应拒绝执行 `git branch && git status`，提示"只支持纯读 git 命令"
2. "添加文件并提交" → 应拒绝执行 `git add . && git commit -m "test"`，提示"只支持纯读 git 命令"
3. "将 git 状态保存到文件" → 应拒绝执行 `git status > output.txt`，提示"不支持这些 shell 特性"
4. "列出文件并回显" → 应拒绝执行 `ls && echo test`，提示"只支持 git 命令"

预期：所有命令链被正确拒绝，返回明确的错误提示

- [ ] **Step 4: 测试路径参数校验**

在对话框中发送：
- "查看 README.md 修改并显示状态" → 应执行 `git diff README.md && git status` 并返回差异（路径在白名单内）
- "查看 frontend/src/App.tsx 修改并显示日志" → 应执行 `git diff frontend/src/App.tsx && git log -3` 并返回差异（路径在白名单内）
- "查看 C:\evil\path\file.txt 修改并回显" → 应拒绝，提示"路径参数不在允许范围"

预期：白名单内路径允许，白名单外路径拒绝

- [ ] **Step 5: 测试中文路径和文件名**

创建一个包含中文的测试文件：

```bash
cd <项目目录>
echo "测试" > 测试文件.txt
git add 测试文件.txt
git commit -m "测试中文文件名"
```

在对话框中发送：
- "查看 git 状态" → 应正确显示中文文件名（UTF-8 或 GBK 编码正确处理）

预期：中文文件名正确显示，无乱码

- [ ] **Step 6: 记录端到端测试结果**

在 `docs/superpowers/specs/2026-06-29-windows-compatibility-performance-optimization-design.md` 回归测试记录后添加：

```markdown
## Windows 端到端测试记录

**测试日期**：2026-06-29  
**测试平台**：Windows 10/11  
**测试结果**：

### 正向测试（允许的命令链）
- ✅ git status && git log 执行成功
- ✅ git diff && git show HEAD 执行成功
- ✅ 路径参数命令链（git diff README.md && git status）执行成功
- ✅ 路径参数命令链（git diff frontend/src/App.tsx && git log）执行成功

### 负向测试（拒绝的命令链）
- ✅ git branch && git status 被正确拒绝（有写能力子命令）
- ✅ git add . && git commit 被正确拒绝（写操作命令链）
- ✅ 重定向（git status > file）被正确拒绝
- ✅ 非 git 命令链（ls && echo）被正确拒绝
- ✅ 白名单外路径命令链被正确拒绝

### 特殊场景
- ✅ 中文路径和文件名正确处理（无乱码）
- ✅ 包含空格的路径正确处理

### 本阶段不涵盖
- ⚠️ 无元字符命令（如单独的 `git add .`、`git branch`）不在本计划范围
- ⚠️ 这些命令走 argv 路径在 Windows 上可以正常执行
```

- [ ] **Step 7: 提交测试记录**

```bash
git add docs/superpowers/specs/2026-06-29-windows-compatibility-performance-optimization-design.md
git commit -m "docs: 添加 Windows 端到端测试记录

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 验收标准检查

完成以上所有任务后，对照设计文档的验收标准：

**本计划覆盖范围（带元字符的 git 命令链）**：
- [ ] ✅ Windows 上执行 `git status && git log` 命令链成功
- [ ] ✅ Windows 上执行 `git diff && git show HEAD` 命令链成功
- [ ] ✅ Windows 上执行 `git diff README.md && git status` 路径参数通过校验（在白名单内）
- [ ] ✅ Windows 上执行 `git diff C:\evil\path && echo` 被正确拒绝（路径不在白名单）
- [ ] ✅ Windows 上执行 `git branch && git status` 被正确拒绝（有写能力子命令）
- [ ] ✅ Windows 上执行 `git add . && git commit -m "test"` 被正确拒绝（写操作命令链）
- [ ] ✅ Windows 上执行 `git status > output.txt` 被正确拒绝（禁止重定向）
- [ ] ✅ Windows 上执行 `ls && echo test` 被正确拒绝（非 git 命令链）
- [ ] ✅ 包含中文文件名的项目路径可正常工作
- [ ] ✅ macOS/Linux 回归测试通过（功能零破坏）
- [ ] ✅ 代码审查确认：Windows 逻辑在单独分支，未修改 Unix 代码路径

**不在本计划范围**：
- ⚠️ 无元字符命令（如单独的 `git add .`、`git branch`、`ls`）走 argv 路径在 Windows 上可以正常执行
- ⚠️ 性能优化（FPS、启动时间、内存占用）属于阶段 2，不在本计划验收范围

---

## 后续工作（不在本计划范围）

阶段 1 完成后，如需继续优化：

**阶段 2：前端性能优化**（1-2 天）
- Profiling 先行（Chrome DevTools Performance Monitor）
- 针对 Top 5 热点组件优化（memo/useCallback/useMemo）
- Virtuoso 参数调优
- Monaco Editor 懒加载

**阶段 3：Electron 启动优化**（1 天）
- 窗口和后端并行启动
- IPC 通知机制（onBackendStatus）
- 硬件加速确认

**第二阶段 Windows shell 增强**（未来版本）
- 支持 `;` 元字符（需 quote-aware 转换）
- 支持管道（`|`）和重定向（`>`、`>>`）
- 扩展白名单（`git branch -l`、`git remote -v` 等只读子命令）
- AppContainer / Job Objects 沙箱实现整命令包裹
