from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.observability import ObservabilityEventCreate, subject_hash, utc_now


class ToolObservabilityContext(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    run_id: str | None = None
    project_name_snapshot: str | None = None
    session_title_snapshot: str | None = None


class RuntimeObservabilityRecorder:
    def __init__(self, collector) -> None:
        self.collector = collector

    def record_runtime_event(
        self,
        *,
        context: ToolObservabilityContext,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        if event_type == "tool:start":
            self._record_tool_event(context=context, data=data, status="running")
            return
        if event_type == "approval:required":
            self._record_tool_event(
                context=context,
                data=data,
                status="waiting_for_approval",
            )
            self._record_approval_event(
                context=context,
                data={
                    **data,
                    "reason": (
                        data.get("approval", {}).get("summary")
                        if isinstance(data.get("approval"), dict)
                        else None
                    ),
                },
                approval_status="requested",
                actor_type="system",
            )
            return
        if event_type == "tool:result":
            self._record_tool_event(
                context=context,
                data=data,
                status="completed" if data.get("success") else "failed",
            )
            return
        if event_type == "tool:error":
            self._record_tool_event(context=context, data=data, status="failed")

    def record_approval_decision(
        self,
        *,
        context: ToolObservabilityContext,
        data: dict[str, Any],
        approval_status: str,
        actor_type: str,
        reason: str | None = None,
    ) -> None:
        payload = dict(data)
        payload["reason"] = reason
        self._record_approval_event(
            context=context,
            data=payload,
            approval_status=approval_status,
            actor_type=actor_type,
        )

    def record_tool_terminal(
        self,
        *,
        context: ToolObservabilityContext,
        data: dict[str, Any],
        status: str,
    ) -> None:
        self._record_tool_event(context=context, data=data, status=status)

    def _record_tool_event(
        self,
        *,
        context: ToolObservabilityContext,
        data: dict[str, Any],
        status: str,
    ) -> None:
        metric_id, invocation_id = self._resolve_tool_ids(context=context, data=data)
        occurred_at = self._parse_datetime(data.get("occurred_at")) or utc_now()
        tool_started_at = self._parse_datetime(data.get("tool_started_at")) or occurred_at
        execution_started_at = self._parse_datetime(data.get("execution_started_at"))
        source_run_id = context.run_id or str(data.get("run_id") or "")
        payload = {
            "invocation_id": invocation_id,
            "tool_call_id": str(data.get("tool_call_id") or ""),
            "source_run_id_hash": subject_hash("run", source_run_id) if source_run_id else None,
            "tool_name": str(data.get("tool_name") or ""),
            "turn_id": context.turn_id,
            "status": status,
            "execution_duration_ms": self._coerce_ms(data.get("execution_duration_ms")),
            "approval_wait_ms": self._coerce_ms(data.get("approval_wait_ms")),
            "total_duration_ms": self._coerce_total_duration_ms(data),
            "error_category": self._error_category(data),
            "error_message": data.get("error"),
            "terminal_reason": self._terminal_reason(status=status, data=data),
            "execution_started_at": (
                execution_started_at.isoformat()
                if execution_started_at is not None
                else (
                    tool_started_at.isoformat()
                    if status == "running"
                    else None
                )
            ),
            "project_name_snapshot": context.project_name_snapshot,
            "session_title_snapshot": context.session_title_snapshot,
        }

        if status == "waiting_for_approval":
            payload["execution_started_at"] = None

        self.collector.record(
            ObservabilityEventCreate(
                entity_type="tool_call",
                entity_id=metric_id,
                event_type=f"tool.{status}",
                payload_json={
                    key: value
                    for key, value in payload.items()
                    if value is not None or key == "execution_started_at"
                },
                subject_project_id=context.project_id,
                subject_session_id=context.session_id,
                subject_run_id=context.run_id,
                occurred_at=occurred_at,
            )
        )

    def _record_approval_event(
        self,
        *,
        context: ToolObservabilityContext,
        data: dict[str, Any],
        approval_status: str,
        actor_type: str,
    ) -> None:
        approval_id = str(data.get("approval_id") or "")
        if not approval_id:
            return

        metric_id, _ = self._resolve_tool_ids(context=context, data=data)
        occurred_at = self._parse_datetime(data.get("occurred_at")) or utc_now()
        payload = {
            "tool_call_metric_id": data.get("tool_call_metric_id") or metric_id,
            "approval_id": approval_id,
            "event_type": approval_status,
            "actor_type": actor_type,
            "reason": data.get("reason"),
        }

        self.collector.record(
            ObservabilityEventCreate(
                entity_type="approval",
                entity_id=approval_id,
                event_type=f"approval.{approval_status}",
                payload_json={key: value for key, value in payload.items() if value is not None},
                subject_project_id=context.project_id,
                subject_session_id=context.session_id,
                subject_run_id=context.run_id,
                occurred_at=occurred_at,
            )
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        return None

    @staticmethod
    def _coerce_ms(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return max(0, int(value))
        return None

    @staticmethod
    def _coerce_total_duration_ms(data: dict[str, Any]) -> int | None:
        explicit = RuntimeObservabilityRecorder._coerce_ms(data.get("total_duration_ms"))
        if explicit is not None:
            return explicit
        duration = data.get("duration")
        if isinstance(duration, (int, float)):
            return max(0, int(duration * 1000))
        return None

    @staticmethod
    def _error_category(data: dict[str, Any]) -> str | None:
        explicit = data.get("error_category")
        if isinstance(explicit, str) and explicit:
            return explicit
        error = str(data.get("error") or "")
        if not error:
            return None
        lowered = error.casefold()
        if "审批被拒绝" in error:
            return "approval_denied"
        if "缺少必需参数" in error or "parse" in lowered:
            return "input_validation"
        if "工具不存在" in error:
            return "tool_not_found"
        return "execution_error"

    @staticmethod
    def _terminal_reason(status: str, data: dict[str, Any]) -> str | None:
        explicit = data.get("terminal_reason")
        if isinstance(explicit, str) and explicit:
            return explicit
        if status == "completed":
            return "completed"
        if RuntimeObservabilityRecorder._error_category(data) == "approval_denied":
            return "denied"
        if status == "failed":
            return "failed"
        if status == "cancelled":
            return "cancelled"
        if status == "interrupted":
            return "interrupted"
        return None

    @staticmethod
    def _resolve_tool_ids(
        *,
        context: ToolObservabilityContext,
        data: dict[str, Any],
    ) -> tuple[str, str]:
        metric_id = data.get("tool_call_metric_id")
        invocation_id = data.get("invocation_id")
        if isinstance(metric_id, str) and metric_id and isinstance(invocation_id, str) and invocation_id:
            return metric_id, invocation_id

        signature = "|".join(
            [
                context.run_id or "",
                str(data.get("tool_call_id") or ""),
                str(data.get("step_number") or ""),
                str(data.get("tool_name") or ""),
            ]
        )
        digest = hashlib.sha256(signature.encode()).hexdigest()[:12]
        return (
            f"tool-metric-{digest}",
            f"tool-invocation-{digest}",
        )
