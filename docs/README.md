# ReflexionOS Documentation Guide

这个仓库里的文档有历史累积,当前请按下面的优先级阅读。

## 当前有效

1. `README.md`
   - 项目概览和当前启动方式。
   - 当前代码实际形态以这里和代码仓库为准。

2. `backend/README.md`
   - 后端依赖来源、桌面启动探测和手动调试说明。

3. `docs/superpowers/specs/2026-04-15-reflexion-os-design.md`
   - 当前长期设计参考文档。
   - 产品定位、整体架构、模块职责可以参考这份,但运行方式、依赖来源、当前协议面仍以 `README.md`、`backend/README.md` 和代码实现为准。

4. `docs/superpowers/specs/2026-04-19-memory-architecture-v1.md`
   - 当前记忆系统的正式架构方案。
   - 当讨论长期协作记忆、运行时读取模型、长期记忆边界、晋升原则与召回路径时，优先参考这份。

5. `docs/plans/2026-04-19-memory-phase-1.md`
   - 当前记忆系统第一阶段方案。
   - 当推进第一阶段记忆能力时，优先参考这份，而不是直接从大而全的记忆目标出发。

6. `docs/plans/2026-04-18-multi-provider-model-plan.md`
   - 当前关于多供应商实例、模型选择、默认值和会话记忆的实施计划。
   - 继续推进设置页和聊天模型选择能力时优先参考这份。

## 历史参考

这些文档保留是为了追溯上下文,默认不需要继续维护:

- `设计方案.md`
  - 早期草稿版设计,已被主设计文档替代。

- `docs/superpowers/specs/2026-04-15-architecture-completeness.md`
  - 一次性的架构完整性分析,不是当前事实来源。

- `docs/superpowers/specs/2026-04-16-frontend-ui-enhancement-design.md`
  - 已完成阶段的前端专题设计,仅供回看。

- `docs/superpowers/plans/README.md`
  - 旧进度看板,数字已经过时。

- `docs/superpowers/plans/2026-04-15-phase1-implementation.md`
  - 第一阶段实施计划归档。

- `docs/superpowers/plans/2026-04-15-phase1-progress.md`
  - 第一阶段进度快照归档。

- `docs/superpowers/plans/2026-04-16-frontend-ui-enhancement.md`
  - 前端 UI 完善实施计划归档。

- `docs/superpowers/status/implementation-status-2026-04-16.md`
  - 2026-04-16 状态快照,不等同于当前实现现状。

- `docs/superpowers/status/frontend-phase2-completion-2026-04-16.md`
  - 前端第二阶段完成报告归档。

## 维护规则

- 后续如果是整体产品定位或长线架构变更,优先更新 `docs/superpowers/specs/2026-04-15-reflexion-os-design.md`。
- 当前记忆系统总体方向，以 `docs/superpowers/specs/2026-04-19-memory-architecture-v1.md` 为准；第一阶段范围以 `docs/plans/2026-04-19-memory-phase-1.md` 为准。
- 当前 LLM 多供应商实例改造的阶段计划，以 `docs/plans/2026-04-18-multi-provider-model-plan.md` 为准。
- 如果只是运行方式、目录结构、开发命令变化,优先更新 `README.md` 和 `backend/README.md`。
- Python 依赖当前统一以 `backend/requirements.txt` 为准,不要再在 `backend/pyproject.toml` 里重复声明。
- 阶段性计划和状态报告可以保留,但应明确标注日期和阶段,不要再把它们当成主设计文档。
- 新增文档前,先判断能否直接补到现有主设计文档里,避免继续产生平行版本。
