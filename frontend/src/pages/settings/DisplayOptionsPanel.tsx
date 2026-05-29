import { useCallback, useEffect } from 'react'
import { uiSettingsApi } from '@/services/apiClient'
import { useSettingsStore } from '@/stores/settingsStore'
import { useToastStore } from '@/stores/toastStore'

export function DisplayOptionsPanel() {
  const showContinuationNotices = useSettingsStore((s) => s.showContinuationNotices)
  const uiSettingsLoaded = useSettingsStore((s) => s.uiSettingsLoaded)
  const setUISetting = useSettingsStore((s) => s.setUISetting)

  useEffect(() => {
    if (uiSettingsLoaded) return
    uiSettingsApi.get()
      .then((res) => {
        setUISetting({ showContinuationNotices: res.data.show_continuation_notices })
      })
      .catch(() => {
        useToastStore.getState().addToast('error', '加载 UI 设置失败')
      })
  }, [uiSettingsLoaded, setUISetting])

  const handleToggleContinuationNotices = useCallback(async () => {
    const next = !showContinuationNotices
    try {
      await uiSettingsApi.update({ show_continuation_notices: next })
      setUISetting({ showContinuationNotices: next })
    } catch {
      useToastStore.getState().addToast('error', '保存 UI 设置失败')
    }
  }, [showContinuationNotices, setUISetting])

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-edge bg-surface-primary p-6">
        <h3 className="mb-4 text-lg font-semibold text-content-primary">聊天显示</h3>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-content-secondary">显示延续摘要通知</p>
            <p className="mt-1 text-sm text-content-muted">
              开启后，对话上下文压缩时会在聊天中显示摘要通知
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={showContinuationNotices}
            onClick={() => { void handleToggleContinuationNotices() }}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 ${
              showContinuationNotices ? 'bg-accent' : 'bg-surface-tertiary'
            }`}
          >
            <span
              aria-hidden="true"
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                showContinuationNotices ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </div>
    </div>
  )
}
