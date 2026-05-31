export interface Skill {
  name: string
  description: string
  category: string
  required_skills: string[]
  enabled: boolean
}

export interface SkillDetail extends Skill {
  content: string
}

export interface SkillCategories {
  [category: string]: { name: string; description: string; enabled: boolean }[]
}
