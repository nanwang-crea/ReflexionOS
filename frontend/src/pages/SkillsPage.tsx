import { useEffect, useState } from 'react'
import { Sparkles, Wrench } from 'lucide-react'
import { skillApi } from '@/services/apiClient'
import type { Skill } from '@/types/skill'

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadSkills = async () => {
      setLoading(true)
      try {
        const response = await skillApi.list()
        setSkills(response.data)
      } catch (error) {
        console.error('Failed to load skills:', error)
      } finally {
        setLoading(false)
      }
    }

    loadSkills()
  }, [])

  return (
    <div className="h-full overflow-y-auto bg-white">
      <div className="mx-auto max-w-5xl px-10 py-10">
        <div className="mb-10">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500">
            <Sparkles className="h-4 w-4" />
            <span>技能</span>
          </div>
          <h1 className="text-3xl font-semibold text-slate-900">当前可用技能</h1>
          <p className="mt-3 max-w-2xl text-[16px] leading-7 text-slate-500">
            技能决定了 Agent 在特定任务下优先采用的工具组合和执行偏好。
          </p>
        </div>

        {loading ? (
          <div className="rounded-3xl border border-slate-200 bg-slate-50 px-6 py-8 text-slate-500">
            正在加载技能列表...
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {skills.map((skill) => (
              <div
                key={skill.name}
                className="rounded-3xl border border-slate-200 bg-white p-6"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-semibold text-slate-900">{skill.name}</h2>
                    <p className="mt-2 text-[15px] leading-7 text-slate-500">
                      {skill.description}
                    </p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-medium ${
                    skill.enabled
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-slate-100 text-slate-500'
                  }`}>
                    {skill.enabled ? '已启用' : '已停用'}
                  </span>
                </div>

                <div className="mt-5">
                  <div className="mb-2 flex items-center gap-2 text-sm text-slate-400">
                    <Wrench className="h-4 w-4" />
                    <span>工具</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {skill.tools.map((tool) => (
                      <span
                        key={tool}
                        className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600"
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="mt-5 rounded-2xl bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-500">
                  {skill.prompt_template}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
