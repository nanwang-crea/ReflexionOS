import { Clock3, Workflow } from 'lucide-react'

export default function AutomationPage() {
  return (
    <div className="h-full overflow-y-auto bg-white">
      <div className="mx-auto max-w-5xl px-10 py-10">
        <div className="mb-10">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500">
            <Workflow className="h-4 w-4" />
            <span>自动化</span>
          </div>
          <h1 className="text-3xl font-semibold text-slate-900">自动化任务</h1>
          <p className="mt-3 max-w-2xl text-[16px] leading-7 text-slate-500">
            后续这里会承载定时执行、巡检任务和周期性工作流的配置入口。
          </p>
        </div>

        <div className="rounded-[32px] border border-slate-200 bg-slate-50 px-8 py-10">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl bg-white p-3 text-slate-500 shadow-sm">
              <Clock3 className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-slate-900">自动化入口已就位</h2>
              <p className="mt-3 max-w-2xl text-[15px] leading-7 text-slate-500">
                当前先提供正式页面和导航位置，后续可以在这里补任务列表、运行历史、调度规则和失败告警。
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
