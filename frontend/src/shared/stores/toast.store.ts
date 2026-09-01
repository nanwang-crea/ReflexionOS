// 文件功能：全局 Toast 提示消息状态（zustand store）
// 文件描述：维护当前展示中的 Toast 列表，支持添加不同级别（error/warning/info）的提示，
//           并在指定时长后自动移除；也支持手动移除
// 核心逻辑：每条 Toast 分配一个自增 ID（模块级 nextId 计数器，非持久化，仅本次运行内唯一），
//           addToast 追加新 Toast 到列表，若 duration > 0 则用 setTimeout 定时自动移除；
//           duration <= 0 视为常驻提示，不设置自动移除定时器
import { create } from 'zustand'

// Toast 级别：错误 / 警告 / 提示
export type ToastLevel = 'error' | 'warning' | 'info'

// ToastItem：单条 Toast 的数据结构
export interface ToastItem {
  id: string
  level: ToastLevel
  message: string
  duration: number
}

// ToastState：Toast 列表状态 + 增删方法
interface ToastState {
  toasts: ToastItem[]
  addToast: (level: ToastLevel, message: string, duration?: number) => void
  removeToast: (id: string) => void
}

// 模块级自增计数器，用于生成本次运行内唯一的 Toast ID（不持久化，页面刷新后重置）
let nextId = 0

// useToastStore：全局 Toast 提示 store
export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  /**
   * 函数名：addToast
   * 入参：
   *   - level (ToastLevel): 提示级别（error/warning/info）
   *   - message (string): 提示文案
   *   - duration (number, 可选，默认 5000): 自动消失的毫秒数，<=0 表示常驻不自动消失
   * 功能：新增一条 Toast 提示，并在到期后自动移除
   * 运行逻辑：
   *   1. 用 nextId 自增生成唯一 id，构造 ToastItem 追加到列表末尾
   *   2. 若 duration > 0，启动一个 setTimeout，到期后从列表中过滤掉该 id 对应的 Toast
   * 出参：无
   */
  addToast: (level, message, duration = 5000) => {
    const id = `toast-${nextId++}`
    set((state) => ({
      toasts: [...state.toasts, { id, level, message, duration }],
    }))
    if (duration > 0) {
      setTimeout(() => {
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        }))
      }, duration)
    }
  },
  /**
   * 函数名：removeToast
   * 入参：
   *   - id (string): 要移除的 Toast ID
   * 功能：手动移除指定 Toast（如用户点击关闭按钮）
   * 运行逻辑：从列表中过滤掉匹配该 id 的项
   * 出参：无
   */
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }))
  },
}))
