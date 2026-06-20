"""Tests for OrchestratorSettings configuration."""

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.settings import AppSettings, ConfigManager, OrchestratorSettings


class TestOrchestratorSettings:
    def test_default_values(self):
        settings = OrchestratorSettings()
        assert settings.max_workers == 4
        assert settings.max_concurrent_workers == 3
        assert settings.enabled is True

    def test_custom_values(self):
        settings = OrchestratorSettings(max_workers=8, max_concurrent_workers=5, enabled=False)
        assert settings.max_workers == 8
        assert settings.max_concurrent_workers == 5
        assert settings.enabled is False

    def test_max_workers_lower_bound(self):
        with pytest.raises(ValidationError):
            OrchestratorSettings(max_workers=0)

    def test_max_workers_upper_bound(self):
        with pytest.raises(ValidationError):
            OrchestratorSettings(max_workers=17)

    def test_max_concurrent_workers_lower_bound(self):
        with pytest.raises(ValidationError):
            OrchestratorSettings(max_concurrent_workers=0)

    def test_max_concurrent_workers_upper_bound(self):
        with pytest.raises(ValidationError):
            OrchestratorSettings(max_concurrent_workers=17)

    def test_json_round_trip(self):
        original = OrchestratorSettings(max_workers=6, max_concurrent_workers=4, enabled=False)
        json_data = original.model_dump()
        restored = OrchestratorSettings(**json_data)
        assert restored.max_workers == original.max_workers
        assert restored.max_concurrent_workers == original.max_concurrent_workers
        assert restored.enabled == original.enabled


class TestAppSettingsWithOrchestrator:
    def test_app_settings_has_orchestrator_field(self):
        app = AppSettings()
        assert hasattr(app, "orchestrator")
        assert isinstance(app.orchestrator, OrchestratorSettings)

    def test_app_settings_orchestrator_default(self):
        app = AppSettings()
        assert app.orchestrator.max_workers == 4
        assert app.orchestrator.max_concurrent_workers == 3
        assert app.orchestrator.enabled is True

    def test_app_settings_json_round_trip(self):
        app = AppSettings()
        data = app.model_dump()
        assert "orchestrator" in data
        restored = AppSettings(**data)
        assert restored.orchestrator.max_workers == 4


class TestConfigManagerWithOrchestrator:
    def test_loads_orchestrator_from_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"orchestrator": {"max_workers": 8, "enabled": False}}, f)
            f.flush()
            mgr = ConfigManager(config_path=f.name)
            assert mgr.settings.orchestrator.max_workers == 8
            assert mgr.settings.orchestrator.enabled is False

    def test_save_and_reload_orchestrator(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()
            mgr = ConfigManager(config_path=f.name)
            mgr.settings.orchestrator.max_workers = 6
            mgr.save()

            mgr2 = ConfigManager(config_path=f.name)
            assert mgr2.settings.orchestrator.max_workers == 6
