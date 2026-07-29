from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime

from app.services.monitoring_service import (
    MonitoringService,
)
from app.services.monitoring_service import (
    monitoring_service as default_monitoring_service,
)

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"warning": 1, "critical": 2}


class MonitoringAlertDispatcher:
    def __init__(
        self,
        *,
        monitoring_service: MonitoringService | None = None,
        sender=None,
    ) -> None:
        self.monitoring_service = monitoring_service or default_monitoring_service
        self.sender = sender or self._send_webhook
        self._task: asyncio.Task | None = None
        self._last_sent_keys: set[str] = set()
        self._last_sent_at_by_key: dict[str, datetime] = {}

    def start_background_tasks(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="monitoring-alert-dispatch")

    async def stop_background_tasks(self) -> None:
        task = self._task
        if task is None:
            return
        self._task = None
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def dispatch_once(self) -> int:
        settings = self.monitoring_service.get_alert_settings()
        if not settings.enable_webhook_notifications or not settings.webhook_url:
            return 0

        alert_status = self.monitoring_service.get_alert_status(window_hours=24)
        active_alerts = [
            alert
            for alert in alert_status.active_alerts
            if _SEVERITY_RANK.get(alert.severity, 0)
            >= _SEVERITY_RANK.get(settings.webhook_min_severity, 2)
        ]

        now = datetime.now(UTC)
        cooldown_seconds = settings.webhook_cooldown_seconds
        sent_count = 0
        current_keys = {f"{alert.key}:{alert.severity}" for alert in active_alerts}

        for alert in active_alerts:
            signature = f"{alert.key}:{alert.severity}"
            last_sent_at = self._last_sent_at_by_key.get(signature)
            if (
                signature in self._last_sent_keys
                and cooldown_seconds > 0
                and last_sent_at is not None
                and (now - last_sent_at).total_seconds() < cooldown_seconds
            ):
                continue

            payload = {
                "type": "monitoring_alert",
                "sent_at": now.isoformat(),
                "severity": alert.severity,
                "key": alert.key,
                "title": alert.title,
                "description": alert.description,
                "current_value": alert.current_value,
                "threshold_value": alert.threshold_value,
            }
            self.sender(settings.webhook_url, payload)
            self._last_sent_at_by_key[signature] = now
            sent_count += 1

        self._last_sent_keys = current_keys
        self._last_sent_at_by_key = {
            key: value
            for key, value in self._last_sent_at_by_key.items()
            if key in current_keys
        }
        return sent_count

    async def _loop(self) -> None:
        while True:
            try:
                settings = self.monitoring_service.get_alert_settings()
                await self.dispatch_once()
                await asyncio.sleep(max(15, settings.poll_interval_seconds))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("monitoring webhook dispatch failed", exc_info=True)
                await asyncio.sleep(60)

    @staticmethod
    def _send_webhook(url: str, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status >= 400:
                    raise RuntimeError(f"webhook responded with status {response.status}")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"webhook dispatch failed: {exc}") from exc
