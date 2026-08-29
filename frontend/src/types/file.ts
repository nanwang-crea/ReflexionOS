// 文件功能：文件读写相关的接口请求/响应类型定义
// 文件描述：定义读取文件内容、读取文件对比内容、写入文件的请求与响应结构，对应后端文件操作 API
// 核心逻辑：读操作返回内容 + 语言类型（用于编辑器语法高亮）；写操作返回是否成功及错误信息
export interface FileContentResponse {
  content: string // 文件文本内容
  language: string // 推断出的语言类型（用于编辑器语法高亮，如 'typescript'/'python' 等）
  exists: boolean // 该文件是否存在
}

// 文件对比（diff）内容响应：用于展示某文件修改前后的内容差异
export interface FileDiffContentResponse {
  original: string // 修改前的原始内容
  modified: string // 修改后的当前内容
  language: string // 推断出的语言类型（用于 diff 编辑器语法高亮）
}

// 写入文件请求
export interface FileWriteRequest {
  project_id: string // 目标项目 id
  path: string // 文件在项目内的相对路径
  content: string // 要写入的文件内容
}

// 写入文件响应
export interface FileWriteResponse {
  success: boolean // 是否写入成功
  error: string | null // 失败时的错误信息，成功时为 null
}
