export interface Skill {
  name: string
  description: string
  category: string
  required_skills: string[]
  enabled: boolean
  source: string
  install_path: string
}

export interface SkillDetail extends Skill {
  content: string
}

export interface SkillCategories {
  [category: string]: { name: string; description: string; enabled: boolean }[]
}

export interface InstallRequest {
  url: string
  skill_name: string
  subdir?: string
  branch?: string
}
