export interface FileContentResponse {
  content: string
  language: string
  exists: boolean
}

export interface FileDiffContentResponse {
  original: string
  modified: string
  language: string
}

export interface FileWriteRequest {
  project_id: string
  path: string
  content: string
}

export interface FileWriteResponse {
  success: boolean
  error: string | null
}
