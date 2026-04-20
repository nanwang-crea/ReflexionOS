# 多供应商实例与模型选择第一阶段实施计划

**日期**: 2026-04-18  
**状态**: 已完成  
**范围**: 第一阶段

## 一、背景

当前 ReflexionOS 的 LLM 配置仍然是单条全局配置模型,只能保存一组 `provider + model + api_key + base_url`。这会直接限制后续体验:

- 无法同时配置多个同类型供应商实例
- 无法把“供应商管理”和“聊天时模型选择”拆开
- 聊天会话无法记住自己的模型选择
- 设置页无法在保存前验证接入配置是否可用

本次优化的核心目标，是把现有单配置结构升级为“供应商实例管理 + 模型列表管理 + 全局默认 + 会话记忆”。

## 二、已确认的产品决策

- 允许同一协议类型配置多条供应商实例
- “供应商”定义为“用户配置的接入方实例”，不是抽象协议枚举
- 聊天模型选择采用“全局默认 + 会话记忆”
- 聊天页面不允许手动输入模型，只能从已配置模型中选择
- 设置页面允许手动输入模型
- 设置页面第一阶段就提供“测试连接”按钮

## 三、第一阶段目标

### 3.1 用户可见目标

- 在设置页新增、编辑、删除供应商实例
- 每个供应商实例下维护多个模型
- 设置全局默认供应商和默认模型
- 在聊天输入框下方选择当前会话使用的供应商和模型
- 新会话自动继承全局默认，已有会话记住自己的最近一次选择
- 在设置页对草稿配置执行连接测试

### 3.2 第一阶段非目标

- 不做自动拉取远端模型列表
- 不做模型级高级参数矩阵管理
- 不做供应商健康检查轮询
- 不做按项目维度的独立默认模型

## 四、核心概念与信息架构

### 4.1 概念拆分

- `providerType`
  - 底层协议类型，例如 `openai_compatible`、`anthropic`、`ollama`
- `providerInstance`
  - 用户在设置页维护的一条接入方配置，例如“OpenAI 官方”“硅基流动”“本地 Ollama”
- `providerModel`
  - 挂在某个供应商实例下的一条模型配置，例如 `gpt-4.1`、`qwen-max`、`llama3.1:8b`
- `defaultSelection`
  - 全局默认的 `providerInstance + providerModel`
- `sessionSelection`
  - 某个聊天会话当前使用的 `providerInstance + providerModel`

### 4.2 建议数据结构

#### 前端类型

```ts
type ProviderType = 'openai_compatible' | 'anthropic' | 'ollama'

interface ProviderModel {
  id: string
  displayName: string
  modelName: string
  enabled: boolean
}

interface ProviderInstance {
  id: string
  name: string
  providerType: ProviderType
  apiKey?: string
  baseUrl?: string
  models: ProviderModel[]
  defaultModelId?: string
  enabled: boolean
}

interface LLMSettingsState {
  providers: ProviderInstance[]
  defaultProviderId?: string
  defaultModelId?: string
}

interface ChatSessionPreference {
  preferredProviderId?: string
  preferredModelId?: string
}
```

#### 后端配置模型

```python
class ProviderModelConfig(BaseModel):
    id: str
    display_name: str
    model_name: str
    enabled: bool = True


class ProviderInstanceConfig(BaseModel):
    id: str
    name: str
    provider_type: ProviderType
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    models: list[ProviderModelConfig] = Field(default_factory=list)
    default_model_id: Optional[str] = None
    enabled: bool = True


class LLMSettings(BaseModel):
    providers: list[ProviderInstanceConfig] = Field(default_factory=list)
    default_provider_id: Optional[str] = None
    default_model_id: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
```

#### 执行时解析配置

```python
class ResolvedLLMConfig(BaseModel):
    provider_id: str
    provider_type: ProviderType
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
```

## 五、页面与交互改造

### 5.1 设置页

- 供应商列表区
  - 展示已配置的供应商实例
  - 支持新增、编辑、删除
- 供应商编辑区
  - 字段包含 `名称、协议类型、Base URL、API Key`
  - 支持手动录入模型列表
  - 支持设置供应商默认模型
- 全局默认区
  - 选择默认供应商
  - 选择默认模型
- 连接测试
  - 使用当前表单草稿发起测试
  - 成功时展示可用结果
  - 失败时展示错误信息并保留表单内容

### 5.2 聊天页

- 在聊天输入框下方增加选择区
- 选择区至少包含：
  - 供应商选择器
  - 模型选择器
- 新会话创建时：
  - 默认使用全局默认供应商与模型
- 已有会话切回时：
  - 恢复该会话上次选择
- 聊天页不提供模型手动输入能力
- 如果当前会话绑定的供应商或模型已被删除：
  - 优先回退到全局默认
  - 若全局默认也不可用，则提示用户重新选择

## 六、接口设计

### 6.1 LLM 管理接口

- `GET /api/llm/providers`
  - 返回所有供应商实例及其模型
- `POST /api/llm/providers`
  - 新增供应商实例
- `PUT /api/llm/providers/{provider_id}`
  - 更新供应商实例
- `DELETE /api/llm/providers/{provider_id}`
  - 删除供应商实例
- `POST /api/llm/providers/test`
  - 用当前草稿配置测试连接
  - 请求体应支持未保存的供应商与模型草稿
