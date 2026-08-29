"""
载荷（payload）解析工具模块。

数据库中存储的 payload 字段可能是已解析的 dict，也可能是原始 JSON 字符串，
本模块统一将其归一化为 dict，供记忆相关模块（工作记忆、召回等）安全读取。
"""

from __future__ import annotations

import json


def as_payload_dict(payload_json: object) -> dict:
    """
    将任意来源的 payload 归一化为 dict。

    参数：
        payload_json: 待解析的载荷，可能是 dict、JSON 字符串，或其他类型（如 None）。
    逻辑：
        - 若已经是 dict，直接返回；
        - 若是字符串，尝试用 json.loads 解析，解析失败或结果不是 dict 则返回空字典；
        - 其他类型一律视为无效载荷，返回空字典。
    返回：
        解析得到的 dict；无法解析时返回空字典 {}（不会返回 None，方便调用方直接取值）。
    """
    if isinstance(payload_json, dict):
        return payload_json
    if isinstance(payload_json, str):
        try:
            parsed = json.loads(payload_json)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
