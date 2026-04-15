import pytest
from app.orchestration.skill_registry import SkillRegistry, Skill, skill_registry


class TestSkillRegistry:
    
    def test_registry_initialization(self):
        registry = SkillRegistry()
        
        assert len(registry.skills) > 0
        assert "code_edit" in registry.skills
        assert "debug" in registry.skills
        assert "refactor" in registry.skills
    
    def test_register_skill(self):
        registry = SkillRegistry()
        skill = Skill(
            name="test_skill",
            description="测试技能",
            tools=["file"],
            prompt_template="Test template"
        )
        
        registry.register_skill(skill)
        
        assert "test_skill" in registry.skills
        assert registry.skills["test_skill"].description == "测试技能"
    
    def test_unregister_skill(self):
        registry = SkillRegistry()
        skill = Skill(name="to_remove", description="将被删除")
        registry.register_skill(skill)
        
        result = registry.unregister_skill("to_remove")
        
        assert result is True
        assert "to_remove" not in registry.skills
    
    def test_get_skill(self):
        registry = SkillRegistry()
        
        skill = registry.get_skill("code_edit")
        
        assert skill is not None
        assert skill.name == "code_edit"
    
    def test_get_nonexistent_skill(self):
        registry = SkillRegistry()
        
        skill = registry.get_skill("nonexistent")
        
        assert skill is None
    
    def test_list_skills(self):
        registry = SkillRegistry()
        
        skills = registry.list_skills()
        
        assert len(skills) >= 3
        assert any(s.name == "code_edit" for s in skills)
    
    def test_enable_disable_skill(self):
        registry = SkillRegistry()
        
        registry.disable_skill("code_edit")
        assert registry.get_skill("code_edit").enabled is False
        
        registry.enable_skill("code_edit")
        assert registry.get_skill("code_edit").enabled is True
    
    def test_list_enabled_skills(self):
        registry = SkillRegistry()
        registry.disable_skill("debug")
        
        enabled = registry.list_enabled_skills()
        
        assert all(s.enabled for s in enabled)
        assert "debug" not in [s.name for s in enabled]
        
        registry.enable_skill("debug")


class TestSkill:
    
    def test_skill_creation(self):
        skill = Skill(
            name="test",
            description="测试",
            tools=["file", "shell"],
            prompt_template="template"
        )
        
        assert skill.name == "test"
        assert len(skill.tools) == 2
        assert skill.enabled is True
    
    def test_skill_default_values(self):
        skill = Skill(name="minimal", description="最小技能")
        
        assert skill.tools == []
        assert skill.prompt_template == ""
        assert skill.enabled is True
