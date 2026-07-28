// 应用内确认弹框的全局单例 store。
// 负责保存当前待确认请求的状态,并在 service 与 UI 之间桥接一个 Promise:
// requestConfirm 写入请求并返回 Promise;用户操作后由 resolveConfirm 兑现并关闭弹框。
// 同一时刻只允许一个弹框:已打开时的新请求直接拒绝(resolve false),避免堆叠/竞态。
import { create } from 'zustand'

export type ConfirmVariant = 'danger' | 'default'

export interface ConfirmOptions {
  title?: string
  variant?: ConfirmVariant
}

interface ConfirmDialogState {
  open: boolean
  title?: string
  message: string
  variant: ConfirmVariant
  // 当前挂起请求的 resolve 引用;关闭后置空,保证只兑现一次。
  resolve: ((confirmed: boolean) => void) | null
  // 发起一次确认;返回的 Promise 在用户点确认/取消后兑现为 true/false。
  requestConfirm: (message: string, options?: ConfirmOptions) => Promise<boolean>
  // 兑现当前请求并关闭弹框;无挂起请求时安全 no-op。
  resolveConfirm: (confirmed: boolean) => void
}

export const useConfirmDialogStore = create<ConfirmDialogState>((set, get) => ({
  open: false,
  title: undefined,
  message: '',
  variant: 'default',
  resolve: null,
  requestConfirm: (message, options) => {
    // 已有弹框打开时拒绝新请求,避免堆叠。
    if (get().open) {
      return Promise.resolve(false)
    }
    return new Promise<boolean>((resolve) => {
      set({
        open: true,
        message,
        title: options?.title,
        variant: options?.variant ?? 'default',
        resolve,
      })
    })
  },
  resolveConfirm: (confirmed) => {
    const { resolve } = get()
    if (!resolve) {
      return
    }
    // 先关闭并清空 resolve 引用,再兑现,确保只兑现一次。
    set({ open: false, resolve: null })
    resolve(confirmed)
  },
}))
