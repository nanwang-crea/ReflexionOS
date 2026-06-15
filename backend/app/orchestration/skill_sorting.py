from app.orchestration.skill_registry import SkillMetadata


def get_plugin_type(skill: SkillMetadata) -> str:
    """获取技能的插件类型"""
    if not skill.plugin_name:
        return 'independent'
    if not skill.install_path:
        return 'local'

    # 标准化路径
    normalized_path = skill.install_path.replace('\\', '/')
    if '/.reflexion/' in normalized_path:
        return 'installed'
    if normalized_path.endswith('/skills') or normalized_path.endswith('/skills/'):
        return 'builtin'
    return 'local'


def sort_skills(skills: list[SkillMetadata]) -> list[SkillMetadata]:
    """
    排序技能列表
    排序规则：插件类型 → 插件名 → 技能名
    """
    type_order = {
        'builtin': 0,
        'installed': 1,
        'local': 2,
        'independent': 3,
    }

    def sort_key(skill: SkillMetadata) -> tuple:
        plugin_type = get_plugin_type(skill)
        type_priority = type_order.get(plugin_type, 999)
        plugin_name = skill.plugin_name or ''
        skill_name = skill.name
        return (type_priority, plugin_name, skill_name)

    return sorted(skills, key=sort_key)
