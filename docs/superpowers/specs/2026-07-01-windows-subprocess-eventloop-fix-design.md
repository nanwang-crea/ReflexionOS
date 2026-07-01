# Windows 子进程执行修复设计文档

## 背景

### 问题定义

在 Windows 上，ReflexionOS 的 shell 工具执行任何 git 命令（包括简单的 `git status` 和命令链 `git status && git log`）都会抛出 `NotImplementedError`，导致整个 shell 功能完全不可用。

错误堆栈：
```
File ".../asyncio/base_events.py", line 528, in _make_subprocess_transport
    raise NotImplementedError
```

### 根本原因

1. **Python asyncio 在 Windows 上的子进程支持限制**
   - `SelectorEventLoop`：**不支持** `create_subprocess_exec/shell`（抛 `NotImplementedError`）
   - `ProactorEventLoop`：**支持** 子进程操作
   - Python 3.12 默认使用 `ProactorEventLoop`

2. **uvicorn --reload 强制覆盖事件循环策略**
   - `uvicorn --reload` 内部用 subprocess 实现热重载
   - `uvicorn/loops/asyncio.py` 的 `asyncio_setup` 函数：
     ```python
     def asyncio_setup(use_subprocess: bool = False) -> None:
         if sys.platform == "win32" and use_subprocess:
             asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
     ```
   - `--reload` 触发 `use_subprocess=True` → 强制设置 `SelectorEventLoop`

3. **覆盖时序问题**
   - `main.py` 在模块导入时设置了 `WindowsProactorEventLoopPolicy()`（已有代码，line 29-30）
   - uvicorn 在启动服务器时**后于** `main.py` 导入，再次调用 `asyncio_setup` 覆盖掉 ProactorEventLoop
   - 最终运行时使用的是 `SelectorEventLoop` → 所有子进程操作失败

### 已验证的事实

- 去掉 `--reload` 启动后，argv 模式的 git 命令（`git status`、`git log`）全部成功执行
- 这证实了根因就是 `--reload` 强制的 `SelectorEventLoop`

### 为什么不能用"设置 policy"方案

**方案**：在 `main.py` 顶部设置 `WindowsProactorEventLoopPolicy()`  
**实测结果**：已实现（line 29-30），但**无效**  
**原因**：uvicorn 的 `asyncio_setup` 在 FastAPI app 启动时**后于** `main.py` 导入执行，覆盖掉了我们的设置  
**限制**：除非完全放弃 `--reload`（开发体验严重下降），否则此方案无法生效

---

## 目标

### 做什么

1. **修复 Windows 子进程执行**：无论用户如何启动后端（带不带 `--reload`），所有 git 命令都能正常执行
2. **跨平台兼容**：macOS/Linux 现有功能和性能 **零影响**
3. **保持开发体验**：用户可以继续使用 `--reload` 进行热重载开发

### 不做什么

1. 不改变 macOS/Linux 的代码执行路径（必须保持原有的异步 subprocess 实现）
2. 不引入新的外部依赖
3. 不修改 uvicorn 的启动方式或参数（用户无感）

---

## 用户故事

### 开发者视角

**当前（Bug 状态）**：
```bash
# 启动后端（开发常用方式）
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 在 ReflexionOS 桌面端输入任意 git 命令
用户输入: git status
结果: Shell 执行失败（NotImplementedError）
```

**修复后（期望行为）**：
```bash
# 启动后端（任意方式都可以）
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# 或者
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 在 ReflexionOS 桌面端输入 git 命令
用户输入: git status
结果: ✓ 执行成功，返回 git 仓库状态

用户输入: git status && git log --oneline -5
结果: ✓ 执行成功（白名单允许，Windows shell 模式运行）
```

---

## 方案设计

### 核心思路

**不依赖事件循环的子进程支持，改用线程池执行同步 subprocess**

- Windows：`await loop.run_in_executor(None, lambda: subprocess.run(...))`
  - 在线程池中运行同步的 `subprocess.run`
  - 同步 subprocess 不依赖事件循环的 `create_subprocess_*` 支持
  - 在任何事件循环（Selector/Proactor）下都能工作
- macOS/Linux：保持现有的 `asyncio.create_subprocess_exec/shell`（零改动）

