// 文件功能：Git 操作相关类型定义
// 文件描述：定义 git 状态码、文件变更、分支信息、提交记录等类型，以及对应的接口响应结构，
//          供前端 git 面板（状态/分支/提交历史展示）使用
// 核心逻辑：围绕 git status / branch / log 三类查询组织类型；staged/unstaged/untracked 对应
//          git 工作区三种文件变更分类
// git 变更状态码：M(修改) / A(新增) / D(删除) / U(未合并/冲突) / R(重命名)
export type GitStatusCode = 'M' | 'A' | 'D' | 'U' | 'R'

/**
 * 函数名：isValidGitStatusCode
 * 入参：
 *   - value (unknown): 待校验的值
 * 功能：类型收窄守卫，判断给定值是否为合法的 GitStatusCode
 * 运行逻辑：判断是否为字符串且属于 ['M', 'A', 'D', 'U', 'R'] 集合
 * 出参：boolean（类型谓词）- true 表示 value 可安全当作 GitStatusCode 使用
 */
export function isValidGitStatusCode(value: unknown): value is GitStatusCode {
  return typeof value === 'string' && ['M', 'A', 'D', 'U', 'R'].includes(value)
}

// 单个文件的 git 变更记录
export interface GitFileChange {
  path: string // 文件相对项目根目录的路径
  status: GitStatusCode
  insertions?: number | null // 新增行数，未统计时为 null/undefined
  deletions?: number | null // 删除行数，未统计时为 null/undefined
}

// 分支基本信息：名称及与其上游分支的领先/落后提交数
export interface GitBranchInfo {
  name: string
  ahead: number // 领先上游分支的提交数
  behind: number // 落后上游分支的提交数
}

// git status 接口响应：当前分支及三类文件变更（已暂存/未暂存/未跟踪）
export interface GitStatusResponse {
  branch: string
  ahead: number
  behind: number
  staged: GitFileChange[] // 已 git add 暂存的变更
  unstaged: GitFileChange[] // 已跟踪但未暂存的变更
  untracked: GitFileChange[] // 尚未被 git 跟踪的新文件
}

// 通用 git 操作结果响应（如 commit/push/pull 等一次性操作）
export interface GitSimpleResponse {
  success: boolean
  error: string | null
}

// 单个分支条目
export interface GitBranchItem {
  name: string
  is_current: boolean // 是否为当前所在分支
  is_remote: boolean // 是否为远程分支
}

// 分支列表接口响应
export interface GitBranchListResponse {
  branches: GitBranchItem[]
  current: string // 当前分支名
}

// 单条 git 提交记录
export interface GitLogCommit {
  hash: string // 完整提交哈希
  short_hash: string // 短哈希（用于展示）
  author: string
  date: string
  message: string // 提交信息
}

// 提交历史接口响应
export interface GitLogResponse {
  commits: GitLogCommit[]
}
