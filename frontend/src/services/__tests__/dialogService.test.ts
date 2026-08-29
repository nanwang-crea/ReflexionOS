// nativeDialogService 的单测：验证错误提示走 Toast、确认对话框走 confirmDialog store（含 Promise 兑现）、以及文本输入仍走原生 window.prompt。
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nativeDialogService } from '../dialogService'
import { useToastStore } from '@/shared/stores/toast.store'
import { useConfirmDialogStore } from '@/shared/stores/confirmDialog.store'

describe('nativeDialogService', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    useToastStore.setState({ toasts: [] })
    useConfirmDialogStore.setState({ open: false, title: undefined, message: '', variant: 'default', resolve: null })
  })

  // 参数：无。
  // 验证：notifyError 会向 toast store 写入一条 level 为 error 的提示，内容与传入消息一致。
  it('notifyError 走 Toast', () => {
    nativeDialogService.notifyError('保存失败')
    const toasts = useToastStore.getState().toasts
    expect(toasts).toHaveLength(1)
    expect(toasts[0].level).toBe('error')
    expect(toasts[0].message).toBe('保存失败')
  })

  // 参数：无。
  // 验证：confirmAction 会打开 confirmDialog store 并写入标题/内容/变体，返回的 Promise 在调用 resolveConfirm(true) 后按预期兑现。
  it('confirmAction 走 confirmDialog store，返回 Promise，并在 resolve 后兑现', async () => {
    const promise = nativeDialogService.confirmAction('确定继续吗？', { variant: 'danger' })
    // 已打开且写入请求
    const state = useConfirmDialogStore.getState()
    expect(state.open).toBe(true)
    expect(state.message).toBe('确定继续吗？')
    expect(state.variant).toBe('danger')
    // 用户点确认
    useConfirmDialogStore.getState().resolveConfirm(true)
    await expect(promise).resolves.toBe(true)
  })

  // 参数：无。
  // 验证：promptText 未走自定义弹窗逻辑，而是直接调用全局 window.prompt 并原样返回其结果。
  it('promptText 仍走原生 window.prompt', () => {
    const promptMock = vi.fn(() => 'next')
    vi.stubGlobal('window', { prompt: promptMock })
    const prompted = nativeDialogService.promptText('重命名', '旧名称')
    expect(promptMock).toHaveBeenCalledWith('重命名', '旧名称')
    expect(prompted).toBe('next')
  })
})
