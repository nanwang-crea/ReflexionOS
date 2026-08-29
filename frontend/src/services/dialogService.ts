// 文件功能：应用内对话交互服务（错误提示 / 确认框 / 文本输入）
// 文件描述：定义 DialogService 接口并提供其默认实现 nativeDialogService，
//           将“弹提示”“弹确认框”这类交互统一收口，业务代码不直接依赖具体 UI 实现
// 核心逻辑：notifyError 走 toast store 展示错误提示；confirmAction 走 confirmDialog store
//           弹出应用内自绘确认框，并以 Promise 形式等待用户点击结果；
//           promptText 目前无调用方，仍指向浏览器原生 window.prompt 作为占位实现
import { useToastStore } from '@/shared/stores/toast.store'
import { useConfirmDialogStore, type ConfirmOptions } from '@/shared/stores/confirmDialog.store'

// DialogService：对话交互能力的统一接口定义
export interface DialogService {
  notifyError: (message: string) => void
  // 确认操作改为异步：弹出应用内确认框，返回用户是否确认。
  confirmAction: (message: string, options?: ConfirmOptions) => Promise<boolean>
  promptText: (message: string, defaultValue?: string) => string | null
}

// nativeDialogService：DialogService 的默认实现，基于应用内 store 而非浏览器原生对话框
export const nativeDialogService: DialogService = {
  /**
   * 函数名：notifyError
   * 入参：
   *   - message (string): 需要展示的错误提示文案
   * 功能：以 toast 形式向用户展示一条错误提示
   * 运行逻辑：调用 toast store 的 addToast，级别固定为 'error'
   * 出参：无
   */
  notifyError: (message) => {
    useToastStore.getState().addToast('error', message)
  },
  // 通过 confirmDialog store 弹出应用内确认框，等待用户操作。
  /**
   * 函数名：confirmAction
   * 入参：
   *   - message (string): 确认框中展示的提示文案
   *   - options (ConfirmOptions, 可选): 确认框附加配置（如标题、危险态样式变体）
   * 功能：弹出应用内确认框，异步等待用户确认或取消
   * 运行逻辑：委托给 confirmDialog store 的 requestConfirm，由该 store 维护弹框状态
   *           并在用户操作后兑现 Promise
   * 出参：Promise<boolean> - true 表示用户确认，false 表示取消或被新请求拒绝
   */
  confirmAction: (message, options) =>
    useConfirmDialogStore.getState().requestConfirm(message, options),
  // promptText 暂无调用方（死代码），保留指向原生 window.prompt，不在本次范围。
  /**
   * 函数名：promptText
   * 入参：
   *   - message (string): 输入框提示文案
   *   - defaultValue (string, 可选): 输入框默认值
   * 功能：弹出浏览器原生文本输入框，获取用户输入
   * 运行逻辑：直接调用 window.prompt；当前项目内暂无调用方，保留作占位实现
   * 出参：string | null - 用户输入的文本，取消输入时为 null
   */
  promptText: (message, defaultValue) => window.prompt(message, defaultValue),
}
