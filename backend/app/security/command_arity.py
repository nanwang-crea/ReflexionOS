import shlex

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
    """Extract prefix rules for each segment of a chained shell command.

    Splits the command by |, &&, ||, ; respecting basic quoting,
    then generates a prefix rule for each segment.
    This ensures that ``trust_and_allow`` on ``cd /path && python3 -c "..."``
    produces rules [``cd *``, ``python3 *``] so that ``python3 -c "..."``
    alone is also trusted in future calls.
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
    """Split a shell command by |, &&, ||, ; respecting basic quoting."""
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
