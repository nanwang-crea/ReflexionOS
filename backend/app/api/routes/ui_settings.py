"""
ui_settings — 前端 UI 偏好配置的查询与更新 API 路由。

UI 设置（如流程展开/自动折叠等偏好）存储在全局 config_manager 中，
本模块仅提供 GET/PUT 两个接口做读取和覆盖式更新。
"""

from fastapi import APIRouter

from app.config.settings import UISettings, config_manager

router = APIRouter(prefix="/api/ui-settings", tags=["ui-settings"])


@router.get("", response_model=UISettings)
async def get_ui_settings():
    """
    GET /api/ui-settings：获取当前的 UI 偏好配置。

    入参：无
    运行逻辑：直接读取 config_manager.settings.ui
    出参：UISettings - 当前 UI 配置（如 show_process_expanded、auto_collapse_process）
    """
    return config_manager.settings.ui


@router.put("", response_model=UISettings)
async def update_ui_settings(ui_settings: UISettings):
    """
    PUT /api/ui-settings：更新 UI 偏好配置。

    入参（Body）：ui_settings - UISettings，新的完整 UI 配置
    运行逻辑：调用 config_manager.update_ui 写入并持久化新配置
    出参：UISettings - 更新后的 UI 配置
    """
    config_manager.update_ui(ui_settings)
    return config_manager.settings.ui