- `GET /api/llm/default`
  - 返回全局默认供应商与模型
- `PUT /api/llm/default`
  - 更新全局默认供应商与模型

### 6.2 Agent 执行接口改造

- `POST /api/agent/execute`
  - 请求体新增 `provider_id`、`model_id`
  - 前端显式传入，后端按会话选择执行

### 6.3 连接测试策略

- 对于 `openai_compatible`
  - 使用表单中的 `base_url + api_key + 目标模型` 发起一次轻量探测
- 对于 `anthropic`
  - 使用相应 SDK 或 HTTP 探测
- 对于 `ollama`
  - 测试本地服务可达性与模型存在性

第一阶段建议优先保证 `openai_compatible` 路径完整可用，其他类型先在接口结构上保持兼容。

## 七、前后端改造清单

### 7.1 前端

- [frontend/src/types/llm.ts](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend/src/types/llm.ts)
  - 从单一 `LLMConfig` 扩展为供应商实例与模型结构
- [frontend/src/stores/settingsStore.ts](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend/src/stores/settingsStore.ts)
  - 保存供应商列表和全局默认选择
- [frontend/src/stores/workspaceStore.ts](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend/src/stores/workspaceStore.ts)
  - 为会话增加 `preferredProviderId`、`preferredModelId`
- [frontend/src/components/chat/ChatInput.tsx](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend/src/components/chat/ChatInput.tsx)
  - 增加聊天底部模型选择 UI
- [frontend/src/pages/AgentWorkspace.tsx](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend/src/pages/AgentWorkspace.tsx)
  - 发送消息时带上会话当前选择
- [frontend/src/pages/SettingsPage.tsx](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend/src/pages/SettingsPage.tsx)
  - 改造为供应商实例管理页
- [frontend/src/services/apiClient.ts](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend/src/services/apiClient.ts)
  - 新增供应商 CRUD、默认选择、测试连接接口

### 7.2 后端

- [backend/app/models/llm_config.py](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend/app/models/llm_config.py)
  - 重构为供应商实例、模型、默认选择相关模型
- [backend/app/config/settings.py](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend/app/config/settings.py)
  - 配置文件从单条 `llm` 扩展为 `providers + default selection`
- [backend/app/api/routes/llm.py](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend/app/api/routes/llm.py)
  - 提供供应商管理与测试连接接口
- [backend/app/services/agent_service.py](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend/app/services/agent_service.py)
  - 根据 `provider_id + model_id` 解析实际运行配置

## 八、配置重建策略

### 8.1 决策

第一阶段不兼容旧 JSON 配置结构，直接切换到新的 `providers + default selection` 配置模型。

这样做的原因是：

- 当前项目仍处于早期阶段，历史配置负担很小
- 目前仅有单条本地 LLM 配置，重建成本可接受
- 可以避免在 `settings.py`、`agent_service.py`、`llm_config.py` 中保留一层临时迁移逻辑
- 能让后端模型和接口从第一天起就围绕新结构实现，减少后续二次清理

### 8.2 执行策略

- 升级后直接采用新的配置文件结构
- 不再尝试把旧的 `provider + model + api_key + base_url` 自动转换为新结构
- 当检测到旧配置不可用时，视为“未配置”状态处理
- 用户需要在新的设置页重新配置供应商、模型和默认项

### 8.3 用户影响与提示

- 这次改造属于一次可接受的破坏性配置变更
- 升级后旧的 LLM 配置将不再生效
- 首次进入聊天页或设置页时，应明确提示用户重新完成 LLM 配置
- 设置页应尽量降低重新配置成本，例如优先提供清晰的空状态和保存反馈

## 九、测试计划

### 9.1 后端测试

- 新配置文件结构可正常初始化和保存
- 遇到旧配置结构时按“未配置”状态处理
- 可新增多个同类型供应商实例
- 删除默认供应商时的默认值回退
- 执行接口根据 `provider_id + model_id` 解析正确配置
- 测试连接接口在成功和失败时都返回可读结果

### 9.2 前端测试

- 设置页新增、编辑、删除供应商流程
- 模型列表手动输入、保存和回显
- 全局默认选择切换
- 新会话继承默认模型
- 已有会话保留自己的模型记忆
- 聊天页只展示已配置模型，不允许自由输入

### 9.3 联调测试

- 从设置页创建供应商并测试连接成功
- 切到聊天页使用该模型发起执行
- 切换不同会话时恢复各自模型选择
- 删除正在被旧会话引用的模型后，前端回退逻辑正确

## 十、实施顺序建议

1. 先重构后端配置模型与配置文件结构
2. 再补齐 LLM 管理接口与测试连接接口
3. 然后改造前端类型和状态管理
4. 最后落地设置页和聊天页交互
5. 完成后做一次前后端联调和回归测试

## 十一、验收标准

- 用户可同时保存两条及以上同类型供应商实例
- 用户可为一个供应商维护多个模型
- 用户可设置全局默认供应商和模型
- 新聊天会话自动继承全局默认
- 同一聊天会话会记住上次所选供应商和模型
- 聊天页模型选择不允许手动输入
- 设置页支持手动输入模型并保存
- 设置页支持测试连接，且结果可视化反馈明确
- 实际执行请求能够使用当前会话选择的供应商和模型
- 升级后用户能够在无旧配置兼容逻辑的前提下重新完成配置并正常使用
