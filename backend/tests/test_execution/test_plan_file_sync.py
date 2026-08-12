import os
import tempfile

import pytest

from app.execution.plan_engine import Plan, PlanStep
from app.execution.plan_file_sync import PlanFileSync


def test_write_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(
            goal="Test goal",
            steps=[PlanStep(content="Step 1", status="in_progress")],
        )
        path = sync.write(plan, session_id="sess-123")
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert "goal: Test goal" in content


def test_read_recovers_plan():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(
            goal="Test goal",
            steps=[
                PlanStep(content="Step 1", status="completed", findings="done"),
                PlanStep(content="Step 2", status="in_progress"),
            ],
        )
        path = sync.write(plan, session_id="sess-456")
        recovered = sync.read(path)
        assert recovered is not None
        assert recovered.goal == "Test goal"
        assert len(recovered.steps) == 2
        assert recovered.steps[0].status == "completed"


def test_delete_removes_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(goal="Test", steps=[PlanStep(content="S1", status="in_progress")])
        path = sync.write(plan, session_id="sess-del")
        assert os.path.exists(path)
        sync.delete(path)
        assert not os.path.exists(path)


def test_find_recovery_plan():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(
            goal="Recover me", steps=[PlanStep(content="S1", status="in_progress")]
        )
        sync.write(plan, session_id="sess-recover")
        found = sync.find_recovery_plan()
        assert found is not None
        assert "sess-recover" in found


def test_find_recovery_plan_no_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        assert sync.find_recovery_plan() is None


def test_sync_updates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(
            goal="Test",
            steps=[
                PlanStep(content="S1", status="in_progress"),
                PlanStep(content="S2", status="pending"),
            ],
        )
        path = sync.write(plan, session_id="sess-sync")
        plan.replace_from(
            [
                PlanStep(content="S1", status="completed", findings="completed step 1"),
                PlanStep(content="S2", status="in_progress"),
            ]
        )
        sync.sync(plan, path)
        recovered = sync.read(path)
        assert recovered is not None
        assert recovered.steps[0].status == "completed"
        assert recovered.steps[1].status == "in_progress"


def test_delete_rejects_path_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        with pytest.raises(ValueError, match="路径超出计划目录"):
            sync.delete("/etc/passwd")


def test_delete_rejects_relative_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        with pytest.raises(ValueError, match="路径超出计划目录"):
            sync.delete(os.path.join(tmpdir, "..", "..", "etc", "passwd"))


def test_sync_rejects_path_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(goal="Test", steps=[PlanStep(content="S1", status="in_progress")])
        with pytest.raises(ValueError, match="路径超出计划目录"):
            sync.sync(plan, "/tmp/evil.md")


def test_session_id_used_as_filename():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(goal="Test", steps=[PlanStep(content="S1", status="in_progress")])
        path = sync.write(plan, session_id="sess-abc123")
        assert os.path.exists(path)
        assert os.path.basename(path) == "sess-abc123.md"
        assert os.path.dirname(path) == tmpdir
