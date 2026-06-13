import { useToastStore } from '@/shared/stores/toast.store'

export interface DialogService {
  notifyError: (message: string) => void
  confirmAction: (message: string) => boolean
  promptText: (message: string, defaultValue?: string) => string | null
}

export const nativeDialogService: DialogService = {
  notifyError: (message) => {
    useToastStore.getState().addToast('error', message)
  },
  confirmAction: (message) => window.confirm(message),
  promptText: (message, defaultValue) => window.prompt(message, defaultValue),
}
