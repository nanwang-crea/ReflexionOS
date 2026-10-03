# 沙箱后端配置覆盖 — 设计文档（Spec）

> 日期：2026-10-03
> 来源：`docs/dsh-reference-opportunities.md` 🟡3「沙箱工厂配置覆盖」
> 规模：小功能（单一配置项 + 工厂分支），一份简式 spec/plan 即可

---

## 一、背景

沙箱选择目前**硬编码**在 `factory.create_sandbox()`（`app/security/sandbox/factory.py:87`）：按平台依次探测 WindowsSandbox → SeatbeltSandbox → LandlockSandbox，取第一个 `is_available()` 为真的，全不可用则兜底 NullSandbox。

排查安全相关问题时缺少对照手段：怀疑某后端误拦/漏拦（如 Seatbelt 在 macOS 上误伤合法写入）时，无法在不改代码的前提下"强制换后端"或"强制 Null 沙箱做无隔离对照"。dsh 对照清单把这项列为 🟡3（低改动、排障收益）。

调研结论：

- 调用点仅一处：`agent_service.py:202` 的 `create_sandbox()`（无参，默认 DEV 级）；
- 配置走 `~/.reflexion/config.json`，`ConfigManager` + `AppSettings` 分节（execution/memory/skill/...），无 sandbox 节；
- 工厂是模块级函数，可直接读全局 `config_manager` 单例（与 `rapid_loop.py` 同款用法）。

## 二、目标

1. `AppSettings` 新增 `sandbox` 配置节，含一个字段：`provider`，取值 `auto`（默认，现有自动探测）/ `windows` / `seatbelt` / `landlock` / `null`。
2. `create_sandbox()` 读取该配置：`auto` 走现有逻辑不变；指定后端时实例化该后端——**不可用时不静默换其他后端**，降级 NullSandbox 并打 warning（用户已明确表达意图，静悄悄换后端反而误导排障）；`null` 直接返回 NullSandbox。
3. 非法取值由 pydantic 校验在配置加载期拒绝（`Literal` 枚举），不进运行时。

## 三、非目标

- ❌ 前端设置界面（只配置文件层，手改 config.json 即可——排障场景受众是开发者）
- ❌ 每个后端各自的策略参数配置（路径/网络等仍由 SandboxLevel 推导）
- ❌ 调用方签名变更（`create_sandbox()` 无参调用保持不变，配置在工厂内部读取）
- ❌ 按会话/按任务动态切换（进程级配置，重启生效即可）

## 四、用户故事 / 行为

**作为排障者**，macOS 上怀疑 Seatbelt 误拦了 agent 的合法写入：把 `~/.reflexion/config.json` 的 `sandbox.provider` 改为 `"null"`，重启后 agent 在无隔离环境重跑同一操作——若不再失败，问题定位在 Seatbelt 策略；改回 `"auto"` 恢复。

**作为跨平台开发者**，Linux 上想提前验证 Windows 沙箱逻辑：设 `"windows"`，工厂实例化 WindowsSandbox，`is_available()` 为 False → 降级 NullSandbox 并打 warning 告知"指定的 windows 后端不可用"——行为明确可预期。

## 五、方案

### 5.1 配置模型（app/config/settings.py）

```python
class SandboxSettings(BaseModel):
    """沙箱配置节：排障用的后端强制指定（默认 auto 自动探测）"""
    provider: Literal["auto", "windows", "seatbelt", "landlock", "null"] = "auto"
```

`AppSettings` 增加 `sandbox: SandboxSettings = Field(default_factory=SandboxSettings)`。

### 5.2 工厂分支（app/security/sandbox/factory.py）

`create_sandbox(level)` 开头读 `config_manager.settings.sandbox.provider`：

- `"auto"` → 现有探测逻辑，一字不改；
- `"null"` → 直接 `NullSandbox()`（info 日志：配置强制无沙箱）；
- 指定后端 → 实例化对应类，`is_available()` 为真则返回；为假则 **warning 日志**（"配置指定的 X 后端在当前主机不可用，降级为无沙箱"）并返回 `NullSandbox()`。

显式映射 `{"windows": WindowsSandbox, "seatbelt": SeatbeltSandbox, "landlock": LandlockSandbox}`，不用 getattr 动态查找（防配置注入类名）。

### 5.3 测试（tests/test_security/ 下新增或并入现有沙箱测试文件）

- `auto` + 全后端不可用时仍兜底 NullSandbox（现有行为不回归）；
- `provider="null"` 直接返回 NullSandbox（即使某后端可用）；
- 指定可用后端（用 monkeypatch 伪造 `is_available=True`）→ 返回该后端实例；
- 指定不可用后端 → 返回 NullSandbox + warning 日志（caplog 断言）；
- 配置缺省（config.json 无 sandbox 节）→ 等价 `auto`。

## 六、边界与降级

- **配置缺失/损坏**：ConfigManager 现有逻辑（回退默认值）天然覆盖，等价 `auto`；
- **指定后端不可用**：降级 NullSandbox + warning，不抛错（排障场景下"跑不起来"比"无沙箱"更糟）；
- **跨平台**：映射表里的后端类在非对应平台实例化即 `is_available()=False`，走降级路径，无平台分支崩溃风险（工厂现有设计已保证）；
- **安全语义**：`"null"` 是无隔离模式，仅排障用——配置项注释中写明，不进入任何默认路径。

## 七、自检

- 无 TBD：配置字段、映射表、降级路径、日志行为均已具体化；
- 调用方零改动已验证（`agent_service.py:202` 无参调用，配置工厂内读）；
- 与既有规范一致：行为变更加中文注释说明意图（CLAUDE.md 编码规范）。
