// 文件功能：插件（Plugin）相关类型定义
// 文件描述：定义已安装插件的信息结构及安装插件的请求结构
// 核心逻辑：插件通过 specifier（如包名/git 地址等标识）安装，解析后固定到具体版本（resolved_ref），
//          并可能附带若干 skill 目录
export interface Plugin {
  name: string
  specifier: string // 安装时使用的插件标识符（如包名、git 仓库地址等）
  resolved_ref: string // 实际解析并锁定安装的版本/引用（如具体的 commit/tag/版本号）
  install_path: string // 插件在本地的安装路径
  has_tools: boolean // 该插件是否提供工具（tool）
  skill_dirs: string[] // 该插件下包含的 skill 目录列表
  num_skills: number // 该插件提供的 skill 数量
}

// 安装插件请求
export interface InstallPluginRequest {
  specifier: string // 待安装插件的标识符
}
