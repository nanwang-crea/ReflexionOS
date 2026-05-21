import { create } from 'zustand'

export type ToastLevel = 'error' | 'warning' | 'info'

export interface ToastItem {
  id: string
  level: ToastLevel
  message: string
  duration: number
}

interface ToastState {
  toasts: ToastItem[]
  addToast: (level: ToastLevel, message: string, duration?: number) => void
  removeToast: (id: string) => void
}

let nextId = 0

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
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
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }))
  },
}))
