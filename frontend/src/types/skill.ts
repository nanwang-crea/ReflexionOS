// 文件功能：Skill（技能/能力包）相关类型定义
// 文件描述：定义 skill 的基本信息、详情（含正文内容）以及按分类组织的 skill 列表结构
// 核心逻辑：skill 可能依赖其他 skill（required_skills），来源可能是内置/插件（source/source_type/plugin_name 标注来源）；
//          SkillCategories 按分类名分组，供设置页面分类展示
export interface Skill {
  name: string
  description: string
  category: string // 所属分类
  required_skills: string[] // 依赖的其他 skill 名称列表
  enabled: boolean // 是否启用
  source: string // 来源标识（如具体插件名或内置来源说明）
  source_type: string // 来源类型（如 'builtin'/'plugin' 等）
  install_path: string // 安装路径
  plugin_name: string // 所属插件名（若来自插件）
  version: string
}

// Skill 详情：在基本信息基础上附带完整正文内容（如 skill 的 markdown 说明文档）
export interface SkillDetail extends Skill {
  content: string
}

// 按分类名组织的 skill 列表：key 为分类名，value 为该分类下的 skill 简要信息（名称/描述/启用状态）列表
export interface SkillCategories {
  [category: string]: { name: string; description: string; enabled: boolean }[]
}
