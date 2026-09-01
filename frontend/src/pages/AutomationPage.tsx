/**
 * 文件功能：自动化任务页面（占位/预留页）
 * 文件描述：展示自动化任务功能的入口页面，当前仅作为占位说明，尚未接入真实的任务列表、
 *          运行历史、调度规则等功能
 * 核心逻辑：纯静态渲染，无状态、无副作用、无数据请求
 */
import { Clock3, Workflow } from 'lucide-react'

/**
 * 函数名：AutomationPage
 * 入参：无
 * 功能：渲染自动化任务页面的静态占位内容，说明后续将承载的功能
 * 运行逻辑：直接返回固定的标题、说明文案和提示卡片 JSX 结构，无任何交互逻辑
 * 出参：JSX.Element - 自动化任务页面的 DOM 结构
 */
export default function AutomationPage() {
  return (
    <div className="h-full overflow-y-auto bg-surface-primary">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
        <div className="mb-8 lg:mb-10">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-surface-tertiary px-3 py-1 text-sm text-content-muted">
            <Workflow className="h-4 w-4" />
            <span>自动化</span>
          </div>
          <h1 className="text-2xl font-semibold text-content-primary sm:text-3xl">自动化任务</h1>
          <p className="mt-3 max-w-2xl text-[16px] leading-7 text-content-muted">
            后续这里会承载定时执行、巡检任务和周期性工作流的配置入口。
          </p>
        </div>

        <div className="rounded-3xl border border-edge bg-surface-tertiary px-4 py-6 sm:px-8 sm:py-10">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
            <div className="rounded-2xl bg-surface-primary p-3 text-content-muted shadow-sm">
              <Clock3 className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-content-primary">自动化入口已就位</h2>
              <p className="mt-3 max-w-2xl text-[15px] leading-7 text-content-muted">
                当前先提供正式页面和导航位置，后续可以在这里补任务列表、运行历史、调度规则和失败告警。
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
