"""附件处理服务 - 统一管理附件的存储、查询和转换"""
import base64
import logging
from datetime import datetime
from pathlib import Path

from app.llm.base import LLMContentPart
from app.models.conversation import MessageAttachment

logger = logging.getLogger(__name__)

MAX_MESSAGE_ATTACHMENTS = 4


class AttachmentService:
    """附件服务 - 统一管理附件文件的查找、元数据构建等"""

    def __init__(self, upload_base_dir: Path | str = "storage/uploads"):
        """初始化附件服务

        Args:
            upload_base_dir: 上传文件的基础目录
        """
        self.upload_base_dir = Path(upload_base_dir)

    def get_session_upload_dir(self, session_id: str) -> Path:
        """获取会话的上传目录

        Args:
            session_id: 会话 ID

        Returns:
            会话的上传目录路径
        """
        return self.upload_base_dir / session_id

    def find_attachment_file(self, session_id: str, attachment_id: str) -> Path | None:
        """根据 attachment_id 查找文件路径

        Args:
            session_id: 会话 ID
            attachment_id: 附件 ID (格式: att_xxxxx)

        Returns:
            文件路径，如果不存在则返回 None
        """
        upload_dir = self.get_session_upload_dir(session_id)
        if not upload_dir.exists():
            logger.warning(f"上传目录不存在: {upload_dir}")
            return None

        # 从 attachment_id 提取 file_id
        file_id = attachment_id.replace("att_", "")

        # 查找匹配的文件
        matching_files = list(upload_dir.glob(f"*_{file_id}.*"))

        if not matching_files:
            logger.warning(f"未找到附件文件: session={session_id}, attachment_id={attachment_id}")
            return None

        if len(matching_files) > 1:
            logger.warning(f"找到多个匹配文件: {matching_files}, 使用第一个")

        return matching_files[0]

    def infer_mime_type(self, file_path: Path) -> str:
        """根据文件扩展名推断 MIME 类型

        Args:
            file_path: 文件路径

        Returns:
            MIME 类型字符串
        """
        ext = file_path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_map.get(ext, "image/png")

    def build_attachment_url(self, session_id: str, attachment_id: str) -> str:
        return f"/api/sessions/{session_id}/attachments/{attachment_id}"

    def build_attachment_metadata(
        self,
        session_id: str,
        attachment_id: str
    ) -> MessageAttachment | None:
        """构建附件元数据对象

        Args:
            session_id: 会话 ID
            attachment_id: 附件 ID

        Returns:
            MessageAttachment 对象，如果文件不存在则返回 None
        """
        file_path = self.find_attachment_file(session_id, attachment_id)
        if not file_path:
            return None

        try:
            mime_type = self.infer_mime_type(file_path)
            file_size = file_path.stat().st_size
            file_ctime = datetime.fromtimestamp(file_path.stat().st_ctime)

            return MessageAttachment(
                id=attachment_id,
                type="image",
                mime_type=mime_type,
                file_path=str(file_path),
                file_size=file_size,
                created_at=file_ctime,
                url=self.build_attachment_url(session_id, attachment_id),
            )
        except Exception as e:
            logger.error(f"构建附件元数据失败: {e}", exc_info=True)
            return None

    def build_attachments_for_message(
        self,
        session_id: str,
        attachment_ids: list[str]
    ) -> list[dict]:
        """为消息构建附件列表（用于事件 payload）

        Args:
            session_id: 会话 ID
            attachment_ids: 附件 ID 列表

        Returns:
            附件元数据的字典列表，用于 JSON 序列化
        """
        attachments_data = []

        for att_id in attachment_ids:
            attachment = self.build_attachment_metadata(session_id, att_id)
            if attachment:
                attachments_data.append(attachment.model_dump(mode="json"))
                logger.debug(f"添加附件元数据: id={att_id}")
            else:
                logger.warning(f"跳过无效附件: id={att_id}")

        return attachments_data

    def cleanup_session_attachments(self, session_id: str) -> int:
        """清理会话的所有附件文件

        Args:
            session_id: 会话 ID

        Returns:
            删除的文件数量
        """
        session_dir = self.get_session_upload_dir(session_id)

        if not session_dir.exists():
            logger.debug(f"会话上传目录不存在，无需清理: {session_dir}")
            return 0

        deleted_count = 0
        try:
            # 删除目录下的所有文件
            for file_path in session_dir.iterdir():
                if file_path.is_file():
                    file_path.unlink()
                    deleted_count += 1
                    logger.debug(f"删除附件文件: {file_path}")

            # 删除空目录
            session_dir.rmdir()
            logger.info(f"清理会话附件完成: session={session_id}, 删除 {deleted_count} 个文件")
        except Exception as e:
            logger.error(f"清理会话附件失败: session={session_id}, error={e}", exc_info=True)

        return deleted_count


# 全局单例
_attachment_service = AttachmentService()


def get_attachment_service() -> AttachmentService:
    """获取附件服务单例"""
    return _attachment_service


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
