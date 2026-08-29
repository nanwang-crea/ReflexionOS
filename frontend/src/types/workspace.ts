// 文件功能：工作区（Workspace）侧边栏会话相关类型定义
// 文件描述：定义会话摘要类型及创建/更新会话时使用的载荷（payload）结构，供工作区侧边栏会话列表使用
// 核心逻辑：SessionSummary 直接复用 ConversationSession；创建与更新会话共用同一套可选字段结构（SessionPayload）
import type { ConversationSession } from '@/types/conversation'

// 会话摘要：用于侧边栏列表展示的会话信息，直接复用完整的 ConversationSession 结构
export type SessionSummary = ConversationSession

// 会话载荷：创建/更新会话时提交的字段，均为可选（未提供的字段保持不变或使用默认值）
export interface SessionPayload {
  title?: string
  preferredProviderId?: string | null
  preferredModelId?: string | null
}

// 创建会话载荷（结构与 SessionPayload 相同）
export type SessionCreatePayload = SessionPayload
// 更新会话载荷（结构与 SessionPayload 相同）
export type SessionUpdatePayload = SessionPayload
