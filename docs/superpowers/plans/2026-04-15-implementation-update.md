# 实施计划更新说明

**更新日期**: 2026-04-15  
**更新原因**: 补充MVP必须的核心组件

---

## 📋 新增内容

### 新增模块: 模块三-B - MVP 核心补充组件

根据架构完整性分析,在实施计划中补充了4个MVP必须的组件:

---

## 🔴 任务 3.5: 实现 Patch 工具

**优先级:** P0 - MVP 核心

**新增文件:**
- `backend/app/tools/patch_tool.py` - Patch 工具
- `backend/app/tools/diff_parser.py` - Unified Diff 解析器
- `backend/tests/test_tools/test_patch_tool.py` - 测试

**功能:**
- Unified Diff 格式解析
- Hunk 应用机制
- 冲突检测
- 安全的文件修改

**工时:** 3小时

---

## 🔴 任务 3.6: 实现持久化存储层

**优先级:** P0 - 基础设施

**技术选型:** SQLite + SQLAlchemy

**新增文件:**
- `backend/app/storage/database.py` - 数据库连接
- `backend/app/storage/models.py` - ORM 模型
- `backend/app/storage/repositories/project_repo.py` - 项目仓储
- `backend/app/storage/repositories/execution_repo.py` - 执行记录仓储
- `backend/tests/test_storage/` - 测试

**数据模型:**
- ProjectModel - 项目数据
- ExecutionModel - 执行记录
- ConversationModel - 对话记录
- LLMUsageModel - LLM使用统计

**工时:** 4小时

---

## 🔴 任务 3.7: 完善配置管理系统

**优先级:** P0 - 用户体验

**新增文件:**
- `backend/app/config/settings.py` - 配置管理器
- `backend/app/config/llm_config.py` - LLM 配置管理
- `backend/tests/test_config/` - 测试

**配置类型:**
- LLMSettings - LLM 配置
- ExecutionSettings - 执行配置
- UISettings - 界面配置

**功能:**
- 动态配置修改
- 配置持久化
- 配置验证
- 默认值管理

**工时:** 2小时

---

## 🔴 任务 3.8: 实现 WebSocket 后端

**优先级:** P0 - 实时性要求

**新增/修改文件:**
- `backend/app/api/websocket.py` - WebSocket 管理
- `backend/app/main.py` - 路由注册

**功能:**
- WebSocket 连接管理
- 执行步骤实时推送
- 心跳机制
- 广播和单播

**事件类型:**
- execution:start - 执行开始
- execution:step - 步骤更新
- execution:complete - 执行完成
- execution:error - 执行错误

**工时:** 3小时

---

## 📊 更新后的工作量估算

### MVP 必须完成的工作:

| 模块 | 任务数 | 总工时 | 状态 |
|------|--------|--------|------|
| 模块一: 后端基础设施 | 3 | 9h | ✅ 已完成 |
| 模块二: LLM适配层 | 2 | 5h | ✅ 已完成 |
| 模块三-A: 工具层基础 | 3 | 8h | ✅ 已完成 |
| **模块三-B: MVP补充** | **4** | **12h** | ⏸️ 待实施 |
| 模块四: 执行引擎 | 4 | 8h | ⏸️ 待实施 |
| 模块五: API路由 | 2 | 6h | ⏸️ 待实施 |
| 模块六: 前端框架 | 3 | 8h | ⏸️ 待实施 |

**MVP 总工时:** 56小时 (约7-8天)

---

## 🎯 实施顺序建议

### Week 1 (已完成)
- ✅ 模块一: 后端基础设施
- ✅ 模块二: LLM适配层
- ✅ 模块三-A: 工具层基础

### Week 2 (当前)
- ⏸️ **模块三-B: MVP补充组件** (12h)
  - Day 1: Patch工具 (3h)
  - Day 2: 持久化存储 (4h)
  - Day 3: 配置管理 + WebSocket (5h)

### Week 3
- ⏸️ 模块四: 执行引擎
- ⏸️ 模块五: API路由

### Week 4
- ⏸️ 模块六: 前端框架
- ⏸️ 集成测试

---

## 📦 新增依赖

在 `requirements.txt` 中添加:

```txt
sqlalchemy==2.0.25
alembic==1.13.1
```

---

## ✅ 验证清单

完成模块三-B后,需要验证:

- [ ] Patch 工具可以正确应用 Diff
- [ ] SQLite 数据库正常创建
- [ ] 项目数据可以持久化和读取
- [ ] 执行记录可以保存和查询
- [ ] 配置可以动态修改和保存
- [ ] WebSocket 可以连接和推送消息
- [ ] 所有新增测试通过

---

## 🔄 与设计文档的对应

| 实施任务 | 设计文档章节 | 优先级 |
|----------|--------------|--------|
| 任务 3.5 | 3.3.3 Patch 工具 | P0 |
| 任务 3.6 | 3.3.1 持久化存储层 | P0 |
| 任务 3.7 | 3.3.2 配置管理系统 | P0 |
| 任务 3.8 | 3.3.4 WebSocket 实时通信 | P0 |

---

## 📝 备注

1. **数据库位置**: 默认使用 `~/.reflexion/reflexion.db`
2. **配置文件位置**: 默认使用 `~/.reflexion/config.json`
3. **WebSocket 端点**: `ws://localhost:8000/ws/execution/{execution_id}`
4. **Patch 工具**: 支持 Unified Diff 格式,后续可增强冲突处理

---

**下次更新:** 完成模块三-B后
