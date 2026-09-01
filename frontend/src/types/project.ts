// 文件功能：项目（Project）相关类型定义
// 文件描述：定义前端管理的“项目”实体结构，即用户接入的一个代码仓库/工作目录
// 核心逻辑：项目以本地路径（path）为核心标识，language 为可选的项目主语言标注
export interface Project {
  id: string
  name: string
  path: string // 项目在本地文件系统中的路径
  language?: string // 项目主语言（可选，如 'typescript'/'python' 等，用于展示图标等）
  created_at: string
  updated_at: string
}
