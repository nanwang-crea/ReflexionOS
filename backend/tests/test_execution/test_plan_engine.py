from app.execution.plan_engine import Plan, PlanStep


def test_plan_step_has_content_not_id():
    step = PlanStep(content="Fix auth", status="in_progress")
    assert step.content == "Fix auth"
    assert not hasattr(step, "id")
    assert not hasattr(step, "description")


def test_plan_current_step_derived_from_status():
    plan = Plan(
        goal="Fix bug",
        steps=[
            PlanStep(content="Analyze", status="completed", findings="Found bug"),
            PlanStep(content="Fix", status="in_progress"),
            PlanStep(content="Test", status="pending"),
        ],
    )
    assert plan.current_step is not None
    assert plan.current_step.content == "Fix"
    assert not hasattr(plan, "current_step_index")


def test_plan_replace_from():
    plan = Plan(
        goal="Fix bug",
        steps=[
            PlanStep(content="Analyze", status="completed", findings="Found bug"),
            PlanStep(content="Fix", status="in_progress"),
        ],
    )
    new_steps = [
        PlanStep(content="Analyze", status="completed", findings="Found bug"),
        PlanStep(content="Fix", status="completed", findings="Fixed"),
        PlanStep(content="Test", status="in_progress"),
    ]
    changes = plan.replace_from(new_steps)
    assert changes["just_completed"] == ["Fix"]
    assert changes["just_started"] == "Test"
    assert plan.current_step.content == "Test"
    assert plan.steps[0].findings == "Found bug"


def test_plan_replace_from_updates_goal():
    plan = Plan(goal="Old goal", steps=[PlanStep(content="S1", status="pending")])
    plan.replace_from([PlanStep(content="S1", status="pending")], goal="New goal")
    assert plan.goal == "New goal"


def test_plan_is_complete():
    plan = Plan(
        goal="Done",
        steps=[
            PlanStep(content="A", status="completed"),
            PlanStep(content="B", status="completed"),
        ],
    )
    assert plan.is_complete is True


def test_plan_no_in_progress_means_no_current_step():
    plan = Plan(
        goal="Test",
        steps=[
            PlanStep(content="A", status="completed"),
            PlanStep(content="B", status="pending"),
        ],
    )
    assert plan.current_step is None


def test_plan_render_to_markdown_new_format():
    plan = Plan(
        goal="Fix auth",
        steps=[
            PlanStep(content="Analyze", status="completed", findings="Found bug"),
            PlanStep(content="Fix", status="in_progress"),
        ],
    )
    md = plan.render_to_markdown()
    assert "goal: Fix auth" in md
    assert "[completed] Analyze" in md
    assert "[in_progress] Fix" in md
    assert "findings: Found bug" in md


def test_plan_parse_from_markdown_new_format():
    md = """# Execution Plan
goal: Fix auth

## Steps
- [completed] Analyze
  findings: Found bug
- [in_progress] Fix
- [pending] Test
"""
    plan = Plan.parse_from_markdown(md)
    assert plan.goal == "Fix auth"
    assert len(plan.steps) == 3
    assert plan.steps[0].content == "Analyze"
    assert plan.steps[0].status == "completed"
    assert plan.steps[0].findings == "Found bug"
    assert plan.steps[1].content == "Fix"
    assert plan.steps[1].status == "in_progress"
    assert plan.current_step.content == "Fix"


def test_plan_to_dict():
    plan = Plan(
        goal="Test",
        steps=[PlanStep(content="S1", status="pending")],
    )
    d = plan.to_dict()
    assert d["goal"] == "Test"
    assert len(d["steps"]) == 1
    assert d["steps"][0]["content"] == "S1"
    assert "current_step_index" not in d


def test_plan_completed_findings():
    plan = Plan(
        goal="Test",
        steps=[
            PlanStep(content="A", status="completed", findings="Found X"),
            PlanStep(content="B", status="in_progress"),
        ],
    )
    assert plan.completed_findings() == ["Found X"]




def test_plan_replace_from_auto_recovers_dropped_completed_steps():
    plan = Plan(
        goal="Test",
        steps=[
            PlanStep(content="A", status="completed", findings="Done"),
            PlanStep(content="B", status="in_progress"),
        ],
    )
    changes = plan.replace_from(
        [
            PlanStep(content="B", status="completed", findings="Done"),
        ]
    )
    # Completed step "A" should be auto-recovered, not rejected
    assert len(plan.steps) == 2
    assert plan.steps[0].content == "A"
    assert plan.steps[0].status == "completed"
    assert plan.steps[1].content == "B"
    assert plan.steps[1].status == "completed"
    assert changes["just_completed"] == ["B"]
