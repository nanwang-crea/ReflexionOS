import { useToastStore } from '@/shared/stores/toast.store'
import { useConfirmDialogStore, type ConfirmOptions } from '@/shared/stores/confirmDialog.store'

export interface DialogService {
  notifyError: (message: string) => void
  // 确认操作改为异步：弹出应用内确认框，返回用户是否确认。
  confirmAction: (message: string, options?: ConfirmOptions) => Promise<boolean>
  promptText: (message: string, defaultValue?: string) => string | null
}

export const nativeDialogService: DialogService = {
  notifyError: (message) => {
    useToastStore.getState().addToast('error', message)
  },
  // 通过 confirmDialog store 弹出应用内确认框，等待用户操作。
  confirmAction: (message, options) =>
    useConfirmDialogStore.getState().requestConfirm(message, options),
  // promptText 暂无调用方（死代码），保留指向原生 window.prompt，不在本次范围。
  promptText: (message, defaultValue) => window.prompt(message, defaultValue),
}
