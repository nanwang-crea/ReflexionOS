from __future__ import annotations


def build_seatbelt_profile(
    allowed_paths: list[str] | None = None,
    read_only_paths: list[str] | None = None,
    allow_network: bool = False,
    level: str = "dev",  # "strict" | "dev" | "permissive"
) -> str:
    allowed_paths = allowed_paths or []
    read_only_paths = read_only_paths or []

    lines: list[str] = []

    # --- header ---
    lines.append("(version 1)")
    lines.append("(deny default)")

    # ========================
    # 基础系统（必须）
    # ========================
    for prefix in ("/usr", "/bin", "/sbin", "/lib", "/System", "/dev", "/etc"):
        lines.append(f'(allow file-read* (subpath "{prefix}"))')

    # dyld / 可执行映射（否则 Python / git 会崩）
    lines.append("(allow file-map-executable)")

    # ========================
    # 临时目录
    # ========================
    for p in ("/tmp", "/private/tmp", "/var/folders"):
        lines.append(f'(allow file-read* file-write* (subpath "{p}"))')

    # ========================
    # 用户目录（dev 以上必须）
    # ========================
    if level in ("dev", "permissive"):
        lines.append('(allow file-read* (subpath "/Users"))')
        lines.append('(allow file-write* (subpath "/Users"))')
        lines.append('(allow process-exec (subpath "/Users"))')

    # ========================
    # 项目路径
    # ========================
    for p in allowed_paths:
        lines.append(f'(allow file-read* file-write* (subpath "{p}"))')

    for p in read_only_paths:
        lines.append(f'(allow file-read* (subpath "{p}"))')

    # ========================
    # 进程执行
    # ========================
    if level == "strict":
        for prefix in ("/usr", "/bin", "/sbin"):
            lines.append(f'(allow process-exec (subpath "{prefix}"))')
    else:
        # dev / permissive：必须放开，否则 venv / git / python 会挂
        lines.append("(allow process-exec)")

    lines.append("(allow process-fork)")
    lines.append("(allow process-info*)")  # 防止部分程序 abort

    # ========================
    # IPC（关键）
    # ========================
    if level in ("dev", "permissive"):
        lines.append("(allow ipc*)")
        lines.append("(allow mach*)")  # ⚠️ macOS 核心，否则 git 直接 SIGABRT

    # ========================
    # 网络
    # ========================
    if allow_network:
        lines.append("(allow network*)")
    else:
        lines.append("(deny network*)")

    # ========================
    # 其他
    # ========================
    lines.append("(allow signal)")
    lines.append("(allow sysctl-read)")

    return "\n".join(lines)
