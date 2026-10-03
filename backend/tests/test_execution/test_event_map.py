"""
文件功能：事件地图活性测试（test_event_map）
文件描述：保证 docs/event-map.md 与执行层代码中的事件发射点严格一致——
         代码新增/删除事件而文档未同步时测试失败，防止事件地图腐化。
核心逻辑：
  - 用 ast 解析 app/execution/ 与 app/agents/ 下全部 .py 文件，收集
    emit("...") / self._emit("...") 调用的第一个字符串字面量参数
    （仅取形如 "domain:name" 的事件名；非常量参数直接报错，要求改字面量）；
  - 从 docs/event-map.md 的表格首列（反引号包裹的事件名）解析已登记集合；
  - 双向比对：代码有而文档无 → 漏登记；文档有而代码无 → 腐化条目。
注意：刻意不做全文正则扫描——prompt 文本中形如 "a:b" 的字符串不是事件，
     只有作为 emit 调用首参出现的字面量才算。
"""

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [BACKEND_ROOT / "app" / "execution", BACKEND_ROOT / "app" / "agents"]
EVENT_MAP_DOC = BACKEND_ROOT.parent / "docs" / "event-map.md"

# 事件名约定：小写字母/下划线组成的 "域:名" 形式
EVENT_NAME_RE = re.compile(r"^[a-z_]+:[a-z_]+$")
# 事件地图表格首列：| `run:start` | ... | ——提取反引号内事件名
DOC_TABLE_ROW_RE = re.compile(r"^\|\s*`([a-z_]+:[a-z_]+)`\s*\|")


def collect_code_events() -> dict[str, list[str]]:
    """AST 扫描执行层全部 emit 调用，收集事件类型及其发射位置。

    入参：无。
    功能：遍历 SCAN_DIRS 下所有 .py 文件；对每个 ast.Call，若 func 是
         `xxx.emit` / `xxx._emit` 属性调用或裸 `emit(...)` 调用，且首参是
         符合事件名约定的字符串字面量，则记录；首参存在但不是字符串常量
         （f-string / 变量 / 表达式）时抛 AssertionError——事件名必须是
         可静态提取的字面量，否则本测试无法保障地图活性。
    出参：dict[str, list[str]] - {事件类型: ["文件:行号", ...]}。
    """
    events: dict[str, list[str]] = {}
    for scan_dir in SCAN_DIRS:
        for py_file in sorted(scan_dir.glob("*.py")):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not _is_emit_call(node):
                    continue
                location = f"{py_file.name}:{node.lineno}"
                if not node.args:
                    continue
                first_arg = node.args[0]
                if not isinstance(first_arg, ast.Constant) or not isinstance(
                    first_arg.value, str
                ):
                    raise AssertionError(
                        f"{location} 的 emit 首参不是字符串字面量，"
                        "事件名必须可静态提取（请改为字面量）"
                    )
                if EVENT_NAME_RE.match(first_arg.value):
                    events.setdefault(first_arg.value, []).append(location)
    return events


def _is_emit_call(node: ast.Call) -> bool:
    """判断一个 Call 节点是否为事件发射调用。

    入参：node (ast.Call) - 待判定的调用节点。
    功能：识别两种形态——属性调用 self._emit(...) / self.emit(...)（含任意
         对象的 .emit/._emit 方法），以及裸函数调用 emit(...)；
         排除 emit 作为关键字参数出现的场景（如 ToolCallExecutor(emit=...)），
         因为那是构造调用，func 不是 emit 本身。
    出参：bool - 是发射调用返回 True。
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in ("emit", "_emit")
    if isinstance(func, ast.Name):
        return func.id in ("emit", "_emit")
    return False


def collect_doc_events() -> set[str]:
    """从事件地图文档表格首列解析已登记的事件类型集合。

    入参：无。
    出参：set[str] - 文档中登记的事件类型（反引号包裹、位于表格行首列）。
    """
    documented: set[str] = set()
    for line in EVENT_MAP_DOC.read_text(encoding="utf-8").splitlines():
        match = DOC_TABLE_ROW_RE.match(line.strip())
        if match:
            documented.add(match.group(1))
    return documented


class TestEventMapLiveness:
    """M-01：代码事件与事件地图双向一致"""

    def test_event_map_doc_exists(self):
        """事件地图文档必须存在（否则后续比对失去意义）。

        入参：无。出参：无。
        """
        assert EVENT_MAP_DOC.exists(), f"事件地图文档缺失: {EVENT_MAP_DOC}"

    def test_code_events_all_documented(self):
        """代码中发射的每种事件都必须已在事件地图登记（漏登记拦截）。

        入参：无。出参：无（失败消息列出漏登记事件及其位置）。
        """
        code_events = collect_code_events()
        documented = collect_doc_events()
        undocumented = sorted(set(code_events) - documented)

        assert not undocumented, (
            "以下事件在代码中发射但未登记到 docs/event-map.md：\n"
            + "\n".join(
                f"  {name}（发射于 {', '.join(code_events[name])}）"
                for name in undocumented
            )
        )

    def test_documented_events_all_in_code(self):
        """事件地图登记的每种事件都必须在代码中存在（腐化条目拦截）。

        入参：无。出参：无（失败消息列出腐化条目）。
        """
        code_events = collect_code_events()
        documented = collect_doc_events()
        stale = sorted(documented - set(code_events))

        assert not stale, (
            "以下事件登记在 docs/event-map.md 但代码中已不存在，"
            "请删除对应条目：\n" + "\n".join(f"  {name}" for name in stale)
        )
