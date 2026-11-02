# 文件功能：写操作并发调度策略（对齐 reflexion-os-studio 的 mutation coordinator 精简版）
# 文件描述：判定一轮 LLM 请求中的哪些写操作可以安全并发执行——只有"文件级 edit
#          （str_replace/write）且目标路径互不相同"的连续段才并发；shell/browser/
#          delegate/未知足迹（如 patch 文本内嵌路径）以及同路径调用保持串行。
#          工具层的按路径文件锁（edit_tool._get_lock）作为最后一道互斥兜底。
# 核心逻辑：从指定下标向后收集"可并发写段"：连续命中 file-scoped edit 且路径
#          （归一化后）互不重复、不超过单批上限即计入；遇到任何不合格调用立即停。
import re
from app.llm.base import LLMToolCall

# edit 工具中目标路径可直接从参数解析的写动作（patch 动作的路径内嵌在补丁文本里，
# 解析代价高且可能多文件，视为未知足迹保持串行）
FILE_SCOPED_WRITE_ACTIONS = frozenset({"str_replace", "write"})

# 单个并发写批的上限（对齐只读批次 MAX_READ_ONLY_CALLS_PER_BATCH 的保守值）
MAX_PARALLEL_WRITE_BATCH = 4


def extract_write_target_path(tool_call: LLMToolCall) -> str | None:
    """提取写调用的目标路径；无法可靠解析时返回 None（视为未知足迹，保持串行）。

    输入：tool_call - LLM 本轮请求的单个工具调用
    逻辑：仅 edit 工具的 str_replace/write 动作可从 arguments.path 直接解析；
          路径归一化（反斜杠转正斜杠）后返回，空/非法返回 None
    输出：归一化路径字符串，或 None
    """
    if tool_call.name != "edit":
        return None
    action = tool_call.arguments.get("action")
    if action not in FILE_SCOPED_WRITE_ACTIONS:
        return None
    path = tool_call.arguments.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    return path.replace("\\", "/").strip()


def collect_parallel_write_run(write_calls: list[LLMToolCall], index: int) -> list[LLMToolCall]:
    """从 index 开始收集可并发执行的连续写调用段（长度至少为 1）。

    输入：write_calls - 本轮全部写操作调用（按 LLM 给出顺序）；index - 起始下标
    逻辑：逐个向后考察——
      - 文件级 edit 且路径归一化后与本段已有路径互不相同：计入本段；
      - 任何不合格调用（非 edit、patch 动作、路径重复、超上限）：立即停止收集。
    输出：write_calls[index:index+len] 的切片；调用方以 len==1 判定退化为串行
    """
    run: list[LLMToolCall] = []
    paths: set[str] = set()
    i = index
    while i < len(write_calls) and len(run) < MAX_PARALLEL_WRITE_BATCH:
        path = extract_write_target_path(write_calls[i])
        if path is None or path in paths:
            break
        run.append(write_calls[i])
        paths.add(path)
        i += 1
    return run
