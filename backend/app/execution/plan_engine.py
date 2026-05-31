from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PlanStep:
    id: int
    description: str
    status: Literal["pending", "in_progress", "completed", "blocked", "failed", "cancelled"] = "pending"
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

    def finalize_for_completion(self):
        for step in self.steps:
            if step.status == "in_progress" or step.status == "pending":
                step.status = "completed"

    def finalize_for_failure(self):
        for step in self.steps:
            if step.status == "in_progress":
                step.status = "failed"
            elif step.status == "pending":
                step.status = "pending"

    def finalize_for_cancellation(self):
        for step in self.steps:
            if step.status == "in_progress" or step.status == "pending":
                step.status = "cancelled"

    def render_for_context(self) -> str:
        lines = [f"## 执行计划\n目标: {self.goal}", ""]
        for s in self.steps:
            mark = {
                "pending": "○",
                "in_progress": "►",
                "completed": "✓",
                "blocked": "✗",
                "failed": "✗",
                "cancelled": "○",
            }[s.status]
            lines.append(f"{mark} {s.description}")
            if s.status == "completed" and s.findings:
                lines.append(f"  → {s.findings}")
        return "\n".join(lines)

    def render_to_markdown(self) -> str:
        lines = ["# 执行计划", f"goal: {self.goal}", ""]
        lines.append("## 步骤")
        for s in self.steps:
            findings_part = f"  findings: {s.findings}" if s.findings else ""
            lines.append(f"{s.id}. [{s.status}] {s.description}")
            if findings_part:
                lines.append(findings_part)
        return "\n".join(lines)

    @classmethod
    def parse_from_markdown(cls, text: str) -> Plan:
        import re
        goal = ""
        steps: list[PlanStep] = []
        current_step_index = -1

        for line in text.splitlines():
            line = line.rstrip()
            if line.startswith("goal:"):
                goal = line[len("goal:"):].strip()
                continue

            step_match = re.match(r"^(\d+)\.\s*\[(\w+)\]\s*(.+)$", line)
            if step_match:
                step_id = int(step_match.group(1))
                status = step_match.group(2)
                description = step_match.group(3).strip()
                steps.append(PlanStep(id=step_id, description=description, status=status))
                if status == "in_progress":
                    current_step_index = len(steps) - 1
                continue

            findings_match = re.match(r"^\s+findings:\s*(.+)$", line)
            if findings_match and steps:
                steps[-1].findings = findings_match.group(1).strip()

        return cls(goal=goal, steps=steps, current_step_index=current_step_index)

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
        }
