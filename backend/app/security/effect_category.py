# backend/app/security/effect_category.py
import enum
import logging

logger = logging.getLogger(__name__)


class CommandAction(str, enum.Enum):
    """Action to take for a command based on its effect classification."""
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class EffectCategory(str, enum.Enum):
    """Command effect categories for security classification."""

    READ_ONLY = "read_only"           # No side effects
    WRITE_PROJECT = "write_project"   # Modifies files/dependencies within project
    WRITE_SYSTEM = "write_system"     # Modifies system state outside project
    DESTRUCTIVE = "destructive"       # Deletes/overwrites files
    ESCALATE = "escalate"             # Privilege escalation
    NETWORK_OUT = "network_out"       # Outbound network requests
    CODE_GEN = "code_gen"             # Inline code execution (cannot statically validate)
    UNKNOWN = "unknown"               # Unrecognized command


EFFECT_DANGER_LEVEL: dict[EffectCategory, int] = {
    EffectCategory.READ_ONLY: 0,
    EffectCategory.WRITE_PROJECT: 1,
    EffectCategory.CODE_GEN: 2,
    EffectCategory.UNKNOWN: 3,
    EffectCategory.NETWORK_OUT: 4,
    EffectCategory.WRITE_SYSTEM: 5,
    EffectCategory.DESTRUCTIVE: 6,
    EffectCategory.ESCALATE: 7,
}

EFFECT_ACTION_MAP: dict[EffectCategory, CommandAction] = {
    EffectCategory.READ_ONLY: CommandAction.ALLOW,
    EffectCategory.WRITE_PROJECT: CommandAction.ALLOW,
    EffectCategory.WRITE_SYSTEM: CommandAction.REQUIRE_APPROVAL,
    EffectCategory.DESTRUCTIVE: CommandAction.REQUIRE_APPROVAL,
    EffectCategory.ESCALATE: CommandAction.DENY,
    EffectCategory.NETWORK_OUT: CommandAction.REQUIRE_APPROVAL,
    EffectCategory.CODE_GEN: CommandAction.REQUIRE_APPROVAL,
    EffectCategory.UNKNOWN: CommandAction.REQUIRE_APPROVAL,
}


def most_dangerous(categories: list[EffectCategory]) -> EffectCategory:
    """Return the most dangerous EffectCategory from a list.

    Raises ValueError if the list is empty.
    """
    if not categories:
        raise ValueError("categories list must not be empty")
    return max(categories, key=lambda c: EFFECT_DANGER_LEVEL[c])
