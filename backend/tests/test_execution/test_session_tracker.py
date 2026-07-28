"""SessionTracker 单元测试 — 轻量会话跟踪器"""

import pytest
from app.memory.session_tracker import SessionTracker, AccessType


class TestSessionTracker:
    def test_initial_state_is_empty(self):
        st = SessionTracker()
        assert st.is_empty()
        assert st.to_prompt_section() == ""

    def test_record_file_read(self):
        st = SessionTracker()
        st.record_file_access("backend/app/foo.py", AccessType.READ, step=1)
        section = st.to_prompt_section()
        assert "foo.py" in section
        assert "read" in section.lower() or "Files read" in section

    def test_record_file_write(self):
        st = SessionTracker()
        st.record_file_access("backend/app/bar.py", AccessType.WRITE, step=2)
        section = st.to_prompt_section()
        assert "bar.py" in section
        assert "modified" in section.lower() or "Files modified" in section

    def test_record_tool_call(self):
        st = SessionTracker()
        st.record_tool_call("grep", step=3)
        st.record_tool_call("grep", step=5)
        st.record_tool_call("edit", step=6)
        summary = st.tool_call_summary
        assert summary["grep"] == 2
        assert summary["edit"] == 1

    def test_duplicate_file_access_merges(self):
        """同一文件多次读取，只保留最新步骤号"""
        st = SessionTracker()
        st.record_file_access("foo.py", AccessType.READ, step=1)
        st.record_file_access("foo.py", AccessType.READ, step=5)
        assert len(st.read_files) == 1
        assert st.read_files["foo.py"].last_step == 5
        assert st.read_files["foo.py"].count == 2

    def test_file_write_tracked_separately_from_read(self):
        st = SessionTracker()
        st.record_file_access("foo.py", AccessType.READ, step=1)
        st.record_file_access("foo.py", AccessType.WRITE, step=3)
        assert "foo.py" in st.read_files
        assert "foo.py" in st.modified_files

    def test_prompt_section_format(self):
        st = SessionTracker()
        st.record_file_access("a.py", AccessType.READ, step=1)
        st.record_file_access("b.py", AccessType.READ, step=2)
        st.record_file_access("a.py", AccessType.WRITE, step=3)
        st.record_tool_call("grep", step=4)
        section = st.to_prompt_section()
        assert "Session Tracking" in section or "Session" in section
        assert "a.py" in section
        assert "b.py" in section

    def test_not_empty_after_recording(self):
        st = SessionTracker()
        assert st.is_empty()
        st.record_file_access("x.py", AccessType.READ, step=1)
        assert not st.is_empty()

    def test_clear_resets_all(self):
        st = SessionTracker()
        st.record_file_access("x.py", AccessType.READ, step=1)
        st.record_tool_call("grep", step=1)
        st.clear()
        assert st.is_empty()

    def test_to_dict_serialization(self):
        st = SessionTracker()
        st.record_file_access("x.py", AccessType.READ, step=1)
        st.record_tool_call("grep", step=1)
        d = st.to_dict()
        assert "read_files" in d
        assert "tool_calls" in d
        assert d["tool_calls"]["grep"] == 1
