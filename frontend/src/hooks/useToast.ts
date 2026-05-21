import { useToastStore, type ToastLevel } from '@/stores/toastStore'

export function useToast() {
  const addToast = useToastStore((s) => s.addToast)
  return {
    showError: (message: string) => addToast('error', message),
    showWarning: (message: string) => addToast('warning', message),
    showInfo: (message: string) => addToast('info', message),
  }
}

export function showToast(level: ToastLevel, message: string, duration?: number) {
  useToastStore.getState().addToast(level, message, duration)
}
