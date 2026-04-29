# ReflexionOS Documentation Guide

这个仓库里的文档有历史累积,当前请按下面的优先级阅读。

## 当前有效

1. `README.md`
   - 项目概览和当前启动方式。
   - 当前代码实际形态以这里和代码仓库为准。

2. `backend/README.md`
   - 后端依赖来源、桌面启动探测和手动调试说明。
   - 同时维护 Phase 1 记忆管线的“实现事实快照”（`messages / conversation_events / curated memory / recall / continuation artifacts`）。

3. `docs/superpowers/plans/2026-04-15-reflexion-os-design-整体架构.md`
   - 当前长期设计参考文档。
   - 产品定位、整体架构、模块职责可以参考这份,但运行方式、依赖来源、当前协议面仍以 `README.md`、`backend/README.md` 和代码实现为准。

4. `docs/superpowers/specs/2026-04-28-agent-memory-overall-design.md`
   - 当前记忆系统的正式整体设计方案。
   - 当讨论长期记忆、session 续航、transcript recall、provider 扩展边界时，优先参考这份。

5. `docs/superpowers/specs/2026-04-24-conversation-phase1-direct-cutover-design.md`
   - 当前会话底座设计方案。
   - 当讨论 `Session / Turn / Run / Message / Event` 会话事实层时，优先参考这份。

## Phase 1 记忆管线（快速定位）

这部分是为了让读文档的人快速落到“当前代码已经实现的事实面”。更完整、更精确的落地细节以 `backend/README.md` 为准；设计与边界以规格文档为准。

- 读取对话内容：以 `messages` 为主（HTTP conversation snapshot 与 runtime seed 都基于 messages）。
- 增量同步与回放：`conversation_events` 保持 append-only，用于 WebSocket 的 `after_seq` 同步，不作为主阅读面。
- Curated memory：项目级条目化存储，渲染为 `USER.md` / `MEMORY.md`，目录在 `{memory.base_dir}/projects/<project_id>/`。
- Recall：读取派生的 `message_search_documents`（由消息投影自动维护，非向量检索）。
- Continuation artifacts：run 结束后由压缩/收敛步骤生成的 system notice（`kind=continuation_artifact`），作为 supplemental context 注入下一轮执行，并默认从 recall/记忆提升中排除。

## 历史参考

这些文档保留是为了追溯上下文,默认不需要继续维护:

- `docs/superpowers/plans/2026-04-28-agent-memory-phase1-implementation.md`
  - Agent memory Phase 1 的实施计划归档,适合回看任务拆分和实现顺序,不等同于当前代码事实。

旧版本 README 里曾出现过的一些一次性分析/状态文档已经不在当前仓库中,因此这里不再继续链接它们,以免把不存在的路径误当成可读来源。

## 维护规则

- 后续如果是整体产品定位或长线架构变更,优先更新 `docs/superpowers/plans/2026-04-15-reflexion-os-design-整体架构.md`。
- 当前记忆系统总体方向，以 `docs/superpowers/specs/2026-04-28-agent-memory-overall-design.md` 为准；在新的 Phase 1 实施计划落出前，以该文档中的“第一阶段落地范围”为准。
- 如果只是运行方式、目录结构、开发命令变化,优先更新 `README.md` 和 `backend/README.md`。
- Python 依赖当前统一以 `backend/requirements.txt` 为准,不要再在 `backend/pyproject.toml` 里重复声明。
- 阶段性计划和状态报告可以保留,但应明确标注日期和阶段,不要再把它们当成主设计文档。
- 新增文档前,先判断能否直接补到现有主设计文档里,避免继续产生平行版本。
