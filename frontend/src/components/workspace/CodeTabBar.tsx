import { Save } from 'lucide-react'
import type { CodeSubTab } from '@/features/code/codeTabStore'

interface CodeTabBarProps {
  subTab: CodeSubTab
  onSubTabChange: (subTab: CodeSubTab) => void
  filename: string | null
  isDirty: boolean
  onSave: () => void
  showSave: boolean
}

export function CodeTabBar({
  subTab,
  onSubTabChange,
  filename,
  isDirty,
  onSave,
  showSave,
}: CodeTabBarProps) {
  const tabs: { key: CodeSubTab; label: string }[] = [
    { key: 'diff', label: 'Diff' },
    { key: 'edit', label: '编辑' },
  ]

  return (
    <div className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-2">
      <div className="flex items-center gap-1">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => onSubTabChange(tab.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              subTab === tab.key
                ? 'bg-slate-100 text-slate-900'
                : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3">
        {filename && (
          <span className="text-sm text-slate-600">
            {isDirty && <span className="mr-1 text-amber-500">●</span>}
            {filename}
          </span>
        )}
        {showSave && (
          <button
            type="button"
            onClick={onSave}
            disabled={!isDirty}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Save className="h-3.5 w-3.5" />
            保存
          </button>
        )}
      </div>
    </div>
  )
}