### 架构

修改点集中在 `backend/app/tools/shell_tool.py` 的两个执行方法：

1. **`_execute_argv` 方法**（line ~288）
   - 当前 Windows 分支：使用 `create_subprocess_shell`（会失败）
   - 修复后 Windows 分支：`loop.run_in_executor` + 同步 `subprocess.run`
   - macOS/Linux 分支：保持 `create_subprocess_exec`（不变）

2. **`_execute_shell` 方法**（line ~349-430）
   - 当前 Windows 分支（line ~428）：使用 `create_subprocess_shell`（会失败）
   - 修复后 Windows 分支：`loop.run_in_executor` + 同步 `subprocess.run`
   - macOS/Linux 分支：保持 `create_subprocess_shell`（不变）

### 数据流

**修复前（Windows 失败路径）**：
```
shell_tool._execute_argv/shell
  → asyncio.create_subprocess_exec/shell
    → SelectorEventLoop._make_subprocess_transport
      → raise NotImplementedError ✗
```

**修复后（Windows 成功路径）**：
```
shell_tool._execute_argv/shell (Windows 分支)
  → loop.run_in_executor(None, _sync_subprocess_wrapper)
    → 线程池
      → subprocess.run (同步调用，直接 fork/spawn)
        → 子进程启动成功 ✓
```

**macOS/Linux（保持不变）**：
```
shell_tool._execute_argv/shell (非 Windows 分支)
  → asyncio.create_subprocess_exec/shell
    → ProactorEventLoop/Unix loop (原生支持)
      → 子进程启动成功 ✓
```

### 代码结构

#### 1. `_execute_argv` 修改

**当前实现**（line ~288-312）：
```python
async def _execute_argv(self, argv: list[str], cwd: str, timeout: int) -> ShellResult:
    # Windows 上 asyncio.create_subprocess_exec 不可用，需要用 shell 模式
    if sys.platform == "win32":
        command_str = " ".join(shlex.quote(arg) for arg in argv)
        process = await asyncio.create_subprocess_shell(  # ← 这里会失败
            command_str, ...
        )
    else:
        process = await asyncio.create_subprocess_exec(*argv, ...)
```

**修复后**：
```python
async def _execute_argv(self, argv: list[str], cwd: str, timeout: int) -> ShellResult:
    if sys.platform == "win32":
        # Windows: 用线程池执行同步 subprocess，不依赖事件循环的子进程支持
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,  # 使用默认线程池
            self._sync_subprocess_run,  # 同步执行函数
            argv,
            cwd,
            timeout,
        )
        return result
    else:
        # macOS/Linux: 保持原有异步 subprocess（零改动）
        process = await asyncio.create_subprocess_exec(*argv, ...)
        # ... 原有逻辑
```

#### 2. `_execute_shell` 修改

**当前 Windows 分支**（line ~428）：
```python
process = await asyncio.create_subprocess_shell(
    shell_command,  # cmd.exe /c "{command}"
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=cwd,
    env=self._build_env(),
)
```

**修复后**：
```python
if sys.platform == "win32":
    # Windows: 线程池 + 同步 subprocess
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        self._sync_subprocess_run_shell,  # shell 模式的同步执行函数
        shell_command,
        cwd,
        timeout,
    )
    return result
else:
    # macOS/Linux: 保持原有异步 subprocess（零改动）
    process = await asyncio.create_subprocess_shell(...)
    # ... 原有逻辑
```

#### 3. 新增同步执行辅助函数

在 `ShellTool` 类内新增两个私有方法（仅 Windows 分支调用）：

