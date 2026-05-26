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
    <div className="flex items-center justify-between border-b border-edge bg-surface-primary px-4 py-2">
      <div className="flex items-center gap-2">
        {filename && (
          <span className="text-sm text-content-secondary">
            {isDirty && <span className="mr-1 text-amber-500">●</span>}
            {filename}
          </span>
        )}
      </div>

      <button
        type="button"
        onClick={onSave}
        disabled={!isDirty}
        className="inline-flex items-center gap-1.5 rounded-md border border-edge bg-surface-primary px-3 py-1.5 text-sm font-medium text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Save className="h-3.5 w-3.5" />
        保存
      </button>
    </div>
  )
}
