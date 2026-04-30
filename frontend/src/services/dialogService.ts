export interface DialogService {
  notifyError: (message: string) => void
  confirmAction: (message: string) => boolean
  promptText: (message: string, defaultValue?: string) => string | null
}

export const nativeDialogService: DialogService = {
  notifyError: (message) => {
    window.alert(message)
  },
  confirmAction: (message) => window.confirm(message),
  promptText: (message, defaultValue) => window.prompt(message, defaultValue),
}
