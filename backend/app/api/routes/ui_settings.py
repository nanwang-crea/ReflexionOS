from fastapi import APIRouter

from app.config.settings import UISettings, config_manager

router = APIRouter(prefix="/api/ui-settings", tags=["ui-settings"])


@router.get("", response_model=UISettings)
async def get_ui_settings():
    return config_manager.settings.ui


@router.put("", response_model=UISettings)
async def update_ui_settings(ui_settings: UISettings):
    config_manager.update_ui(ui_settings)
    return config_manager.settings.ui
