export interface Project {
  id: string
  name: string
  path: string
  language?: string
  created_at: string
  updated_at: string
}

export interface ProjectCreate {
  name: string
  path: string
  language?: string
}
