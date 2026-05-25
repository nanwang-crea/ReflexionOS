import { Save } from 'lucide-react'

interface CodeTabBarProps {
  filename: string | null
  isDirty: boolean
  onSave: () => void
}

export function CodeTabBar({
  filename,
  isDirty,
  onSave,
}: CodeTabBarProps) {
  return (
    <div className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-2">
      <div className="flex items-center gap-2">
        {filename && (
          <span className="text-sm text-slate-600">
            {isDirty && <span className="mr-1 text-amber-500">●</span>}
            {filename}
          </span>
        )}
      </div>

      <button
        type="button"
        onClick={onSave}
        disabled={!isDirty}
        className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Save className="h-3.5 w-3.5" />
        保存
      </button>
    </div>
  )
}
