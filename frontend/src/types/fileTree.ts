// 文件功能：文件树（项目目录结构）相关类型定义
// 文件描述：定义文件树节点结构及文件树接口响应结构，用于前端文件浏览器组件渲染项目目录
// 核心逻辑：树形结构，每个节点标记文件/目录类型及 git 状态，目录节点通过 children 递归包含子节点
// git 变更状态码：M(修改) / A(新增) / D(删除) / U(未合并/冲突) / R(重命名)
export type GitStatusCode = 'M' | 'A' | 'D' | 'U' | 'R'

// 文件树节点：表示项目目录树中的一个文件或目录
export interface FileTreeNode {
  name: string // 文件/目录名（不含路径）
  type: 'file' | 'directory'
  path: string // 相对项目根目录的路径
  git_status: GitStatusCode | null // 该文件的 git 变更状态，无变更或非文件节点时为 null
  children?: FileTreeNode[] | null // 子节点列表，仅目录节点可能有值；未展开或非目录时为 null/undefined
}

// 文件树接口响应：顶层为文件树的根节点数组
export interface FileTreeResponse {
  tree: FileTreeNode[]
}
