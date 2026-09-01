/**
 * 文件功能：系统提示消息展示组件
 * 文件描述：以醒目的警示样式展示系统级提示文本（如中断/错误提示）
 * 核心逻辑：纯展示组件，直接渲染传入的文本内容
 */
import { memo } from 'react'

/**
 * 组件名：SystemNoticeItem
 * 入参（props）：
 *   - contentText (string): 系统提示的文本内容
 * 作用/渲染逻辑：以警示色卡片样式展示传入的文本
 * 返回值：JSX.Element - 系统提示卡片
 */
export const SystemNoticeItem = memo(function SystemNoticeItem({ contentText }: { contentText: string }) {
  return (
    <div className="mb-6 max-w-[920px] mx-auto w-full rounded-2xl border border-status-warning-border bg-status-warning-soft px-4 py-3 text-sm text-status-warning">
      {contentText}
    </div>
  )
})
