export type GitStatusCode = 'M' | 'A' | 'D' | 'U' | 'R'

export function isValidGitStatusCode(value: unknown): value is GitStatusCode {
  return typeof value === 'string' && ['M', 'A', 'D', 'U', 'R'].includes(value)
}

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

export interface GitBranchItem {
  name: string
  is_current: boolean
  is_remote: boolean
}

export interface GitBranchListResponse {
  branches: GitBranchItem[]
  current: string
}

export interface GitLogCommit {
  hash: string
  short_hash: string
  author: string
  date: string
  message: string
}

export interface GitLogResponse {
  commits: GitLogCommit[]
}
