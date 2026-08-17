# backend/app/security/command_arity.py
# 命令信任前缀规则提取：把一条已获批准的命令，归纳成一条可复用的"前缀信任规则"，
# 用于会话内后续遇到相同前缀的命令时自动放行（免重复审批）。
# 核心安全考量：对高危命令（DENY_TRUST_COMMANDS 中列出的，如 rm/chmod/dd 等）
# 不能只信任命令名前缀（如 "rm *"），否则一次批准 "rm a.txt" 会导致以后
# "rm -rf /" 之类的危险调用也被自动放行；因此这些命令的信任规则要保留完整命令文本，
# 缩小信任范围到"完全相同的命令+任意后续参数"。
import shlex

# 需要精确匹配完整命令（而非仅命令名前缀）才能建立信任规则的高危命令集合。
# 原因：这些命令一旦被赋予"前缀信任"，攻击面会被无限放大（例如信任了一次 rm 就等于
# 信任了所有 rm 调用，包括 rm -rf /）。因此对它们，信任规则退化为"命令原文 + *"。
DENY_TRUST_COMMANDS: set[str] = {
    "rm",
    "chmod",
    "chown",
    "mkfs",
    "dd",
    "fdisk",
    "mkdisk",
}


def extract_prefix_rule(command: str) -> str:
    """从单条命令提取信任前缀规则（单段命令版本，不处理管道/链式组合）。

    参数：
        command: 原始命令字符串。

    逻辑：
        1. 空命令直接返回通配 "*"（不建立任何有意义的信任）。
        2. 用 shlex 解析出 token；解析失败（引号不闭合等）时退化为按空白切分。
        3. 取第一个 token 作为命令名 key：
           - 若命令名在 DENY_TRUST_COMMANDS（高危命令）中，返回"完整命令 + *"，
             即只信任这一条具体命令的参数扩展，不放宽到整个命令名；
           - 否则返回"命令名 + *"，信任范围放宽到该命令名的任意参数调用。

    返回：
        规则字符串，形如 "python *" 或 "rm -rf /tmp/foo *"，供后续 fnmatch 风格匹配使用；
        无法解析出有效命令时返回 "*"（通配，即不建立信任限制的兜底）。
    """
    if not command or not command.strip():
        return "*"

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    if not tokens:
        return "*"

    key = tokens[0]

    if key in DENY_TRUST_COMMANDS:
        return command + " *"

    return key + " *"


def extract_prefix_rules(command: str) -> list[str]:
    """从链式 shell 命令的每个分段分别提取信任前缀规则。

    参数：
        command: 原始命令字符串，可能包含 |、&&、||、; 等链式/管道操作符。

    逻辑：
        1. 空命令直接返回 ["*"]。
        2. 用 _split_chain 按 |、&&、||、; 拆分命令（引号内的这些符号不算分隔符）。
        3. 对每个非空分段，同 extract_prefix_rule 的逻辑单独生成一条规则：
           高危命令（DENY_TRUST_COMMANDS）保留完整分段文本，其余命令只取命令名。
        这样 ``cd /path && python3 -c "..."`` 会产生 [``cd *``, ``python3 *``]，
        使得日后单独出现的 ``python3 -c "..."`` 也能被信任，避免每个组合都要重新审批。

    返回：
        规则字符串列表，与分段顺序一致；没有解析出任何有效分段时返回 ["*"]。
    """
    if not command or not command.strip():
        return ["*"]

    segments = _split_chain(command)
    rules: list[str] = []
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()
        if not tokens:
            continue
        key = tokens[0]
        if key in DENY_TRUST_COMMANDS:
            rules.append(segment + " *")
        else:
            rules.append(key + " *")

    return rules or ["*"]


def _split_chain(command: str) -> list[str]:
    """按 |、&&、||、; 拆分链式 shell 命令（简单的引号感知状态机）。

    参数：
        command: 原始命令字符串。

    逻辑：
        逐字符扫描，用 in_single/in_double 两个状态位跟踪是否处于引号内；
        只有在引号外遇到 &&、||、|、; 才切分为新的一段，引号内的同名字符原样保留
        （避免把 python3 -c "a && b" 误拆成两段）。

    返回：
        按顺序排列的命令分段列表（未做 strip，调用方自行处理首尾空白）。
    """
    segments: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False

    i = 0
    while i < len(command):
        ch = command[i]

        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
            i += 1
            continue
        elif ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
            i += 1
            continue

        if not in_single and not in_double:
            if ch == '&' and i + 1 < len(command) and command[i + 1] == '&':
                segments.append(''.join(current))
                current = []
                i += 2
                continue
            elif ch == '|' and i + 1 < len(command) and command[i + 1] == '|':
                segments.append(''.join(current))
                current = []
                i += 2
                continue
            elif ch == '|' or ch == ';':
                segments.append(''.join(current))
                current = []
                i += 1
                continue

        current.append(ch)
        i += 1

    if current:
        segments.append(''.join(current))

    return segments
