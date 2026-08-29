"""
技能排序模块。

根据技能来源（内置/已安装插件/本地/独立）与插件名、技能名，
为技能列表提供统一稳定的展示排序规则。
"""

from app.orchestration.skill_registry import SkillMetadata


def get_plugin_type(skill: SkillMetadata) -> str:
    """获取技能的插件类型

    判断规则：
        - 无 plugin_name：视为独立技能 'independent'
        - 有 plugin_name 但无 install_path：视为本地 'local'
        - install_path 包含 '/.reflexion/'：视为已安装插件 'installed'
        - install_path 以 '/skills' 结尾：视为内置 'builtin'
        - 其余情况：'local'

    Args:
        skill: 技能元数据

    Returns:
        str: 插件类型标识，取值为 'builtin'/'installed'/'local'/'independent'
    """
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
    排序规则：插件类型（builtin < installed < local < independent）→ 插件名 → 技能名

    Args:
        skills: 待排序的技能元数据列表

    Returns:
        list[SkillMetadata]: 按规则排序后的新列表
    """
    type_order = {
        'builtin': 0,
        'installed': 1,
        'local': 2,
        'independent': 3,
    }

    def sort_key(skill: SkillMetadata) -> tuple:
        """计算单个技能的排序键：(类型优先级, 插件名, 技能名)"""
        plugin_type = get_plugin_type(skill)
        type_priority = type_order.get(plugin_type, 999)
        plugin_name = skill.plugin_name or ''
        skill_name = skill.name
        return (type_priority, plugin_name, skill_name)

    return sorted(skills, key=sort_key)