```python
def _sync_subprocess_run(
    self,
    argv: list[str],
    cwd: str,
    timeout: int,
) -> ShellResult:
    """
    同步执行 subprocess（argv 模式），在线程池中调用。
    仅用于 Windows 平台，绕过事件循环的子进程支持限制。
    """
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=self._build_env(),
            capture_output=True,
            timeout=timeout,
            check=False,  # 不抛异常，通过返回码判断
        )
        
        # GBK/UTF-8 编码降级（复用现有逻辑）
        output = self._decode_windows_output(result.stdout)
        error = self._decode_windows_output(result.stderr)
        
        return ShellResult(
            success=(result.returncode == 0),
            output=output.strip(),
            error=error.strip() if error else None,
        )
    except subprocess.TimeoutExpired:
        return ShellResult(
            success=False,
            output=None,
            error=f"命令执行超时（{timeout}秒）",
        )
    except Exception as e:
        logger.error("同步 subprocess 执行异常: %s", e, exc_info=True)
        return ShellResult(success=False, output=None, error=str(e))

def _sync_subprocess_run_shell(
    self,
    shell_command: str,
    cwd: str,
    timeout: int,
) -> ShellResult:
    """
    同步执行 subprocess（shell 模式），在线程池中调用。
    仅用于 Windows 平台，绕过事件循环的子进程支持限制。
    """
    # shell_command 已经是 cmd.exe /c "{原始命令}" 格式
    try:
        result = subprocess.run(
            shell_command,
            cwd=cwd,
            env=self._build_env(),
            capture_output=True,
            timeout=timeout,
            shell=True,  # shell 模式
            check=False,
        )
        
        output = self._decode_windows_output(result.stdout)
        error = self._decode_windows_output(result.stderr)
        
        return ShellResult(
            success=(result.returncode == 0),
            output=output.strip(),
            error=error.strip() if error,
        )
    except subprocess.TimeoutExpired:
        return ShellResult(
            success=False,
            output=None,
            error=f"Shell 命令执行超时（{timeout}秒）",
        )
    except Exception as e:
        logger.error("同步 shell subprocess 执行异常: %s", e, exc_info=True)
        return ShellResult(success=False, output=None, error=str(e))

def _decode_windows_output(self, data: bytes) -> str:
    """
    解码 Windows 子进程输出，GBK/UTF-8 降级处理。
    复用现有编码处理逻辑。
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("gbk")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")
```

### 错误处理

1. **超时**：`subprocess.run(timeout=...)` 抛 `TimeoutExpired` → 捕获后返回 `ShellResult(success=False, error="超时")`
2. **编码错误**：复用现有的 GBK/UTF-8 降级逻辑（`_decode_windows_output`）
3. **子进程异常**：捕获所有 `Exception`，记录日志，返回失败结果
4. **线程池异常**：`run_in_executor` 会传播 executor 内的异常，外层 `_execute_decision` 的 `except Exception` 会捕获

### 跨平台隔离约束

**硬性要求**（来自用户指令）：

1. **Windows 特殊逻辑必须放在 `if sys.platform == "win32"` 分支内**
2. **macOS/Linux 保留原有代码路径，零改动**

**实现保证**：

- `_execute_argv` 的 `if sys.platform == "win32":` 分支：线程池逻辑
- `_execute_argv` 的 `else:` 分支：原有的 `create_subprocess_exec`（不变）
- `_execute_shell` Windows 分支：线程池逻辑
- `_execute_shell` macOS/Linux 分支：原有的 `create_subprocess_shell`（不变）
- 新增的 `_sync_subprocess_run*` 方法仅在 Windows 分支调用，不影响其他平台

---

## 边界与降级

### 性能考虑

**线程池开销**：
- `run_in_executor(None, ...)` 使用 Python 默认的 `ThreadPoolExecutor`
- 每次调用会提交任务到线程池，有轻微的线程调度开销（通常 < 1ms）
- 相比异步 subprocess 的开销可以忽略（子进程启动本身是重操作）

**并发限制**：
- 默认线程池大小：`min(32, (os.cpu_count() or 1) + 4)`（Python 3.8+）
- Windows 上的 git 命令并发度受线程池大小限制
- 实际场景中，用户交互触发的 git 命令并发度远小于线程池容量

### 已知限制

1. **仅解决 Windows subprocess 执行问题**
   - 不改变 Windows 白名单策略（仍然只支持 4 个纯读 git 子命令 + `&&`/`||`）
   - macOS/Linux 的 sandbox 包装、路径校验等逻辑不受影响

2. **线程池 vs 异步性能差异**
   - Windows 上使用线程池会有轻微的上下文切换开销
   - 但比"完全无法执行"好得多，且用户无感知

