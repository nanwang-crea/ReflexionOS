# 配置驱动的模型能力系统

**日期**: 2026-06-15
**状态**: 待审核

## 背景

当前 `model_capabilities.py` 使用硬编码白名单判断模型是否支持视觉能力。问题：

1. 白名单永远追不上模型更新速度（OpenAI/Anthropic/Gemini/OpenRouter/本地模型）
2. `supports_vision()` 函数已定义但从未被调用
3. attachment_service 直接转换图片，不检查模型能力，发给纯文本模型会 400

## 设计目标

- 能力由配置驱动，不维护硬编码列表
- 三态标记：`None`（未探测）/ `True`（启用）/ `False`（禁用）
- 连接测试时自动探测 vision 能力
- 用户可手动覆盖探测结果

## 数据模型

### ProviderModelConfig 扩展

**文件**: `backend/app/models/llm_config.py`

```python
class ProviderModelConfig(BaseModel):
    id: str
    display_name: str
    model_name: str
    context_window: int = 128000
    enabled: bool = True
    # 新增能力字段
    supports_vision: bool | None = None      # 三态：None=未探测, True/False=已知
    supports_tools: bool | None = True       # 默认开启
    supports_reasoning: bool | None = True   # 默认开启
```

### ResolvedLLMConfig 扩展

**文件**: `backend/app/models/llm_config.py`

```python
class ResolvedLLMConfig(BaseModel):
    # ... 现有字段 ...
    supports_vision: bool | None = None
    supports_tools: bool | None = True
    supports_reasoning: bool | None = True
```

从 `ProviderModelConfig` 透传到 `ResolvedLLMConfig`，下游代码直接读 resolved config。

## 自动探测流程

### 触发时机

用户点击"测试连接"时，文本请求成功后自动执行 vision 探测。

### 探测逻辑

**文件**: `backend/app/services/llm_provider_service.py` → `test_provider_connection`

```
1. 发送普通文本请求（已有逻辑）
2. 文本请求成功后：
   a. 构造 1x1 PNG 的 image_url content part
   b. 发送带图片的请求
   c. 成功 → supports_vision = True
   d. 任何异常 → supports_vision = False
3. 探测结果写回 ProviderModelConfig 并持久化
```

### 1x1 PNG 数据

使用硬编码的最小 PNG base64：

```python
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
```

### 探测结果持久化

探测完成后，更新对应 model 的 `supports_vision` 字段，通过 `config_manager.update_llm()` 写入 JSON 配置。

## 能力检查接入点

### attachment_service

**文件**: `backend/app/services/attachment_service.py`

当前：直接转换所有图片附件为 `LLMContentPart`，不检查模型能力。

改为：
1. 函数签名增加 `supports_vision: bool | None` 参数
2. `supports_vision == False` 时，跳过图片附件并记录警告
3. `supports_vision is None` 时，仍然转换（向后兼容，不阻断用户）

### agent_service

**文件**: `backend/app/services/agent_service.py`

调用 attachment_service 前，从 `resolved_llm_config` 读取 `supports_vision` 传入。

## 删除硬编码白名单

**文件**: `backend/app/llm/model_capabilities.py`

删除整个文件：
- `VISION_CAPABLE_MODELS` 集合
- `supports_vision()` 函数

**文件**: `backend/tests/test_llm/test_model_capabilities.py`

删除整个测试文件（测试的是已删除的白名单逻辑）。

## 前端展示

### Provider 设置页

**文件**: `frontend/src/features/llm/` 相关组件

每个 model 行增加能力状态展示：

| supports_vision | 显示 |
|-----------------|------|
| `None` | Auto（灰色标签） |
| `True` | Enabled（绿色标签） |
| `False` | Disabled（红色标签） |

`supports_tools` 和 `supports_reasoning` 默认 True，UI 上只显示 Enabled 状态，暂不做切换控件。

### 连接测试后刷新

测试连接成功后：
1. 后端返回更新后的 model config（含探测结果）
2. 前端刷新该 model 的能力状态显示

## 涉及文件清单

| 文件 | 改动类型 |
|------|----------|
| `backend/app/models/llm_config.py` | 修改：增加能力字段 |
| `backend/app/services/llm_provider_service.py` | 修改：连接测试增加 vision 探测 |
| `backend/app/services/attachment_service.py` | 修改：接入 supports_vision 检查 |
| `backend/app/services/agent_service.py` | 修改：传递 supports_vision |
| `backend/app/llm/model_capabilities.py` | 删除 |
| `backend/tests/test_llm/test_model_capabilities.py` | 删除 |
| `backend/tests/test_services/test_attachment_service.py` | 修改：增加能力检查测试 |
| `backend/tests/test_services/test_llm_provider_service.py` | 修改：增加探测测试 |
| `frontend/src/features/llm/` | 修改：能力状态展示 |

## 向后兼容

- 现有 JSON 配置中无能力字段的 model，`supports_vision` 默认 `None`
- `None` 状态下 attachment_service 仍然转换图片（不阻断）
- 用户需手动测试一次连接以完成自动探测
