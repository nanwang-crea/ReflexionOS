from __future__ import annotations


def build_seatbelt_profile(
    allowed_paths: list[str] | None = None,
    read_only_paths: list[str] | None = None,
    allow_network: bool = False,
) -> str:
    """Build a macOS Seatbelt (sandbox-exec) profile string.

    The profile uses a whitelist approach: everything is denied by default,
    then specific operations are re-allowed.

    Parameters
    ----------
    allowed_paths:
        Directories the sandboxed process may read *and* write.
    read_only_paths:
        Directories the sandboxed process may only read.
    allow_network:
        If True, allow outbound network connections; otherwise deny.
    """
    allowed_paths = allowed_paths or []
    read_only_paths = read_only_paths or []

    lines: list[str] = []

    # --- header ---
    lines.append("(version 1)")
    lines.append("(deny default)")

    # --- system binary / library reads ---
    for prefix in ("/usr", "/bin", "/sbin", "/lib", "/System", "/dev"):
        lines.append(f'(allow file-read* (subpath "{prefix}"))')

    # --- macOS temp directories ---
    lines.append('(allow file-read* file-write* (subpath "/var/folders"))')
    lines.append('(allow file-read* file-write* (subpath "/private/tmp"))')

    # --- project write paths ---
    for p in allowed_paths:
        lines.append(f'(allow file-read* file-write* (subpath "{p}"))')

    # --- read-only paths ---
    for p in read_only_paths:
        lines.append(f'(allow file-read* (subpath "{p}"))')

    # --- process execution ---
    for prefix in ("/usr", "/bin", "/sbin"):
        lines.append(f'(allow process-exec (subpath "{prefix}"))')
    lines.append("(allow process-fork)")

    # --- networking ---
    if allow_network:
        lines.append("(allow network*)")
    else:
        lines.append("(deny network*)")

    # --- misc ---
    lines.append("(allow signal)")
    lines.append("(allow sysctl-read)")

    # --- /etc for DNS / SSL certs ---
    lines.append('(allow file-read* (subpath "/etc"))')

    return "\n".join(lines)
