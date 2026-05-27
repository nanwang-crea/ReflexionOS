# 统一 Edit 工具设计

**日期**: 2026-05-27  
**状态**: 已批准

## 背景

ReflexionOS 当前的文件编辑能力分散在两个工具中：
- `file` 工具的 `write` action：全量覆写文件，小改动也要重写整个文件
- `patch` 工具：支持 Unified Diff 和 Codex-style patch，但匹配逻辑是严格精确匹配

三个核心痛点：
1. **匹配失败率高**：LLM 生成的缩进/空格与实际文件不一致，patch 精确匹配经常失败
2. **Patch 格式难生成**：Unified Diff / Codex-style 格式对 LLM 来说过于复杂，经常格式错误
3. **write 只能全量覆写**：修改一行也要重写整个文件，效率低且容易出错

参考 opencode 的 `edit` 工具实现（9层级联模糊匹配），将其核心思路移植到 ReflexionOS，同时精简层级、适配现有架构。

## 方案：统一 Edit 工具

废弃 `patch` 工具，移除 `file` 工具的 `write`/`delete` action，统一为一个 `edit` 工具。

### Schema

```json
{
  "name": "edit",
  "description": "文件编辑工具，支持三种模式：str_replace（推荐，简单精确替换）、patch（复杂多行修改）、write（创建新文件）",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "action": {
        "type": "string",
        "enum": ["str_replace", "patch", "write"],
        "description": "编辑模式：str_replace=字符串替换（推荐）、patch=应用diff补丁、write=全量写入（仅创建新文件）"
      },
      "path": {
        "type": "string",
        "description": "文件路径（相对或绝对）"
      },
      "old_string": {
        "type": "string",
        "description": "str_replace 使用：要替换的文本；空字符串表示在文件末尾追加"
      },
      "new_string": {
        "type": "string",
        "description": "str_replace 使用：替换后的文本，必须与 old_string 不同"
      },
      "replace_all": {
        "type": "boolean",
        "default": false,
        "description": "str_replace 使用：替换所有出现位置（默认只替换第一个唯一匹配）"
      },
      "patch": {
        "type": "string",
        "description": "patch 使用：Unified Diff 或 Codex-style patch 内容"
      },
      "content": {
        "type": "string",
        "description": "write 使用：文件完整内容"
      }
    },
    "required": ["action", "path"]
  }
}
```

**参数规则：**
- `str_replace` 需要 `old_string` + `new_string`
- `patch` 需要 `patch`
- `write` 需要 `content`
- `old_string=""` 时：文件存在则追加到末尾，文件不存在则创建

### 级联模糊匹配策略（核心）

借鉴 opencode 的多层级匹配，精简为 **5 层**：

| 层级 | 策略 | 说明 |
|------|------|------|
| 1 | `ExactReplacer` | 精确字符串匹配 |
| 2 | `WhitespaceFlexReplacer` | 处理缩进差异、首尾空白、行内 trim。合并了 LineTrimmed、IndentationFlexible、TrimmedBoundary 的能力 |
| 3 | `AnchorReplacer` | 首尾行锚定 + 中间行匹配比例（≥50%）。轻量版 BlockAnchor，不用 Levenshtein，改用简单行匹配计数 |
| 4 | `EscapeNormalizer` | 反转义 `\n`/`\t`/`\r` 等转义序列后匹配 |
| 5 | `GlobalReplacer` | 配合 `replace_all` 的批量精确匹配 |

**匹配流程：**

```
for each replacer in [Exact, WhitespaceFlex, Anchor, EscapeNormalizer, Global]:
    candidates = replacer.find_matches(content, old_string)
    if no candidates: continue
    if replace_all and candidates: return replace_all_matches()
    if exactly one unique candidate: return replace_single()
    # multiple candidates → continue to next layer

if no candidate found across all layers:
    raise "未找到匹配内容"
if all layers had multiple candidates:
    raise "匹配到多个位置，请增加上下文"
```

**各层详细算法：**

#### ExactReplacer
直接 `content.find(old_string)`，找到唯一匹配即返回。

#### WhitespaceFlexReplacer
1. 将 `old_string` 和 `content` 都按行拆分
2. 对每行去除前后空白后比较
3. 找到所有行 trim 匹配的起始位置
4. 对每个候选位置，检查原始缩进是否一致（公共前缀空白差异可容忍）
5. 只保留唯一候选

#### AnchorReplacer
1. 要求 `old_string` 至少 3 行
2. 取 `old_string` 的第一行和最后一行（trim 后）作为锚点
3. 在 `content` 中找到所有首行匹配的位置
4. 对每个候选，检查尾行是否也匹配
5. 对首尾都匹配的候选，计算中间行匹配比例（trim 后比较）
6. 比例 ≥ 50% 则视为候选
7. 取最佳候选；多候选则跳过

