import { useCallback, useEffect } from 'react'
import { uiSettingsApi } from '@/features/settings/api/uiSettings.api'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import { useToastStore } from '@/shared/stores/toast.store'

function ToggleSwitch({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: () => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 ${
        checked ? 'bg-accent' : 'bg-surface-tertiary'
      }`}
    >
      <span
        aria-hidden="true"
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  )
}

export function DisplayOptionsPanel() {
  const showProcessExpanded = useSettingsStore((s) => s.showProcessExpanded)
  const autoCollapseProcess = useSettingsStore((s) => s.autoCollapseProcess)
  const uiSettingsLoaded = useSettingsStore((s) => s.uiSettingsLoaded)
  const setUISetting = useSettingsStore((s) => s.setUISetting)

  useEffect(() => {
    if (uiSettingsLoaded) return
    uiSettingsApi.get()
      .then((res) => {
        setUISetting({
          showProcessExpanded: res.data.show_process_expanded,
          autoCollapseProcess: res.data.auto_collapse_process,
        })
      })
      .catch(() => {
        useToastStore.getState().addToast('error', '加载 UI 设置失败')
      })
  }, [uiSettingsLoaded, setUISetting])

  const handleToggle = useCallback(async (key: 'show_process_expanded' | 'auto_collapse_process') => {
    const current = key === 'show_process_expanded'
      ? showProcessExpanded
      : autoCollapseProcess
    const next = !current
    try {
      await uiSettingsApi.update({
        show_process_expanded: key === 'show_process_expanded' ? next : showProcessExpanded,
        auto_collapse_process: key === 'auto_collapse_process' ? next : autoCollapseProcess,
      })
      setUISetting({
        showProcessExpanded: key === 'show_process_expanded' ? next : showProcessExpanded,
        autoCollapseProcess: key === 'auto_collapse_process' ? next : autoCollapseProcess,
      })
    } catch {
      useToastStore.getState().addToast('error', '保存 UI 设置失败')
    }
  }, [showProcessExpanded, autoCollapseProcess, setUISetting])

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-edge bg-surface-primary p-6">
        <h3 className="mb-4 text-lg font-semibold text-content-primary">聊天显示</h3>

        <div className="flex items-center justify-between">
          <div>
            <p className="text-content-secondary">过程内容默认展开</p>
            <p className="mt-1 text-sm text-content-muted">
              开启后，思考过程和过程说明的内容默认展开显示；关闭则只显示标题行
            </p>
          </div>
          <ToggleSwitch
            checked={showProcessExpanded}
            onChange={() => { void handleToggle('show_process_expanded') }}
          />
        </div>

        <hr className="my-5 border-edge" />

        <div className="flex items-center justify-between">
          <div>
            <p className="text-content-secondary">完成后自动折叠过程</p>
            <p className="mt-1 text-sm text-content-muted">
              开启后，AI 回答生成完毕时自动将思考、工具调用等过程区域整体折叠，点击「展开过程」可重新查看
            </p>
          </div>
          <ToggleSwitch
            checked={autoCollapseProcess}
            onChange={() => { void handleToggle('auto_collapse_process') }}
          />
        </div>
      </div>
    </div>
  )
}
