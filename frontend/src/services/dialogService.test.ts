import { afterEach, describe, expect, it, vi } from 'vitest'
import { nativeDialogService } from './dialogService'

describe('nativeDialogService', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('routes notifications, confirmations, and prompts through native browser dialogs', () => {
    const alertMock = vi.fn()
    const confirmMock = vi.fn(() => true)
    const promptMock = vi.fn(() => 'next')
    vi.stubGlobal('window', {
      alert: alertMock,
      confirm: confirmMock,
      prompt: promptMock,
    })

    nativeDialogService.notifyError('保存失败')
    const confirmed = nativeDialogService.confirmAction('确定继续吗？')
    const prompted = nativeDialogService.promptText('重命名', '旧名称')

    expect(alertMock).toHaveBeenCalledWith('保存失败')
    expect(confirmMock).toHaveBeenCalledWith('确定继续吗？')
    expect(confirmed).toBe(true)
    expect(promptMock).toHaveBeenCalledWith('重命名', '旧名称')
    expect(prompted).toBe('next')
  })
})
