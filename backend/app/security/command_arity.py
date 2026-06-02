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
