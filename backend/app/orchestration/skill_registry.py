from typing import Dict, List, Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class Skill(BaseModel):
    """技能定义"""
    name: str
    description: str
    tools: List[str] = []
    prompt_template: str = ""
    enabled: bool = True


class SkillRegistry:
    """技能注册中心 - 第一阶段仅提供基础接口"""
    
    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        self._register_default_skills()
        logger.info("技能注册中心初始化完成")
    
    def _register_default_skills(self):
        """注册默认技能"""
        default_skills = [
            Skill(
                name="code_edit",
                description="代码编辑技能：读取、修改、创建代码文件",
                tools=["file", "patch", "shell"],
                prompt_template="Focus on minimal, precise code changes."
            ),
            Skill(
                name="debug",
                description="调试技能：分析错误、查找问题、修复bug",
                tools=["file", "shell", "patch"],
                prompt_template="Analyze errors systematically, verify fixes with tests."
            ),
            Skill(
                name="refactor",
                description="重构技能：改进代码结构、优化性能",
                tools=["file", "patch", "shell"],
                prompt_template="Preserve behavior while improving code quality."
            ),
        ]
        
        for skill in default_skills:
            self.skills[skill.name] = skill
    
    def register_skill(self, skill: Skill) -> None:
        """注册技能"""
        self.skills[skill.name] = skill
        logger.info(f"注册技能: {skill.name}")
    
    def unregister_skill(self, name: str) -> bool:
        """注销技能"""
        if name in self.skills:
            del self.skills[name]
            logger.info(f"注销技能: {name}")
            return True
        return False
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """获取技能"""
        return self.skills.get(name)
    
    def list_skills(self) -> List[Skill]:
        """列出所有技能"""
        return list(self.skills.values())
    
    def list_enabled_skills(self) -> List[Skill]:
        """列出所有启用的技能"""
        return [s for s in self.skills.values() if s.enabled]
    
    def enable_skill(self, name: str) -> bool:
        """启用技能"""
        skill = self.get_skill(name)
        if skill:
            skill.enabled = True
            logger.info(f"启用技能: {name}")
            return True
        return False
    
    def disable_skill(self, name: str) -> bool:
        """禁用技能"""
        skill = self.get_skill(name)
        if skill:
            skill.enabled = False
            logger.info(f"禁用技能: {name}")
            return True
        return False


skill_registry = SkillRegistry()
