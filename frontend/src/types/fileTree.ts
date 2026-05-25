export type GitStatusCode = 'M' | 'A' | 'D' | 'U'

export interface FileTreeNode {
  name: string
  type: 'file' | 'directory'
  path: string
  git_status: GitStatusCode | null
  children?: FileTreeNode[] | null
}

export interface FileTreeResponse {
  tree: FileTreeNode[]
}
