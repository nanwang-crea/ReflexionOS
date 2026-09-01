# Startup Validation Report

生成时间：2026-08-11 15:23:48 CST

## 结论

本机 macOS 已完成可自动化的真实启动验证：

- FastAPI 后端可真实启动，并能响应 `/health`、`/`、`/api/projects/`。
- 前端生产构建可完成。
- Vite 开发态 renderer 可启动并返回首页 `200 OK`。
- Electron 桌面壳可启动，并能自动拉起默认后端 `127.0.0.1:8000/health`。

Windows 真机仍需补充人工启动验证。当前 macOS 环境无法真实验证 Windows GUI、Windows pywin32 sandbox、Windows 打包产物运行。

## 本机启动验证记录

| 项目 | 命令/动作 | 结果 | 说明 |
| --- | --- | --- | --- |
| 后端真实启动 | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8765` | 通过 | 启动完成，插件和技能扫描正常。 |
| 后端健康检查 | `curl http://127.0.0.1:8765/health` | 通过 | 返回 `{"status":"healthy"}`。 |
| 后端根路由 | `curl http://127.0.0.1:8765/` | 通过 | 返回应用名、版本、运行状态和功能开关。 |
| 后端项目 API | `curl http://127.0.0.1:8765/api/projects/` | 通过 | 返回项目列表 JSON。 |
| 前端生产构建 | `pnpm build` | 通过 | `tsc && vite build` 成功；仅有 Vite chunk size warning。 |
| Vite dev 启动 | `pnpm dev:web ...` | 通过 | Vite dev server 启动，实际端口 `5174`。 |
| Vite 首页探活 | `curl -I http://127.0.0.1:5174/` | 通过 | 返回 `HTTP/1.1 200 OK`。 |
| Electron 桌面启动 | `pnpm start` | 通过 | Electron 进程启动，无启动错误输出。 |
| Electron 自动后端 | `curl http://127.0.0.1:8000/health` | 通过 | Electron 启动后默认后端返回 `{"status":"healthy"}`。 |
| 进程清理 | 停止 Electron / 后端 | 通过 | 已释放 `8000` 端口，无监听残留。 |

## 自动化已证明的修复

以下修复已经被单元/集成测试和本机启动验证共同覆盖：

1. subagent 工具集隔离：排除 `delegate`、`plan`、`browser`，并克隆状态型工具。
2. subagent shell session 隔离：child shell 绑定 child session id。
3. subagent child loop 生命周期：`sub-run-*` loop 注册和注销可追踪。
4. subagent 审批执行：审批通过后使用 child loop 的真实 tool registry。
5. subagent 审批归属校验：错误 session/run 路由会被拒绝。
6. subagent `trust_and_allow`：trust rule 写入父 session。
7. cancel/reset/delete 清理：pending approval 和 trust rules 按 session 清理。
8. 前端 subagent events：按 `sessionId + delegate_call_id` 隔离，避免串台。
9. delegate UI 关联键：transcript detail 保留 `tool_call_id` 和 `session_id`。
10. SubAgentDetailPanel：`run:waiting_for_approval` / `run:resuming` 不打断工具批次。
11. approval payload：统一解析 shell/sandbox/trust/parent session 字段。
12. 后端和前端基础启动链路：本机 macOS 下后端、Vite、Electron 自动后端均可启动。

## Mac 真机验收问题清单

启动命令：

```bash
cd frontend
pnpm dev
```

请在 macOS 上逐项确认：

| 编号 | 验收问题 | 期望结果 |
| --- | --- | --- |
| M1 | Electron 窗口是否能正常打开？ | 能看到 ReflexionOS 主界面。 |
| M2 | 后端状态是否正常？ | 应无 backend failed 提示，`http://127.0.0.1:8000/health` 返回 healthy。 |
| M3 | 新建/选择项目后能否进入会话？ | 项目列表和会话列表正常显示。 |
| M4 | 发送一条普通消息是否有流式响应？ | assistant 消息、工具 trace、状态流转正常。 |
| M5 | 触发一个 delegate 子任务是否显示“正在执行子任务”？ | delegate 卡片出现，点击可进入子 agent 详情。 |
| M6 | 子 agent 调用工具时详情页是否实时更新？ | 工具 start/result、模型内容、步骤数正确更新。 |
| M7 | 子 agent 触发 shell 审批时，审批卡片是否显示在 delegate 卡片内？ | 审批按钮、命令摘要、风险信息可见。 |
| M8 | 点击“允许一次”后子 agent 是否继续执行？ | 审批后工具结果配回原工具，详情页不再卡等待。 |
| M9 | 点击“信任并允许”后，同 session 同类命令是否减少重复审批？ | trust rule 生效。 |
| M10 | 同时打开两个会话并触发 delegate，事件是否串台？ | 每个会话只显示自己的子 agent 步骤。 |
| M11 | reset 会话后子 agent 历史步骤是否清空？ | 当前会话 delegate 历史不残留。 |
| M12 | 删除会话后是否无资源残留/错误弹窗？ | 会话删除成功，日志无关键清理失败。 |

