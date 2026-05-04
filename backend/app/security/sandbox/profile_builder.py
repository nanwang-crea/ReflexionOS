from __future__ import annotations

from abc import ABC, abstractmethod

from app.security.sandbox.sandbox_policy import SandboxPolicy


class ProfileBuilder(ABC):
    """Cross-platform sandbox profile builder base class.

    Subclasses implement ``build()`` to produce platform-specific sandbox
    configuration.  Seatbelt returns a profile string; Landlock/bwrap
    returns an argument list.
    """

    def __init__(self, policy: SandboxPolicy) -> None:
        self.policy = policy

    @abstractmethod
    def build(self) -> str | list[str]:
        """Build platform-specific sandbox configuration.

        Returns
        -------
        str
            For Seatbelt (.sb profile string).
        list[str]
            For Landlock/bwrap (argument list).
        """
        ...
