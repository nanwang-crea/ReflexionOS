# 图片输入一期实施方案

**日期**: 2026-06-16  
**状态**: 待实施  
**对应设计**: [2026-06-16-image-input-phase1-design.md](C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/docs/superpowers/specs/2026-06-16-image-input-phase1-design.md)

## 1. 实施目标

基于当前代码，把“图片作为输入上下文”的雏形能力补成可稳定交付的一期能力。

本期交付边界：

- 支持粘贴、拖拽、文件选择添加图片
- 单次消息最多 4 张图片
- 发送前可预览和删除
- 发送时先上传，再通过 `attachment_ids` 引用
- 后端将图片注入模型上下文
- 已发送消息稳定回显图片
- 模型不支持 vision 时有明确反馈
- 编辑重跑默认保留原图片附件

## 2. 总体实施顺序

按依赖关系，建议顺序固定为：

1. 先修图片展示和 URL 生成
2. 再加“最多 4 张”的前后端约束
3. 再统一 vision 能力来源
4. 再补附件生命周期和清理
5. 再补编辑重跑附件继承
6. 最后补测试和回归

原因：

- 如果图片展示不稳定，后面所有调试都容易误判
- 如果没有数量约束，多图行为很难收敛
- 如果 `supports_vision` 不统一，无法定义“图片到底有没有参与推理”
- 如果生命周期和重跑不补，功能虽能演示但不具备稳定性

## 3. Phase 拆分

### Phase 1：图片展示稳定化

**目标**

- 已发送消息里的图片展示路径稳定
- 兼容开发模式、Electron 打包模式、`file://` 场景
- 前端不再依赖 `filePath` 推导展示 URL

**改动点**

前端：

- `frontend/src/components/workspace/UserMessageItem.tsx`
  - 改为直接使用 `sessionId + attachment.id`
  - 统一走 `getApiBaseUrl()`
- `frontend/src/components/workspace/WorkspaceTranscript.tsx`
  - 向 `UserMessageItem` 传入 `message.sessionId`

后端：

- `backend/app/services/attachment_service.py`
  - 增加稳定的附件展示 URL 生成逻辑
- `backend/app/services/conversation_service.py`
  - 将 `url` 注入消息附件 DTO

**验收标准**

- 同一条用户消息的图片在页面重渲染后不丢失
- Electron 打包版里图片地址不再依赖相对 `/api/...`
- 前端不再从 `filePath` 反推 session

### Phase 2：单次 4 张图片约束

**目标**

- 产品规则固定：单次发送最多 4 张
- 前端拦截，后端兜底

**改动点**

前端：

- `frontend/src/features/conversation/hooks/useImageUpload.ts`
  - `addFiles()` 中检查当前数量 + 新增数量
  - 超过 4 张时报错
- `frontend/src/pages/AgentWorkspace.tsx`
  - 捕获超限错误并 toast 提示

后端：

- `backend/app/api/routes/websocket.py`
  - 校验 `attachment_ids` 数量
- `backend/app/services/conversation_service.py`
  - 在 `start_turn()` 或进入前做兜底校验

**错误提示建议**

前端提示：

- `单次最多发送 4 张图片`

后端提示：

- `attachment_ids exceeds limit: max 4`

**验收标准**

- 第 5 张图片无法加入待发送队列
- 即使前端绕过限制，后端也会拒绝创建 turn

### Phase 3：统一 vision 能力来源

**目标**

- 前端展示与后端实际行为一致
- 不再用静态名单作为主判断依据

**改动点**

前端：

- `frontend/src/constants/visionModels.ts`
  - 不再作为主能力判断
- `frontend/src/pages/AgentWorkspace.tsx`
  - 图片添加时读取后端下发的 `supports_vision`
- `frontend/src/pages/settings/ProviderPanel.tsx`
  - 展示真实 `supports_vision`

后端：

- `backend/app/models/llm_config.py`
- `backend/app/services/llm_provider_service.py`
- `backend/app/services/agent_service.py`

**行为规则**

- `supports_vision === true`：正常注入图片
- `supports_vision === false`：允许上传，但发送前明确提示“当前模型不支持图片分析”
- `supports_vision === null`：可先按兼容模式放行，同时提示能力未确认

**验收标准**

- UI 中的 vision 状态与运行时行为一致
- 不再出现“前端可传图但后端跳过图片”的不透明状态

### Phase 4：附件生命周期治理

**目标**

- 减少孤儿附件
- 发送失败时状态明确

**最低实现**

先不引入新表，做轻量治理：

- 上传后文件先落盘
- 只有消息成功创建后，这批附件才视为已绑定
- 增加清理逻辑，定期删除长时间未被消息引用的附件文件

