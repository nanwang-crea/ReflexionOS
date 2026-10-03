# 沙箱后端配置覆盖 — 实现计划（Plan）

> 日期：2026-10-03
> 对应 Spec：[2026-10-03-sandbox-provider-config-design.md](../specs/2026-10-03-sandbox-provider-config-design.md)
> 规模：2 个业务文件小改 + 1 个测试文件，预计半小时级。

---

## Step 1：配置模型加 sandbox 节

**改动文件**：`backend/app/config/settings.py`。

**做什么**：

1. 新增 `SandboxSettings(BaseModel)`：单字段 `provider: Literal["auto","windows","seatbelt","landlock","null"] = "auto"`，带中文注释（标明 `"null"` 为无隔离排障模式、不进入任何默认路径）。
2. `AppSettings` 增加 `sandbox: SandboxSettings = Field(default_factory=SandboxSettings)`。

**验证**：`python -c "from app.config.settings import AppSettings; print(AppSettings().sandbox.provider)"` 输出 `auto`；`AppSettings(**{"sandbox":{"provider":"bogus"}})` 抛 ValidationError。

---

## Step 2：工厂配置分支

**改动文件**：`backend/app/security/sandbox/factory.py`。

**做什么**：

1. 文件头注释更新（说明配置覆盖意图——CLAUDE.md 修改注释规范）。
2. 模块级加显式映射 `_NAMED_BACKENDS = {"windows": WindowsSandbox, "seatbelt": SeatbeltSandbox, "landlock": LandlockSandbox}`。
3. `create_sandbox(level)` 开头读 `config_manager.settings.sandbox.provider`：
   - `"auto"` → 落到现有探测循环（不变）；
   - `"null"` → `logger.info` 后直接 `NullSandbox()`；
   - 指定后端 → 实例化并探测，可用则返回；不可用 `logger.warning("配置指定的 %s 后端在当前主机不可用，降级为无沙箱")` 后返回 `NullSandbox()`。
4. 配置读取包 try/except：配置层异常时按 `auto` 处理（防御性，不因配置读取失败拖垮沙箱创建）。

**验证**：`python -m compileall app/security/sandbox/` + Step 3 测试。

---

## Step 3：测试

**改动文件**：新建 `backend/tests/test_security/test_sandbox_factory_config.py`。

**做什么**（monkeypatch `config_manager.settings` 或工厂内读取点，各后端 `is_available` 用 monkeypatch 控制）：

1. `auto` + 全后端不可用 → NullSandbox（现有行为不回归）；
2. `"null"` → NullSandbox（即使某后端可用也强制）；
3. 指定后端且可用（monkeypatch `is_available=True`）→ 返回该后端实例；
4. 指定后端不可用 → NullSandbox + `caplog` 断言 warning 文案；
5. 配置缺省 → 等价 auto。

**验证**：`pytest tests/test_security/test_sandbox_factory_config.py -v` 全绿。

---

## Step 4：收尾

1. 全量回归：`pytest tests/ --ignore=tests/test_browser`；
2. dsh 清单 🟡3 勾掉；devlog 记录；wiki 不摄入（改动太小，价值低）。

**验证**：全量绿 + 文档更新。

---

## 风险与对策

| 风险 | 对策 |
|---|---|
| 配置读取循环导入（config → sandbox → config） | 工厂内**函数内局部导入** config_manager（settings 模块不依赖 sandbox，单向依赖本就安全，局部导入再保险一层） |
| 测试污染全局 config 单例 | monkeypatch fixture 收尾自动还原；不持久化任何配置 |
| 指定后端类构造抛异常（非 is_available 路径） | 构造也包进 try，异常视同不可用走降级 |
