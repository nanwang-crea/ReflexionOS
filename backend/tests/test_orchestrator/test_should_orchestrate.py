"""should_orchestrate 单元测试

测试矩阵见设计文档 §5.1
"""

import pytest
from app.execution.orchestrator import should_orchestrate, OrchestratorConfig


class TestShouldOrchestrate:
    """should_orchestrate 测试用例"""

    def test_t1_normal_paragraph_not_triggered(self):
        """T1: 普通段落不触发"""
        config = OrchestratorConfig()
        assert should_orchestrate("请帮我看看这个文件有什么问题", config) is False

    def test_t2_markdown_heading_not_triggered(self):
        """T2: Markdown 标题不触发"""
        config = OrchestratorConfig()
        assert should_orchestrate("# 任务一\n## 子任务\n### 步骤", config) is False

    def test_t3_single_item_not_triggered(self):
        """T3: 单项列表不触发"""
        config = OrchestratorConfig()
        assert should_orchestrate("1. 重构 auth.py 使其支持 JWT 认证", config) is False

    def test_t4_two_or_more_items_triggered(self):
        """T4: 两项以上编号列表触发"""
        config = OrchestratorConfig()
        # 单行格式
        assert should_orchestrate("1. 重构认证模块使其支持 JWT 认证 2. 编写单元测试覆盖边界情况 3. 更新项目 README 文档", config) is True
        # 多行格式
        assert should_orchestrate("1. 重构认证模块使其支持 JWT 认证\n2. 编写单元测试覆盖边界情况\n3. 更新项目 README 文档", config) is True

    def test_t5_short_content_not_triggered(self):
        """T5: 每项少于 10 字符不触发"""
        config = OrchestratorConfig()
        assert should_orchestrate("1. 改代码\n2. 写测试\n3. 更新文档", config) is False

    def test_t6_chinese_comma_triggered(self):
        """T6: 中文顿号编号触发"""
        config = OrchestratorConfig()
        assert should_orchestrate("1、重构认证模块使其支持 OAuth\n2、添加单元测试覆盖边界情况", config) is True

    def test_t7_parenthesis_triggered(self):
        """T7: 括号编号触发"""
        config = OrchestratorConfig()
        assert should_orchestrate("1) 修复登录 bug 并添加完善的错误处理机制\n2) 编写回归测试用例覆盖所有边界情况", config) is True

    def test_t8_disable_overrides_all(self):
        """T8: disable_orchestration 优先"""
        config = OrchestratorConfig(disable_orchestration=True)
        assert should_orchestrate("1. 任务一需要完成重构 2. 任务二需要编写测试", config) is False

    def test_t9_force_overrides_all(self):
        """T9: force_orchestration 优先"""
        config = OrchestratorConfig(force_orchestration=True)
        assert should_orchestrate("随便什么内容", config) is True

    def test_t10_empty_string(self):
        """T10: 空字符串"""
        config = OrchestratorConfig()
        assert should_orchestrate("", config) is False

    def test_t11_mixed_heading_and_numbered(self):
        """T11: 混合标题+编号"""
        config = OrchestratorConfig()
        assert should_orchestrate("# 标题\n1. 子任务一需要完成认证重构\n2. 子任务二需要编写测试用例", config) is True

    def test_disable_overrides_force(self):
        """disable 优先于 force"""
        config = OrchestratorConfig(disable_orchestration=True, force_orchestration=True)
        assert should_orchestrate("1. 任务一 2. 任务二", config) is False