#### EscapeNormalizer
1. 对 `old_string` 反转义：`\\n` → `\n`，`\\t` → `\t` 等
2. 同时尝试匹配原始和反转义版本

#### GlobalReplacer
1. 找到 `old_string` 在 `content` 中的所有出现位置
2. 当 `replace_all=True` 时使用，执行全量替换

### 并发控制

对同一文件路径加 asyncio Lock，防止并发编辑冲突：

```python
import asyncio
_file_locks: dict[str, asyncio.Lock] = {}

def _get_lock(path: str) -> asyncio.Lock:
    if path not in _file_locks:
        _file_locks[path] = asyncio.Lock()
    return _file_locks[path]
```

### 行尾检测

```python
def detect_line_ending(content: str) -> str:
    if '\r\n' in content:
        return '\r\n'
    return '\n'

def normalize_to_lf(text: str) -> str:
    return text.replace('\r\n', '\n')

def convert_line_ending(text: str, ending: str) -> str:
    if ending == '\r\n':
        return text.replace('\n', '\r\n')
    return text
```

在 `str_replace` 执行流程中：
1. 读取文件，检测行尾风格
2. 将 `old_string` 和 `new_string` normalize 为 `\n`
3. 在 normalize 后的 content 上执行替换
4. 将结果还原为原行尾风格后写入

### 错误信息

匹配失败时，返回有帮助的诊断信息：
- `old_string` 的前 3 行内容
- 在文件中找到的最相似位置（如果有）
- 建议增加上下文或检查缩进

### Patch 模式

复用现有 `diff_parser.py` 中的 `DiffParser` 和 `CodexPatchParser`，但在 `_apply_hunk` 和 `_apply_codex_hunk` 中也引入模糊匹配：
- `_apply_hunk`：上下文行验证允许空白差异
- `_apply_codex_hunk`：`old_block` 匹配使用 WhitespaceFlexReplacer 而非精确比较

### Write 模式

直接复用现有 `file_tool._write_file` 的逻辑：
- `validate_write_path` 安全检查
- 自动创建目录
- 异步写入

## 工具注册变更

`agent_service.py` 的 `_build_run_tool_registry`：

```python
# Before:
registry.register(FileTool(path_security))    # read/write/list/delete/search
registry.register(PatchTool(path_security))   # unified diff / codex

# After:
registry.register(FileTool(path_security))    # read/list/search only
registry.register(EditTool(path_security))    # str_replace/patch/write
```

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `backend/app/tools/edit_tool.py` | **新增**：EditTool 实现，包含 5 层 replacer |
| `backend/app/tools/file_tool.py` | **修改**：移除 `write`/`delete` action 及相关 schema |
| `backend/app/tools/patch_tool.py` | **删除**：功能并入 EditTool |
| `backend/app/tools/diff_parser.py` | **保留**：被 EditTool 复用 |
| `backend/app/services/agent_service.py` | **修改**：注册变更 |
| `backend/app/execution/runtime_tool_definitions.py` | **修改**：更新工具 schema |
| `backend/app/execution/prompt_manager.py` | **修改**：更新 prompt 引导 LLM 优先使用 str_replace |
| `backend/tests/test_tools/test_edit_tool.py` | **新增**：EditTool 测试 |
| `backend/tests/test_tools/test_file_tool.py` | **修改**：移除 write/delete 测试 |
| `backend/tests/test_tools/test_patch_tool.py` | **删除** |
| `frontend/src/components/execution/receiptUtils.ts` | **修改**：edit 工具的分类逻辑 |

## 不影响的部分

- `file_content_service.py` 的 HTTP API（给 UI 用，不是 agent 工具）
- `path_security.py`
- 前端 Monaco 编辑器组件
- `codeTabStore`、`fileApi` 等前端 store

## 测试策略

`test_edit_tool.py` 覆盖以下场景：

1. **str_replace 精确匹配**：old_string 精确存在于文件中
2. **str_replace 缩进差异**：old_string 缩进与文件不同，WhitespaceFlex 匹配成功
3. **str_replace 首尾锚定**：old_string 有中间行差异，AnchorReplacer 匹配成功
4. **str_replace 转义差异**：old_string 含转义序列，EscapeNormalizer 匹配成功
5. **str_replace replace_all**：多处匹配全部替换
6. **str_replace 未找到**：返回有意义的错误信息
7. **str_replace 多处匹配**：返回错误，建议增加上下文
8. **str_replace 空文件追加**：old_string="" 在空文件中追加
9. **patch unified diff**：复用现有 diff 测试用例
10. **patch codex-style**：复用现有 codex 测试用例
11. **patch 模糊匹配**：hunk 上下文行允许空白差异
12. **write 创建新文件**：content 写入不存在的路径
13. **并发编辑**：同一文件两个并发 edit 操作，结果一致
14. **行尾保留**：CRLF 文件编辑后仍为 CRLF
15. **路径安全**：敏感路径被拦截
