export interface Skill {
  name: string
  description: string
  category: string
  required_skills: string[]
  enabled: boolean
  source: string
  source_type: string
  install_path: string
  plugin_name: string
  version: string
}

export interface SkillDetail extends Skill {
  content: string
}

export interface SkillCategories {
  [category: string]: { name: string; description: string; enabled: boolean }[]
}
