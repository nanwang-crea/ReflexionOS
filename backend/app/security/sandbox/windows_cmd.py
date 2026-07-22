# Windows cmd 内部命令判定与降级执行。
#
# 定义 CMD_INTERNAL_COMMANDS 清单（无独立 .exe 的 cmd 内部命令）
# 和 is_cmd_internal_command 判定函数，供 shell_tool 在 Windows 上
# 将 argv 模式降级为 shell 模式（cmd.exe /c）执行。
#
# 有独立 .exe 的命令（find/findstr/robocopy/where/tasklist 等）不在清单中，
# argv 模式能直接 CreateProcess 执行，不需要降级。

from __future__ import annotations

CMD_INTERNAL_COMMANDS: frozenset[str] = frozenset({
    # 控制流 / 脚本
    "if", "for", "call", "goto", "shift", "setlocal", "endlocal",
    "rem", "pause", "exit", "start",
    # 目录
    "mkdir", "md", "rmdir", "rd", "pushd", "popd", "mklink",
    # 文件操作
    "copy", "xcopy", "move", "ren", "rename", "del", "erase", "type",
    # 显示 / 环境
    "echo", "set", "dir", "cd", "chdir", "cls", "ver", "vol",
    "prompt", "title", "color", "path", "assoc", "ftype",
    "date", "time", "break", "verify", "dpath", "keys", "chcp",
})

# 明确排除（System32 下有独立 .exe，argv 模式能跑，不应降级）：
# find, findstr, robocopy, where, tasklist, taskkill, reg, sc, net,
# wmic, ping, ipconfig 等


def is_cmd_internal_command(name: str | None) -> bool:
    """判断命令名是否为 cmd.exe 内部命令（无独立 .exe）。

    函数名：is_cmd_internal_command
    入参：
      - name (str | None): 命令名（argv[0]）
    功能：检查命令名是否在 CMD_INTERNAL_COMMANDS 清单中。
    运行逻辑：空值或不在清单中返回 False，否则返回 True。
    出参：bool - 是否为 cmd 内部命令
    """
    if not name:
        return False
    return name.lower() in CMD_INTERNAL_COMMANDS
