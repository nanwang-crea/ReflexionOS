import os
import tempfile
from app.execution.plan_engine import Plan, PlanStep
from app.execution.plan_file_sync import PlanFileSync


def test_write_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(
            goal="Test goal",
            steps=[PlanStep(id=1, description="Step 1", status="in_progress")],
            current_step_index=0,
        )
        path = sync.write(plan, slug="test-goal")
        assert os.path.exists(path)
        content = open(path).read()
        assert "goal: Test goal" in content


def test_read_recovers_plan():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(
            goal="Test goal",
            steps=[
                PlanStep(id=1, description="Step 1", status="completed", findings="done"),
                PlanStep(id=2, description="Step 2", status="in_progress"),
            ],
            current_step_index=1,
        )
        path = sync.write(plan, slug="test-goal")
        recovered = sync.read(path)
        assert recovered is not None
        assert recovered.goal == "Test goal"
        assert len(recovered.steps) == 2
        assert recovered.steps[0].status == "completed"


def test_delete_removes_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(goal="Test", steps=[PlanStep(id=1, description="S1", status="in_progress")], current_step_index=0)
        path = sync.write(plan, slug="test")
        assert os.path.exists(path)
        sync.delete(path)
        assert not os.path.exists(path)


def test_find_recovery_plan():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(goal="Recover me", steps=[PlanStep(id=1, description="S1", status="in_progress")], current_step_index=0)
        sync.write(plan, slug="recover-test")
        found = sync.find_recovery_plan()
        assert found is not None
        assert "recover-test" in found


def test_find_recovery_plan_no_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        assert sync.find_recovery_plan() is None


def test_sync_updates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(goal="Test", steps=[PlanStep(id=1, description="S1", status="in_progress"), PlanStep(id=2, description="S2", status="pending")], current_step_index=0)
        path = sync.write(plan, slug="test")
        plan.advance(findings="completed step 1")
        sync.sync(plan, path)
        recovered = sync.read(path)
        assert recovered is not None
        assert recovered.steps[0].status == "completed"
        assert recovered.steps[1].status == "in_progress"
