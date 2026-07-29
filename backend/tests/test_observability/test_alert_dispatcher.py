import pytest

from app.config.settings import MonitoringAlertSettings
from app.models.monitoring import MonitoringAlertState, MonitoringAlertStatusResponse
from app.observability.alert_dispatcher import MonitoringAlertDispatcher
from app.services.monitoring_service import monitoring_service


class StubMonitoringService:
    def __init__(self):
        self.settings = MonitoringAlertSettings(
            enable_webhook_notifications=True,
            webhook_url="https://example.com/webhook",
            webhook_min_severity="warning",
            webhook_cooldown_seconds=300,
        )
        self.alert_status = MonitoringAlertStatusResponse(
            settings=self.settings,
            active_alerts=[
                MonitoringAlertState(
                    key="failed_request_count_warn",
                    severity="warning",
                    title="LLM 失败请求偏高",
                    current_value=3,
                    threshold_value=2,
                    description="当前窗口内失败或中断的 Provider 请求数已超过阈值。",
                )
            ],
        )

    def get_alert_settings(self):
        return self.settings

    def get_alert_status(self, *, project_id=None, window_hours=24):
        return self.alert_status


def test_alert_dispatcher_uses_default_monitoring_service():
    dispatcher = MonitoringAlertDispatcher()

    assert dispatcher.monitoring_service is monitoring_service


@pytest.mark.asyncio
async def test_alert_dispatcher_sends_new_alert_once_and_dedupes_until_state_changes():
    service = StubMonitoringService()
    sent_payloads = []

    dispatcher = MonitoringAlertDispatcher(
        monitoring_service=service,
        sender=lambda url, payload: sent_payloads.append((url, payload)),
    )

    first_count = await dispatcher.dispatch_once()
    second_count = await dispatcher.dispatch_once()

    assert first_count == 1
    assert second_count == 0
    assert len(sent_payloads) == 1
    assert sent_payloads[0][0] == "https://example.com/webhook"
    assert sent_payloads[0][1]["severity"] == "warning"
