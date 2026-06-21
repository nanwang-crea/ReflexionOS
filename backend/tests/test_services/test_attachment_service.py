"""测试附件服务"""
import base64
from pathlib import Path
import tempfile
import pytest

from app.services.attachment_service import convert_attachments_to_content_parts
from app.models.conversation import MessageAttachment
from datetime import datetime


def test_convert_local_image_to_base64():
    """测试本地图片转换为 base64"""
    # 创建临时图片文件
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".png", delete=False) as f:
        f.write(b"fake png data")
        temp_path = f.name

    try:
        attachment = MessageAttachment(
            id="att_test123",
            type="image",
            mime_type="image/png",
            file_path=temp_path,
            file_size=13,
            created_at=datetime.now()
        )

        parts = convert_attachments_to_content_parts([attachment])

        assert len(parts) == 1
        assert parts[0]["type"] == "image_url"
        assert parts[0]["url"].startswith("data:image/png;base64,")

        # 验证 base64 解码
        base64_data = parts[0]["url"].split(",")[1]
        decoded = base64.b64decode(base64_data)
        assert decoded == b"fake png data"
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_convert_external_url():
    """测试外部 URL 直接使用"""
    attachment = MessageAttachment(
        id="att_external",
        type="image",
        mime_type="image/jpeg",
        file_path="https://example.com/image.jpg",
        file_size=12345,
        created_at=datetime.now()
    )

    parts = convert_attachments_to_content_parts([attachment])

    assert len(parts) == 1
    assert parts[0]["type"] == "image_url"
    assert parts[0]["url"] == "https://example.com/image.jpg"


def test_skip_nonexistent_file():
    """测试跳过不存在的文件"""
    attachment = MessageAttachment(
        id="att_missing",
        type="image",
        mime_type="image/png",
        file_path="/nonexistent/path/image.png",
        file_size=0,
        created_at=datetime.now()
    )

    parts = convert_attachments_to_content_parts([attachment])

    # 应该跳过不存在的文件
    assert len(parts) == 0


def test_skip_non_image_attachment():
    """测试跳过非图片附件"""
    attachment = MessageAttachment(
        id="att_doc",
        type="file",
        mime_type="application/pdf",
        file_path="/some/document.pdf",
        file_size=1000,
        created_at=datetime.now()
    )

    parts = convert_attachments_to_content_parts([attachment])

    # 应该跳过非图片附件
    assert len(parts) == 0


def test_skip_images_when_vision_not_supported():
    """测试当模型不支持 vision 时跳过图片"""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".png", delete=False) as f:
        f.write(b"fake png data")
        temp_path = f.name

    try:
        attachment = MessageAttachment(
            id="att_test",
            type="image",
            mime_type="image/png",
            file_path=temp_path,
            file_size=13,
            created_at=datetime.now()
        )

        # supports_vision = False 应该跳过图片
        parts = convert_attachments_to_content_parts([attachment], supports_vision=False)
        assert len(parts) == 0

        # supports_vision = True 应该转换图片
        parts = convert_attachments_to_content_parts([attachment], supports_vision=True)
        assert len(parts) == 1

        # supports_vision = None 应该转换图片（向后兼容）
        parts = convert_attachments_to_content_parts([attachment], supports_vision=None)
        assert len(parts) == 1
    finally:
        Path(temp_path).unlink(missing_ok=True)
