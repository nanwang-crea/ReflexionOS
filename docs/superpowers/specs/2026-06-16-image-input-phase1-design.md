# 图片输入一期开发方案

**日期**: 2026-06-16  
**状态**: 待开发  
**范围**: 仅支持图片作为用户输入上下文，不扩展到 PDF / 音频 / 视频 / 通用附件

## 1. 背景

当前代码已经具备一条可工作的图片输入雏形链路：

- 前端输入：`ChatInput` 支持粘贴、拖拽、文件选择图片
- 前端缓存：`useImageUpload` 管理待发送图片、压缩、上传
- 发送流程：`AgentWorkspace` 在发送消息时先上传图片，再把 `attachment_ids` 传给 `startTurn`
- 后端上传：`POST /api/sessions/{session_id}/upload`
- 消息落库：`ConversationService.start_turn()` 将附件元数据写入消息
- 上下文组装：`ContextAssembler` 将附件转成 LLM `content parts`
- 模型适配：`OpenAIAdapter` 将图片 part 转成 `image_url`

这说明“图片输入”已经不是从零开始，而是需要从“可运行雏形”补到“稳定一期能力”。

## 2. 目标

一期目标只做一件事：

**让用户可以稳定地把图片和文本一起发送给 Agent，并确保图片真正参与模型推理。**

具体要求：

1. 用户可通过粘贴、拖拽、文件选择添加图片
2. 发送前可预览并删除图片
3. 图片与文本一起发送
4. 后端能将图片稳定注入模型上下文
5. 已发送的用户消息可以稳定回显图片
6. 失败路径明确，可定位问题

## 3. 非目标

本期明确不做：

- PDF / Word / 音频 / 视频输入
- 通用附件系统抽象
- 会话级附件复用面板
- 大图原图管理策略
- 图片标注、框选、OCR 专项能力
- 多模态编辑器或图库管理

## 4. 当前实现现状

### 4.1 已有能力

- `frontend/src/components/chat/ChatInput.tsx`
  - 已支持图片粘贴、拖拽、文件选择
- `frontend/src/features/conversation/hooks/useImageUpload.ts`
  - 已支持本地待上传图片状态、压缩、发送时上传
- `frontend/src/pages/AgentWorkspace.tsx`
  - 已将 `uploadAll()` 接入发送流程
- `backend/app/api/routes/upload.py`
  - 已提供图片上传和图片读取接口
- `backend/app/services/attachment_service.py`
  - 已提供附件元数据构建和图片转 `content parts`
- `backend/app/memory/context_assembly.py`
  - 已将消息附件注入模型消息内容

### 4.2 当前主要缺口

1. 图片展示 URL 生成方式不稳，前端不应依赖 `filePath` 猜路径
2. 前端和后端对 vision 能力的判断来源不一致
3. 编辑重跑链路没有稳定继承附件
4. 上传成功但消息发送失败时会残留孤儿文件
5. 缺少图片输入端到端回归测试

## 5. 一期方案

一期分成 5 个子目标，按顺序开发。

### 5.1 子目标 A：稳定前端图片输入体验

保留当前交互模型，不重做 UI。

继续使用：

- 粘贴图片
- 拖拽图片
- 文件按钮上传图片
- 发送前预览
- 删除待发送图片

必要补充：

- 明确单张大小限制提示
- 明确仅支持图片格式
- 发送中禁用重复点击
- 上传失败时给出准确提示

涉及文件：

- `frontend/src/components/chat/ChatInput.tsx`
- `frontend/src/components/chat/ImagePreview.tsx`
- `frontend/src/features/conversation/hooks/useImageUpload.ts`

### 5.2 子目标 B：统一消息发送协议

继续沿用当前方向：

- 前端发送前先上传图片
- websocket / runtime 只传 `attachment_ids`
- 后端根据 `attachment_ids` 恢复图片元数据

不改成：

- 前端直接把 base64 图片发到 websocket
- 前端直接构造多模态 message parts

原因：

- 前端只负责上传和引用，不负责模型输入协议
- 后端可以统一管理 provider 差异
- 后续更容易替换图片存储方案

涉及文件：

