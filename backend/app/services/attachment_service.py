"""附件处理服务 - 将图片附件转换为 LLMContentPart"""
import base64
import logging
from pathlib import Path

from app.llm.base import LLMContentPart
from app.models.conversation import MessageAttachment

logger = logging.getLogger(__name__)


def convert_attachments_to_content_parts(
    attachments: list[MessageAttachment],
    supports_vision: bool | None = None,
) -> list[LLMContentPart]:
    """将消息附件转换为 LLM 内容部分

    Args:
        attachments: 消息附件列表
        supports_vision: 模型是否支持视觉能力 (None=未探测, True=支持, False=不支持)

    Returns:
        LLMContentPart 列表
    """
    parts = []

    for attachment in attachments:
        if attachment.type != "image":
            logger.warning(f"跳过非图片附件: {attachment.type}")
            continue

        # 如果明确不支持 vision，跳过图片
        if supports_vision is False:
            logger.warning(
                f"模型不支持视觉能力，跳过图片附件: {attachment.file_path}"
            )
            continue

        # 判断是本地文件还是外部 URL
        if attachment.file_path.startswith(("http://", "https://")):
            # 外部 URL - 直接使用
            parts.append(
                LLMContentPart(
                    type="image_url",
                    image_url={"url": attachment.file_path}
                )
            )
        else:
            # 本地文件 - 读取并转换为 base64
            try:
                file_path = Path(attachment.file_path)
                if not file_path.exists():
                    logger.error(f"图片文件不存在: {attachment.file_path}")
                    continue

                with open(file_path, "rb") as f:
                    image_data = f.read()

                # 转换为 base64
                base64_data = base64.b64encode(image_data).decode("utf-8")

                # 构建 data URL
                data_url = f"data:{attachment.mime_type};base64,{base64_data}"

                parts.append(
                    LLMContentPart(
                        type="image_url",
                        image_url={"url": data_url}
                    )
                )
            except Exception as e:
                logger.error(f"读取图片文件失败 {attachment.file_path}: {e}")
                continue

    return parts
