from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PlanStep:
    content: str
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    findings: str = ""

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "status": self.status,
            "findings": self.findings,
        }


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def current_step(self) -> PlanStep | None:
        for s in self.steps:
            if s.status == "in_progress":
                return s
        return None

    @property
    def is_complete(self) -> bool:
        return bool(self.steps) and all(s.status == "completed" for s in self.steps)

    def replace_from(self, new_steps: list[PlanStep], goal: str | None = None) -> dict:
        old_completed = {s.content for s in self.steps if s.status == "completed"}
        old_in_progress = next(
            (s.content for s in self.steps if s.status == "in_progress"), None
        )
        self.steps = new_steps
        if goal is not None:
            self.goal = goal
        just_completed = [
            s.content for s in new_steps
            if s.status == "completed" and s.content not in old_completed
        ]
        just_started = None
        for s in new_steps:
            if s.status == "in_progress" and s.content != old_in_progress:
                just_started = s.content
                break
        return {
            "just_completed": just_completed,
            "just_started": just_started,
        }

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
            lines.append(f"{mark} {s.content}")
            if s.status == "completed" and s.findings:
                lines.append(f"  → {s.findings}")
        return "\n".join(lines)

    def render_to_markdown(self) -> str:
        lines = ["# Execution Plan", f"goal: {self.goal}", "", "## Steps"]
        for s in self.steps:
            lines.append(f"- [{s.status}] {s.content}")
            if s.findings:
                lines.append(f"  findings: {s.findings}")
        return "\n".join(lines)

    @classmethod
    def parse_from_markdown(cls, text: str) -> Plan:
        goal = ""
        steps: list[PlanStep] = []
        for line in text.splitlines():
            line = line.rstrip()
            if line.startswith("goal:"):
                goal = line[len("goal:"):].strip()
                continue
            step_match = re.match(r"^-\s*\[(\w+)\]\s*(.+)$", line)
            if step_match:
                status = step_match.group(1)
                content = step_match.group(2).strip()
                steps.append(PlanStep(content=content, status=status))
                continue
            findings_match = re.match(r"^\s+findings:\s*(.+)$", line)
            if findings_match and steps:
                steps[-1].findings = findings_match.group(1).strip()
        return cls(goal=goal, steps=steps)

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
        }
