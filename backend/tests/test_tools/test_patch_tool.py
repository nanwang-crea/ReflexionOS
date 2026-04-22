import os
import tempfile
from pathlib import Path

import pytest

from app.security.path_security import PathSecurity
from app.tools.patch_tool import PatchTool


class TestPatchTool:
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)
    
    @pytest.fixture
    def patch_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return PatchTool(security)
    
    @pytest.mark.asyncio
    async def test_apply_simple_patch(self, patch_tool, temp_dir):
        """测试简单的 Patch 应用"""
        # 创建测试文件
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")
        
        # 创建 patch - 使用绝对路径
        patch = f"""--- a/{test_file}
+++ b/{test_file}
@@ -1,2 +1,2 @@
 def hello():
-    print('hello')
+    print('hello world')
"""
        
        result = await patch_tool.execute({"patch": patch})
        
        assert result.success is True
        assert "hello world" in test_file.read_text()
    
    @pytest.mark.asyncio
    async def test_create_new_file(self, patch_tool, temp_dir):
        """测试创建新文件"""
        new_file = Path(temp_dir) / "new_file.py"
        
        patch = f"""--- /dev/null
+++ b/{new_file}
@@ -0,0 +1,3 @@
+def new_function():
+    return "created"
+"""
        
        result = await patch_tool.execute({"patch": patch})
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_patch_with_context(self, patch_tool, temp_dir):
        """测试带上下文的 Patch"""
        test_file = Path(temp_dir) / "example.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\n")
        
        patch = f"""--- a/{test_file}
+++ b/{test_file}
@@ -2,2 +2,2 @@
 line2
-line3
+line3_modified
 line4
"""
        
        result = await patch_tool.execute({"patch": patch})
        
        assert result.success is True
        content = test_file.read_text()
        assert "line3_modified" in content
    
    @pytest.mark.asyncio
    async def test_patch_preserves_other_lines(self, patch_tool, temp_dir):
        """测试 Patch 不影响其他行"""
        test_file = Path(temp_dir) / "preserve.py"
        original_content = "line1\nline2\nline3\nline4\nline5\n"
        test_file.write_text(original_content)
        
        patch = f"""--- a/{test_file}
+++ b/{test_file}
@@ -2,1 +2,1 @@
-line2
+line2_modified
"""
        
        result = await patch_tool.execute({"patch": patch})
        
        assert result.success is True
        content = test_file.read_text()
        assert "line1" in content
        assert "line2_modified" in content
        assert "line3" in content
        assert "line4" in content
        assert "line5" in content
    
    @pytest.mark.asyncio
    async def test_patch_missing_parameter(self, patch_tool):
        """测试缺少参数"""
        result = await patch_tool.execute({})
        
        assert result.success is False
        assert "缺少 patch 参数" in result.error
    
    @pytest.mark.asyncio
    async def test_patch_invalid_format(self, patch_tool):
        """测试无效的 Diff 格式"""
        result = await patch_tool.execute({"patch": "invalid diff content"})
        
        assert result.success is False
        assert "无法解析" in result.error
