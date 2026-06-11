# 计划更新问题修复报告

## ✅ 已完成修复

### 修改文件
`backend/app/tools/plan_tool.py`

### 修改内容

#### 1. 改进 plan_tool description（第19-28行）
```python
# 修复前
"Manage execution plans for multi-step tasks. "
"Send the FULL step list every call — NEVER omit completed steps, always keep them with status=completed and findings. "
...

# 修复后
"Update execution plan after completing each step. "
"Mark completed step with findings, set next step to in_progress. "
"Send FULL step list — keep all completed steps intact. "
"Update when: current step is done OR need to track progress. "
...
```

**改进点**：
- 从"管理计划"改为"完成步骤后更新"（更明确触发时机）
- 简化规则描述，突出核心动作

#### 2. 增强当前步骤的输出反馈（第130-136行）
```python
# 修复前
if current:
    output_parts.append(f"[Current] {current.content}")
    output_parts.append("Continue executing this step with your tools. Do NOT stop — the plan is not yet complete.")

# 修复后
if current:
    output_parts.append(f"[Current] {current.content}")
    hint = self._analyze_step_action(current.content)
    output_parts.append(f"→ {hint}")
    output_parts.append("Execute these actions, then update the plan to mark this step completed.")
```

**改进点**：
- 添加具体行动提示（如"读文件 → 定位问题 → 用 edit 修复"）
- 明确执行后需要更新计划

#### 3. 新增步骤行动分析方法
```python
def _analyze_step_action(self, step_content: str) -> str:
    """分析步骤内容，返回具体行动提示"""
    content_lower = step_content.lower()
    
    if any(kw in content_lower for kw in ["read", "check", "inspect", "review", "understand"]):
        return "Use file/grep tools to read and understand the relevant code"
    
    if any(kw in content_lower for kw in ["fix", "修复", "solve", "resolve"]):
        return "Read the target file, identify the issue, then use edit tool to fix it"
    
    if any(kw in content_lower for kw in ["test", "verify", "run", "验证"]):
        return "Use shell tool to run tests or verification commands"
    
    if any(kw in content_lower for kw in ["create", "add", "implement", "write"]):
        return "Use edit tool to create or add the required code/files"
    
    if any(kw in content_lower for kw in ["refactor", "restructure", "reorganize"]):
        return "Read existing code, plan changes, then use edit tool to restructure"
    
    return "Use appropriate tools to complete this step"
```

**功能**：
- 根据步骤内容关键词，提供具体工具使用建议
- 支持中英文关键词

---

## 修复效果对比

### 修复前
```
Plan updated (0/3 done)...
  ► Fix the bug in conversation_projection.py
[Current] Fix the bug in conversation_projection.py
Continue executing this step with your tools. Do NOT stop — the plan is not yet complete.
```
❌ Agent 不知道该用什么工具、怎么执行

### 修复后
```
Plan updated (0/3 done)...
  ► Fix the bug in conversation_projection.py
[Current] Fix the bug in conversation_projection.py
→ Read the target file, identify the issue, then use edit tool to fix it
Execute these actions, then update the plan to mark this step completed.
```
✅ Agent 清楚知道：读文件 → 定位问题 → 用 edit 修复 → 更新计划

---

## 验证结果

### Python 编译检查
```bash
python3 -m py_compile app/tools/plan_tool.py
```
✅ 通过

### 模块导入检查
❌ 无法验证（缺少依赖 pydantic）
- 需要在完整环境中测试

---

## 解决的问题

1. ✅ **计划更新缺少上下文**：现在会根据当前步骤内容提供具体行动建议
2. ✅ **不知道何时更新计划**：description 明确"完成步骤后更新"
3. ✅ **不知道需要做什么**：输出中包含具体工具使用建议

---

## 建议的后续测试

1. **功能测试**：创建一个多步骤计划，观察每步的输出提示
2. **关键词覆盖测试**：验证不同类型步骤（读取、修复、测试、创建）的提示准确性
3. **中文支持测试**：验证中文关键词（如"修复"）是否正常工作

---

生成时间: 2026-06-11
修复范围: backend/app/tools/plan_tool.py
状态: 代码修改完成，等待完整环境测试