## Windows 真机验收问题清单

启动命令：

```powershell
cd frontend
pnpm dev
```

如果使用 Git Bash / WSL 辅助启动，也可参考：

```bash
./start-dev.sh
```

请在 Windows 上逐项确认：

| 编号 | 验收问题 | 期望结果 |
| --- | --- | --- |
| W1 | Electron 窗口是否能正常打开？ | 能看到 ReflexionOS 主界面，无 Electron spawn/ENOENT 类错误。 |
| W2 | Electron 是否能找到 Python 后端环境？ | 后端自动启动；必要时设置 `REFLEXION_PYTHON_PATH` 后可启动。 |
| W3 | `http://127.0.0.1:8000/health` 是否 healthy？ | 返回 `{"status":"healthy"}`。 |
| W4 | 普通 shell 工具是否可执行低风险命令？ | 例如 `dir` / `git status` 能返回结果。 |
| W5 | Windows 下 shell 审批是否正常弹出？ | 高风险或需网络命令应进入审批，不应直接失败。 |
| W6 | 子 agent shell 审批是否能通过父会话 UI 处理？ | 审批按钮可用，允许后子 agent 继续。 |
| W7 | `trust_and_allow` 是否在 Windows shell 命令上生效？ | 同 session 同类命令不重复审批或按 trust 规则减少审批。 |
| W8 | Windows sandbox/network/path elevation 审批是否正常？ | 需要网络/路径提升时出现正确审批卡片。 |
| W9 | 并发 delegate 是否稳定？ | 多个 delegate 同时运行时不互相覆盖事件。 |
| W10 | reset/cancel/delete 是否清理 pending approval？ | 已取消或删除会话后旧审批按钮不可再误提交。 |
| W11 | `pnpm dist:win` 是否能完成打包？ | Windows 包构建成功，启动产物可打开。 |
| W12 | 打包后的 Windows 应用是否能启动内置后端？ | 用户无需手动起 Python 后端即可进入应用。 |

## 需要特别观察的问题

### 1. Windows sandbox 真机覆盖不足

当前 macOS 下 Windows API 测试按平台跳过，这是正确的；但不能替代 Windows 真机验证。

需要 Windows 上重点验证：

- `CreateRestrictedToken`
- ACL 写入边界
- `CreateProcessAsUser`
- sandbox network/path elevation 审批
- `uvicorn --reload` 与 Windows event loop 兼容性

### 2. Electron GUI 交互无法完全自动证明

本机已证明 Electron 进程可启动并能自动拉起后端；但窗口内真实点击、审批按钮、详情面板滚动等仍建议人工点验。

### 3. Vite chunk size warning

`pnpm build` 通过，但 Vite 提示主 JS chunk 大于 500 kB。这不是本次修复引入的功能错误，也不会阻止启动；后续可独立做 code splitting 优化。

## 建议真实启动验收流程

### Mac

1. `cd frontend && pnpm dev`
2. 确认窗口打开和后端 healthy。
3. 创建或选择项目。
4. 发起一个普通任务。
5. 发起一个包含 delegate 的任务，例如：“请委托子 agent 检查当前项目 README 和 package 脚本，并总结启动方式。”
6. 发起一个会触发 shell 审批的子任务，例如：“委托子 agent 执行 git status 并解释结果。”
7. 测试允许一次、信任并允许、拒绝三条审批路径。
8. 测试 reset 和 delete 后没有旧审批残留。

### Windows

1. 安装 backend requirements 和 frontend dependencies。
2. `cd frontend && pnpm dev`
3. 如无法找到 Python，设置 `REFLEXION_PYTHON_PATH` 后重试。
4. 重复 Mac 的 delegate/subagent/审批流程。
5. 额外测试 Windows shell 命令：`dir`、`git status`、需要审批的写操作、需要网络的命令。
6. 执行 `pnpm dist:win`，验证打包产物可启动并自动拉起后端。

## 当前状态

- 本机 macOS 自动化启动验证：已完成。
- Windows 真机启动验证：待在 Windows 机器执行。
- 源码、测试、文档改动：未提交，未推送。