- `frontend/src/pages/AgentWorkspace.tsx`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/hooks/useConversationRuntime.ts`
- `backend/app/api/routes/websocket.py`
- `backend/app/services/conversation_service.py`

### 5.3 子目标 C：统一 vision 能力来源

当前前端使用静态名单 `visionModels.ts` 判断模型是否支持图片，后端则已有动态 `supports_vision` 能力链路。

一期方案：

- 以前端消费后端返回的 `supports_vision` 为准
- 前端移除或弱化静态白名单判断
- 后端在模型配置、连接测试、运行时 resolved config 中统一下发 `supports_vision`

预期结果：

- 用户在 UI 上看到的“支持图片/不支持图片”与后端实际行为一致
- 避免“前端看起来能发图，但后端实际没喂给模型”的错位

涉及文件：

- `frontend/src/pages/settings/ProviderPanel.tsx`
- `frontend/src/types/llm.ts`
- `frontend/src/constants/visionModels.ts`
- `backend/app/models/llm_config.py`
- `backend/app/services/llm_provider_service.py`
- `backend/app/services/agent_service.py`

### 5.4 子目标 D：补齐附件生命周期

一期不做复杂的附件中心，但要把最基本的生命周期补全。

要求：

1. 上传后未发送成功的附件不能长期残留
2. 已绑定消息的附件可以被正常回显
3. 删除 session 时继续清理附件目录

建议实现：

- 上传文件时默认视为 `pending`
- `start_turn` 成功创建消息后视为 `attached`
- 后台定期清理超时 `pending` 文件

如果本期不想引入数据库表扩展，至少先做简化版本：

- 基于目录时间戳清理长时间未被消息引用的文件

涉及文件：

- `backend/app/api/routes/upload.py`
- `backend/app/services/attachment_service.py`
- `backend/app/services/agent_service.py`
- `backend/app/api/routes/sessions.py`

### 5.5 子目标 E：补齐编辑重跑一致性

当前多模态最危险的问题不是上传，而是“用户第一次发图后，编辑重跑可能丢图”。

一期必须明确规则：

- 用户编辑文本并重跑时，默认保留原图片附件
- 如果后续需要“重跑时移除图片”，应由显式交互控制，而不是隐式丢失

建议实现：

- 在 `edit_and_rerun` 链路中继承原 user message 的 `attachments`
- 或显式继承原始 `attachment_ids`

涉及文件：

- `backend/app/api/routes/websocket.py`
- `backend/app/services/conversation_service.py`
- `backend/app/services/agent_service.py`

## 6. 数据与接口约定

### 6.1 前端待发送附件状态

继续沿用现有 `PendingAttachment`，但建议补充状态语义：

```ts
type PendingAttachmentStatus = 'pending' | 'uploading' | 'uploaded' | 'error'
```

建议结构：

```ts
interface PendingAttachment {
  id: string
  file: File
  previewUrl: string
  status?: PendingAttachmentStatus
  error?: string | null
}
```

### 6.2 后端消息附件结构

消息附件应作为稳定 DTO 输出，前端不应再根据 `filePath` 推导展示地址。

建议后端输出：

```ts
interface MessageAttachmentDto {
  id: string
  type: 'image'
  mime_type: string
  file_path: string
  file_size: number
  created_at: string
  url: string
}
```

其中 `url` 供前端直接展示，`file_path` 只保留给服务端内部使用或调试使用。

## 7. 分阶段开发计划

### Phase 1：稳定输入与展示

目标：

- 图片输入、预览、删除可稳定工作
- 用户消息图片回显稳定

任务：

1. 清理前端图片 URL 生成逻辑，统一走运行时 API base
2. 后端附件 DTO 增加显式 `url`
3. 修复 mac / Windows / 打包模式下的图片回显路径问题

### Phase 2：稳定模型消费

目标：

- 图片真正参与推理
- 模型能力判断一致

任务：

1. 前后端统一 `supports_vision`
2. 无 vision 时给出明确提示
3. 保证 `ContextAssembler` 只在允许时注入图片 parts

### Phase 3：稳定生命周期

目标：

- 不产生明显孤儿附件
- 失败路径可恢复

任务：

1. 补孤儿附件清理
2. 上传失败 / 发送失败时保留明确错误信息
3. 消息创建成功后再清除前端待发送附件

### Phase 4：稳定编辑重跑

目标：

- 编辑重跑不丢图片上下文

任务：

1. 为 `edit_and_rerun` 继承附件
2. 增加对应回归测试

## 8. 测试计划

一期至少覆盖以下测试。

### 8.1 前端

1. 粘贴图片后出现预览
2. 拖拽图片后出现预览
3. 删除待发送图片后预览消失
4. 发送带图片消息时调用上传接口并传出 `attachmentIds`
5. 已发送消息图片可正常渲染

### 8.2 后端

1. 上传图片成功返回 `attachment_id`
2. 非图片上传被拒绝
3. 带 `attachment_ids` 的消息能生成附件元数据
4. `ContextAssembler` 能生成图片 content parts
5. `supports_vision == False` 时不注入图片
6. `edit_and_rerun` 继承原附件

### 8.3 端到端

1. 发送“文本 + 1 张图片”后，消息回显正常
2. 模型支持 vision 时，图片参与推理
3. 模型不支持 vision 时，用户收到明确提示
4. 编辑并重跑后，图片仍然存在

## 9. 风险与权衡

### 9.1 当前继续使用 data URL

优点：

- 接入简单
- 不依赖外部对象存储

缺点：

- 请求体大
- 重试成本高
- 多图场景扩展性差

结论：

- 一期接受该方案
- 二期再评估替换为临时可访问 URL 或对象存储方案

### 9.2 先做图片，不做通用附件

优点：

- 范围清晰
- 现有代码复用率高
- 风险可控

缺点：

- 后续扩展到文档输入时需要再次抽象

结论：

- 一期必须先限制为图片输入
- 等图片链路稳定后再做附件系统抽象

## 10. 最终建议

基于当前代码，最合理的推进方式不是“重做多模态”，而是：

**先把图片输入作为一期正式能力补齐，再决定是否扩展到更广义的多模态输入。**

推荐实际开发顺序：

1. 修图片展示 URL 与回显稳定性
2. 统一 `supports_vision`
3. 补孤儿附件清理
4. 修编辑重跑附件继承
5. 补齐前后端和端到端测试

如果以上 5 步完成，这套图片输入能力就可以从“雏形”提升到“可稳定交付的一期功能”。
