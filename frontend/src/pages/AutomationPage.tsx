import { Clock3, Workflow } from 'lucide-react'

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
