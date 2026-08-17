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
  /**
   * 函数名：requestConfirm
   * 入参：
   *   - message (string): 确认框展示的提示文案
   *   - options (ConfirmOptions, 可选): title（标题）、variant（样式变体，默认 'default'）
   * 功能：发起一次确认请求，打开弹框并等待用户操作
   * 运行逻辑：
   *   1. 若当前已有弹框打开（get().open 为 true），直接返回已 resolve 为 false 的 Promise，
   *      拒绝本次新请求，避免多个确认框堆叠或状态竞态
   *   2. 否则创建一个新 Promise，将其 resolve 函数保存到 state.resolve，
   *      同时写入 open=true、message、title、variant，交由 UI 层渲染弹框
   *   3. 该 Promise 保持挂起，直到调用方调用 resolveConfirm 才会兑现
   * 出参：Promise<boolean> - true 表示用户确认，false 表示取消或被新请求拒绝
   */
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
  /**
   * 函数名：resolveConfirm
   * 入参：
   *   - confirmed (boolean): 用户的操作结果，true 表示确认，false 表示取消
   * 功能：兑现当前挂起的确认请求并关闭弹框
   * 运行逻辑：
   *   1. 读取当前 state 中的 resolve 引用，若为空（无挂起请求）则直接返回，安全 no-op
   *   2. 先将 open 置为 false 并清空 resolve 引用（避免重复兑现），再调用取出的 resolve
   *      兑现 Promise，确保即便回调中同步再次触发也不会二次执行
   * 出参：无
   */
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
