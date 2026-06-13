import { afterEach, describe, expect, it, vi } from 'vitest'
import { nativeDialogService } from './dialogService'
import { useToastStore } from '@/shared/stores/toast.store'

describe('nativeDialogService', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    useToastStore.setState({ toasts: [] })
  })

  it('routes notifications, confirmations, and prompts through native browser dialogs', () => {
    const confirmMock = vi.fn(() => true)
    const promptMock = vi.fn(() => 'next')
    vi.stubGlobal('window', {
      confirm: confirmMock,
      prompt: promptMock,
    })

    nativeDialogService.notifyError('保存失败')
    const confirmed = nativeDialogService.confirmAction('确定继续吗？')
    const prompted = nativeDialogService.promptText('重命名', '旧名称')

    const toasts = useToastStore.getState().toasts
    expect(toasts).toHaveLength(1)
    expect(toasts[0].level).toBe('error')
    expect(toasts[0].message).toBe('保存失败')
    expect(confirmMock).toHaveBeenCalledWith('确定继续吗？')
    expect(confirmed).toBe(true)
    expect(promptMock).toHaveBeenCalledWith('重命名', '旧名称')
    expect(prompted).toBe('next')
  })
})
