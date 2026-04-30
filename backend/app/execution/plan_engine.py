from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PlanStep:
    id: int
    description: str
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    findings: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "findings": self.findings,
        }


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    current_step_index: int = -1

    @property
    def current_step(self) -> PlanStep | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def is_complete(self) -> bool:
        return bool(self.steps) and all(s.status == "completed" for s in self.steps)

    def start(self):
        if not self.steps:
            return
        self.current_step_index = 0
        self.steps[0].status = "in_progress"

    def advance(self, findings: str = ""):
        step = self.current_step
        if step:
            step.status = "completed"
            step.findings = findings
        self.current_step_index += 1
        if self.current_step_index < len(self.steps):
            self.steps[self.current_step_index].status = "in_progress"

    def block(self, reason: str):
        step = self.current_step
        if step:
            step.status = "blocked"
            step.findings = reason

    def adjust_remaining(self, remaining_descriptions: list[str]):
        """Replace all pending/blocked steps after current with new descriptions."""
        # Keep completed and in_progress steps, replace the rest.
        kept = [s for s in self.steps if s.status in ("completed", "in_progress")]
        next_id = (max(s.id for s in kept) + 1) if kept else 1
        new_steps = [
            PlanStep(id=next_id + i, description=desc)
            for i, desc in enumerate(remaining_descriptions)
        ]
        self.steps = kept + new_steps

    def completed_findings(self) -> list[str]:
        return [s.findings for s in self.steps if s.status == "completed" and s.findings]

    def render_for_context(self) -> str:
        lines = [f"## 执行计划\n目标: {self.goal}", ""]
        for s in self.steps:
            mark = {
                "pending": "○",
                "in_progress": "►",
                "completed": "✓",
                "blocked": "✗",
            }[s.status]
            lines.append(f"{mark} {s.description}")
            if s.status == "completed" and s.findings:
                lines.append(f"  → {s.findings}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
        }
