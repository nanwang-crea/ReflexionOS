export type GitStatusCode = 'M' | 'A' | 'D' | 'U' | 'R'

export interface GitFileChange {
  path: string
  status: GitStatusCode
  insertions?: number | null
  deletions?: number | null
}

export interface GitBranchInfo {
  name: string
  ahead: number
  behind: number
}

export interface GitStatusResponse {
  branch: string
  ahead: number
  behind: number
  staged: GitFileChange[]
  unstaged: GitFileChange[]
  untracked: GitFileChange[]
}

export interface GitSimpleResponse {
  success: boolean
  error: string | null
}
