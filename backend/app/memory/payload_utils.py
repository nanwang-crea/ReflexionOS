from __future__ import annotations

import json


def as_payload_dict(payload_json: object) -> dict:
    if isinstance(payload_json, dict):
        return payload_json
    if isinstance(payload_json, str):
        try:
            parsed = json.loads(payload_json)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
