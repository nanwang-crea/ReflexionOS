import shlex

COMMAND_ARITY: dict[str, int] = {
    "git": 2,
    "npm": 1,
    "npm run": 2,
    "npx": 2,
    "pip": 1,
    "pip install": 2,
    "python": 1,
    "node": 1,
    "docker": 1,
    "docker compose": 2,
    "curl": 1,
    "wget": 1,
    "make": 1,
    "cargo": 1,
    "go": 1,
    "pytest": 1,
    "vitest": 1,
    "rm": 1,
}

DEFAULT_ARITY = 1


def extract_prefix_rule(command: str) -> str:
    if not command or not command.strip():
        return "*"

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    if not tokens:
        return "*"

    best_arity = DEFAULT_ARITY
    best_prefix_len = 0
    for prefix, arity in COMMAND_ARITY.items():
        prefix_tokens = prefix.split()
        prefix_len = len(prefix_tokens)
        if len(tokens) >= prefix_len and tokens[:prefix_len] == prefix_tokens:
            if prefix_len > best_prefix_len:
                best_prefix_len = prefix_len
                best_arity = arity

    prefix_tokens = tokens[:best_arity]
    return " ".join(prefix_tokens) + " *"
