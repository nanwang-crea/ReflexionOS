from app.execution.plan_engine import Plan, PlanStep


def test_render_to_markdown_full_plan():
    plan = Plan(
        goal="Implement X feature",
        steps=[
            PlanStep(id=1, description="Analyze plan_tool.py", status="completed", findings="plan_update_required is a toggle"),
            PlanStep(id=2, description="Modify plan_engine.py", status="in_progress"),
            PlanStep(id=3, description="Add step type detection", status="pending"),
            PlanStep(id=4, description="Test the changes", status="blocked", findings="Missing test fixture"),
        ],
        current_step_index=1,
    )
    md = plan.render_to_markdown()
    assert "goal: Implement X feature" in md
    assert "[completed] Analyze plan_tool.py" in md
    assert "[in_progress] Modify plan_engine.py" in md
    assert "[pending] Add step type detection" in md
    assert "[blocked] Test the changes" in md
    assert "findings: plan_update_required is a toggle" in md
    assert "findings: Missing test fixture" in md


def test_parse_from_markdown_round_trip():
    plan = Plan(
        goal="Implement X feature",
        steps=[
            PlanStep(id=1, description="Analyze plan_tool.py", status="completed", findings="found toggle"),
            PlanStep(id=2, description="Modify plan_engine.py", status="in_progress"),
            PlanStep(id=3, description="Test changes", status="pending"),
        ],
        current_step_index=1,
    )
    md = plan.render_to_markdown()
    restored = Plan.parse_from_markdown(md)
    assert restored.goal == plan.goal
    assert len(restored.steps) == len(plan.steps)
    assert restored.steps[0].status == "completed"
    assert restored.steps[0].findings == "found toggle"
    assert restored.steps[1].status == "in_progress"
    assert restored.steps[2].status == "pending"
    assert restored.current_step_index == 1


def test_parse_from_markdown_empty_findings():
    md = """# 执行计划
goal: Simple task

## 步骤
1. [in_progress] Do something
"""
    plan = Plan.parse_from_markdown(md)
    assert plan.goal == "Simple task"
    assert len(plan.steps) == 1
    assert plan.steps[0].status == "in_progress"
    assert plan.steps[0].findings == ""


def test_step_to_dict_includes_findings():
    step = PlanStep(id=1, description="Test", findings="important discovery")
    d = step.to_dict()
    assert d["findings"] == "important discovery"