**改动点**

- `backend/app/api/routes/upload.py`
- `backend/app/services/attachment_service.py`
- `backend/app/services/agent_service.py`
- `backend/app/api/routes/sessions.py`

**验收标准**

- 上传成功但发送失败时，不会长期残留大量孤儿文件
- 删除 session 时，附件目录仍能正确清理

### Phase 5：编辑重跑附件继承

**目标**

- 用户编辑文本并重跑时，默认保留原图

**改动点**

- `backend/app/api/routes/websocket.py`
  - `edit_and_rerun` 协议扩展或继承逻辑接入点
- `backend/app/services/conversation_service.py`
  - 重跑时继承原 user message 的附件
- `backend/app/services/agent_service.py`
  - 调整运行参数传递

**推荐策略**

- 默认继承原附件
- 不在一期做“重跑时手动取消某张图”的交互

**验收标准**

- 带图用户消息触发编辑重跑后，模型仍收到图片上下文

### Phase 6：测试补齐

**目标**

- 给图片输入链路建立稳定回归保护

**前端测试**

- `ChatInput` 粘贴图片
- `ChatInput` 拖拽图片
- `useImageUpload` 数量限制
- `AgentWorkspace` 发送时传出 `attachmentIds`
- `UserMessageItem` 正确渲染图片 URL

**后端测试**

- 图片上传成功
- 非图片上传失败
- 超过 4 张时拒绝
- `ContextAssembler` 正确生成图片 `content parts`
- `supports_vision == false` 时不注入图片
- `edit_and_rerun` 保留附件

**端到端测试**

- 发送 1 张图 + 文本
- 发送 4 张图 + 文本
- 发送第 5 张时失败
- 编辑重跑后图片仍存在

## 4. 文件级实施清单

### 前端

必须修改：

- `frontend/src/components/chat/ChatInput.tsx`
- `frontend/src/components/chat/ImagePreview.tsx`
- `frontend/src/features/conversation/hooks/useImageUpload.ts`
- `frontend/src/pages/AgentWorkspace.tsx`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/hooks/useConversationRuntime.ts`
- `frontend/src/components/workspace/UserMessageItem.tsx`
- `frontend/src/components/workspace/WorkspaceTranscript.tsx`
- `frontend/src/pages/settings/ProviderPanel.tsx`
- `frontend/src/types/llm.ts`

可能删除或降级：

- `frontend/src/constants/visionModels.ts`

### 后端

必须修改：

- `backend/app/api/routes/upload.py`
- `backend/app/api/routes/websocket.py`
- `backend/app/services/attachment_service.py`
- `backend/app/services/conversation_service.py`
- `backend/app/services/agent_service.py`
- `backend/app/services/llm_provider_service.py`
- `backend/app/models/llm_config.py`
- `backend/app/memory/context_assembly.py`

必须补测试：

- `backend/tests/test_api/test_upload.py`
- `backend/tests/test_services/test_attachment_service.py`
- 增加 `context_assembly` / `edit_and_rerun` 相关测试

## 5. 实施时的关键规则

1. 不把图片内容直接塞进 websocket 消息。
2. 不在前端推断模型是否支持 vision，以后端配置为准。
3. 不依赖 `filePath` 生成用户消息图片展示 URL。
4. 不在一期扩展通用附件类型。
5. 前端限制和后端限制必须同时存在。

## 6. 风险控制

### 风险 1：图片显示修好了，但模型其实没吃到图

对策：

- Phase 3 前后端统一 `supports_vision`
- 加入 `ContextAssembler` 级测试

### 风险 2：多图导致请求体过大

对策：

- 一期限制 4 张
- 保留现有压缩逻辑
- 后续评估 data URL 替换方案

### 风险 3：发送失败遗留附件

对策：

- Phase 4 补生命周期治理
- 后端定时清理未引用文件

## 7. 推荐实施顺序

如果按最小可交付路径推进，建议按下面顺序做：

1. 修 `UserMessageItem` 图片 URL 生成
2. 后端 attachment DTO 增加 `url`
3. 前端 `useImageUpload` 限制最多 4 张
4. 后端 `attachment_ids` 数量兜底
5. 统一 `supports_vision`
6. 清理孤儿附件
7. 修 `edit_and_rerun` 附件继承
8. 补测试

## 8. 完成定义

满足以下条件，视为图片输入一期完成：

1. 用户可以稳定发送 1 到 4 张图片
2. 图片能稳定回显
3. 模型支持 vision 时，图片进入推理上下文
4. 模型不支持 vision 时，系统给出明确反馈
5. 编辑重跑不丢图
6. 没有明显孤儿附件堆积
7. 前后端与端到端测试通过
