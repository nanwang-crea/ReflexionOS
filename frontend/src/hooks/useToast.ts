// 文件功能：全局 Toast 提示的便捷调用入口
// 文件描述：封装 toast.store 的 addToast 方法，提供组件内 hook 用法和组件外（非 React 上下文）直接调用两种方式
// 核心逻辑：useToast 通过 zustand store 订阅 addToast 方法供组件使用；showToast 直接读取 store 的最新状态，
// 用于事件回调、工具函数等无法使用 hook 的场景
import { useToastStore, type ToastLevel } from '@/shared/stores/toast.store'

// 函数名：useToast
// 入参：无
// 功能：在 React 组件内提供 showError/showWarning/showInfo 三个便捷方法，用于弹出不同级别的全局提示
// 运行逻辑：从 toastStore 中取出 addToast 方法，包一层固定级别（error/warning/info）的调用
// 出参：{ showError, showWarning, showInfo } - 三个接收 message 字符串的提示函数
export function useToast() {
  const addToast = useToastStore((s) => s.addToast)
  return {
    showError: (message: string) => addToast('error', message),
    showWarning: (message: string) => addToast('warning', message),
    showInfo: (message: string) => addToast('info', message),
  }
}

// 函数名：showToast
// 入参：
//   - level (ToastLevel): 提示级别，如 'error' | 'warning' | 'info'
//   - message (string): 提示文案
//   - duration (number, 可选): 提示展示时长（毫秒），不传则使用 store 默认值
// 功能：在非 React 组件上下文（如普通函数、事件处理器）中直接触发全局提示
// 运行逻辑：跳过 hook 订阅，直接调用 useToastStore.getState() 获取当前 store 实例并调用 addToast
// 出参：无
export function showToast(level: ToastLevel, message: string, duration?: number) {
  useToastStore.getState().addToast(level, message, duration)
}
