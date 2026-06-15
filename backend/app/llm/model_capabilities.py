"""模型能力检测模块"""

VISION_CAPABLE_MODELS = {
    # OpenAI
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4-vision-preview",

    # Anthropic Claude
    "claude-3-opus",
    "claude-3-sonnet",
    "claude-3-haiku",
    "claude-3-5-sonnet",
    "claude-fable-5",

    # Google Gemini
    "gemini-pro-vision",
    "gemini-1.5-pro",
    "gemini-1.5-flash",

    # 通配符模式
    "gpt-4o-*",
    "claude-3-*",
    "gemini-*-vision",
}


def supports_vision(model_name: str) -> bool:
    """检测模型是否支持视觉能力

    Args:
        model_name: 模型名称

    Returns:
        是否支持视觉
    """
    if not model_name:
        return False

    # 精确匹配
    if model_name in VISION_CAPABLE_MODELS:
        return True

    # 通配符匹配
    for pattern in VISION_CAPABLE_MODELS:
        if "*" in pattern:
            prefix = pattern.replace("*", "")
            if model_name.startswith(prefix):
                return True

    return False
