export interface Plugin {
  name: string
  specifier: string
  resolved_ref: string
  install_path: string
  has_tools: boolean
  skill_dirs: string[]
  num_skills: number
}

export interface InstallPluginRequest {
  specifier: string
}
