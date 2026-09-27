"""验证依赖基线能发现间接依赖漂移、过期输入和平台条件差异。"""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "baseline_environment", Path(__file__).with_name("check-python-env.py")
)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class DependencyBaselineTests(unittest.TestCase):
    """使用临时声明文件和受控版本数据测试校验结果，不修改实际安装环境。"""

    def check_dependencies(self, requirements, locked, installed, environment=None):
        """输入依赖文本、锁文本及版本字典；在临时目录调用校验器；返回发现的问题。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "requirements.txt"
            lock = root / "requirements.lock"
            source.write_text(requirements, encoding="utf-8")
            lock.write_text(locked, encoding="utf-8")
            with patch("importlib.metadata.version", side_effect=installed.__getitem__):
                return CHECKER.validate_dependencies(source, lock, environment)

    def test_platform_markers_only_check_applicable_packages(self):
        """无参数；分别模拟 Windows/macOS 的条件依赖；无关平台的包不应被查询。"""
        requirements = 'pywin32==308; sys_platform == "win32"\n'
        locked = requirements + 'macholib==1.16.4; sys_platform == "darwin"\n'
        for platform, installed in [
            ("win32", {"pywin32": "308"}),
            ("darwin", {"macholib": "1.16.4"}),
        ]:
            with self.subTest(platform=platform):
                self.assertEqual(
                    self.check_dependencies(
                        requirements, locked, installed, {"sys_platform": platform}
                    ),
                    [],
                )

    def test_transitive_version_drift_is_rejected(self):
        """无参数；仅改变间接依赖 Starlette 的安装版本；校验必须明确指出版本偏差。"""
        errors = self.check_dependencies(
            "fastapi==0.115.6\n",
            "fastapi==0.115.6\nstarlette==0.41.3\n",
            {"fastapi": "0.115.6", "starlette": "0.42.0"},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("starlette==0.41.3", errors[0])
        self.assertIn("0.42.0", errors[0])

    def test_changed_direct_requirement_requires_lock_update(self):
        """无参数；模拟安装版本匹配旧锁但直接依赖已更新；校验必须要求重新生成锁。"""
        errors = self.check_dependencies(
            "httpx==0.28.1\n", "httpx==0.27.0\n", {"httpx": "0.27.0"}
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("requirements.lock", errors[0])
        self.assertIn("httpx==0.28.1", errors[0])

    def test_new_extras_require_lock_update(self):
        """无参数；模拟新增 standard 扩展但没有更新锁；校验必须拒绝缺失的扩展声明。"""
        errors = self.check_dependencies(
            "uvicorn[standard]==0.34.2\n",
            "uvicorn==0.34.2\n",
            {"uvicorn": "0.34.2"},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("uvicorn[standard]", errors[0])


if __name__ == "__main__":
    unittest.main()