3. **调试日志输出时序**
   - 线程池中的同步 subprocess 执行时，日志输出可能与主事件循环的日志交错
   - 不影响功能，但查日志时需要注意时间戳排序

### 异常场景

| 场景 | 处理方式 |
|------|---------|
| 线程池耗尽 | `run_in_executor` 阻塞等待空闲线程（符合 asyncio 语义） |
| subprocess 超时 | 捕获 `TimeoutExpired`，返回失败结果 |
| 编码错误（中文路径/输出） | GBK → UTF-8 降级（复用现有逻辑） |
| 未知 subprocess 异常 | 捕获所有 `Exception`，记录日志，返回失败 |

---

## 测试计划

### 单元测试（可选，视实现时间）

1. 模拟 Windows 环境，测试 `_sync_subprocess_run` 的编码处理
2. 测试超时场景（设置短超时，执行慢命令）

### 集成测试（必须）

**测试环境**：Windows 10/11 + Python 3.12 + Electron 31

**测试用例**：

| 编号 | 输入 | 预期结果 |
|------|------|---------|
| 1 | `git status` | ✓ 执行成功，返回仓库状态 |
| 2 | `git log --oneline -5` | ✓ 执行成功，返回最近 5 条 commit |
| 3 | `git status && git log --oneline -5` | ✓ 执行成功（白名单允许，shell 模式） |
| 4 | `git diff` | ✓ 执行成功 |
| 5 | `git show HEAD` | ✓ 执行成功 |
| 6 | `cd ... && git status` | ✗ 白名单拒绝（cd 不是 git 命令）|
| 7 | `git status \| grep modified` | ✗ 白名单拒绝（管道符不支持）|
| 8 | 中文路径仓库的 `git status` | ✓ 编码正确处理（GBK 降级） |

**启动方式验证**：

- 带 `--reload`：所有测试用例通过
- 不带 `--reload`：所有测试用例通过

### 回归测试

**macOS/Linux**：
- 确认现有的 shell 工具测试全部通过（无新增失败）
- 确认性能无明显下降（测量 `git status` 执行耗时）

---

## 实施步骤

1. **修改 `_execute_argv` 方法**
   - 添加 Windows 分支的线程池逻辑
   - 保持 macOS/Linux 分支不变

2. **修改 `_execute_shell` 方法**
   - 添加 Windows 分支的线程池逻辑
   - 保持 macOS/Linux 分支不变

3. **新增同步执行辅助函数**
   - `_sync_subprocess_run`（argv 模式）
   - `_sync_subprocess_run_shell`（shell 模式）
   - `_decode_windows_output`（编码处理）

4. **测试验证**
   - Windows 端到端测试（8 个用例）
   - 两种启动方式（带/不带 `--reload`）
   - macOS/Linux 回归测试

5. **清理临时调试日志**（可选）
   - 决定是否保留 `command_policy.py` 和 `shell_tool.py` 中添加的调试日志
   - 或者调整为 DEBUG 级别

6. **文档更新**
   - 在 Windows shell 兼容性设计文档中记录此修复
   - 更新实现计划的 Task 6 测试结果

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 线程池性能开销 | Windows 上 git 命令执行稍慢（< 1ms） | 可接受，用户无感知 |
| 线程池耗尽导致阻塞 | 高并发场景下等待空闲线程 | 默认线程池容量足够大（32+），实际并发度低 |
| 跨平台代码分支维护 | 增加维护成本 | 通过 `if sys.platform == "win32"` 严格隔离，清晰明确 |
| 回归 macOS/Linux | 误改非 Windows 分支 | 代码审查 + 回归测试确保零改动 |

---

## 总结

**核心决策**：Windows 上用线程池执行同步 `subprocess.run`，绕过事件循环的子进程支持限制。

**优势**：
1. 不依赖启动参数（`--reload` 可用）
2. 不与 uvicorn 抢事件循环策略
3. macOS/Linux 零改动（符合跨平台约束）
4. 实现简单，风险可控

**劣势**：
1. Windows 上有轻微性能开销（可接受）
2. 增加了平台分支代码（但逻辑清晰，隔离明确）

**结论**：这是在"保留 `--reload`"约束下，唯一稳定可行的方案。
