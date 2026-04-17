import { Blocks, Puzzle } from 'lucide-react'

export default function PluginsPage() {
  return (
    <div className="h-full overflow-y-auto bg-white">
      <div className="mx-auto max-w-5xl px-10 py-10">
        <div className="mb-10">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500">
            <Puzzle className="h-4 w-4" />
            <span>插件</span>
          </div>
          <h1 className="text-3xl font-semibold text-slate-900">插件工作台</h1>
          <p className="mt-3 max-w-2xl text-[16px] leading-7 text-slate-500">
            这里会展示已安装插件、可接入能力和未来的插件市场入口。
          </p>
        </div>

        <div className="rounded-[32px] border border-slate-200 bg-slate-50 px-8 py-10">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl bg-white p-3 text-slate-500 shadow-sm">
              <Blocks className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-slate-900">暂未安装插件</h2>
              <p className="mt-3 max-w-2xl text-[15px] leading-7 text-slate-500">
                当前版本已经为插件预留了工作区页面，后续可以把外部工具、第三方服务集成和插件市场接进来。
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
