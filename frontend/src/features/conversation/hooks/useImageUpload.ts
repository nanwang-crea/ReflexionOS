import { useCallback, useRef, useState } from 'react'

export interface PendingAttachment {
  id: string
  serverId?: string
  file: File
  previewUrl: string
  status: 'compressing' | 'uploading' | 'uploaded' | 'error'
  error?: string
  retryCount: number
}

const MAX_FILE_SIZE = 10 * 1024 * 1024
const MAX_RETRY = 2
const MAX_DIMENSION = 2048
const COMPRESS_THRESHOLD = 1024 * 1024

async function compressImage(file: File): Promise<File> {
  if (file.size <= COMPRESS_THRESHOLD) {
    return file
  }

  return new Promise((resolve) => {
    const img = new Image()
    const url = URL.createObjectURL(file)

    img.onload = () => {
      URL.revokeObjectURL(url)

      let { width, height } = img
      if (width > MAX_DIMENSION || height > MAX_DIMENSION) {
        const ratio = Math.min(MAX_DIMENSION / width, MAX_DIMENSION / height)
        width = Math.round(width * ratio)
        height = Math.round(height * ratio)
      }

      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        resolve(file)
        return
      }

      ctx.drawImage(img, 0, 0, width, height)
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            resolve(file)
            return
          }
          const compressed = new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), {
            type: 'image/jpeg',
            lastModified: Date.now(),
          })
          resolve(compressed)
        },
        'image/jpeg',
        0.8
      )
    }

    img.onerror = () => {
      URL.revokeObjectURL(url)
      resolve(file)
    }

    img.src = url
  })
}

async function uploadFile(
  sessionId: string,
  file: File,
  signal?: AbortSignal
): Promise<{ attachment_id: string }> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`/api/sessions/${sessionId}/upload`, {
    method: 'POST',
    body: formData,
    signal,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(error.detail || '上传失败')
  }

  return response.json()
}

export function useImageUpload(sessionId: string | null) {
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map())

  const uploadedIds = attachments
    .filter((a) => a.status === 'uploaded' && a.serverId)
    .map((a) => a.serverId!)

  const isUploading = attachments.some(
    (a) => a.status === 'compressing' || a.status === 'uploading'
  )

  const doUpload = useCallback(
    async (attachment: PendingAttachment) => {
      if (!sessionId) return

      const controller = new AbortController()
      abortControllersRef.current.set(attachment.id, controller)

      try {
        setAttachments((prev) =>
          prev.map((a) =>
            a.id === attachment.id ? { ...a, status: 'uploading' as const, error: undefined } : a
          )
        )

        const result = await uploadFile(sessionId, attachment.file, controller.signal)

        setAttachments((prev) =>
          prev.map((a) =>
            a.id === attachment.id
              ? { ...a, status: 'uploaded' as const, serverId: result.attachment_id }
              : a
          )
        )
      } catch (err) {
        if (controller.signal.aborted) return

        const errorMsg = err instanceof Error ? err.message : '上传失败'
        setAttachments((prev) =>
          prev.map((a) =>
            a.id === attachment.id
              ? { ...a, status: 'error' as const, error: errorMsg }
              : a
          )
        )
      } finally {
        abortControllersRef.current.delete(attachment.id)
      }
    },
    [sessionId]
  )

  const addFiles = useCallback(
    async (files: File[]) => {
      const imageFiles = files.filter((f) => f.type.startsWith('image/'))
      if (imageFiles.length === 0) return

      const oversized = imageFiles.filter((f) => f.size > MAX_FILE_SIZE)
      if (oversized.length > 0) {
        throw new Error(`图片大小超过限制（最大 10MB）：${oversized.map((f) => f.name).join(', ')}`)
      }

      const newAttachments: PendingAttachment[] = imageFiles.map((file) => ({
        id: crypto.randomUUID(),
        file,
        previewUrl: URL.createObjectURL(file),
        status: 'compressing' as const,
        retryCount: 0,
      }))

      setAttachments((prev) => [...prev, ...newAttachments])

      for (const attachment of newAttachments) {
        try {
          const compressed = await compressImage(attachment.file)
          const updatedAttachment = { ...attachment, file: compressed }
          setAttachments((prev) =>
            prev.map((a) => (a.id === attachment.id ? updatedAttachment : a))
          )
          await doUpload(updatedAttachment)
        } catch {
          setAttachments((prev) =>
            prev.map((a) =>
              a.id === attachment.id
                ? { ...a, status: 'error' as const, error: '压缩失败' }
                : a
            )
          )
        }
      }
    },
    [doUpload]
  )

  const removeAttachment = useCallback((id: string) => {
    const controller = abortControllersRef.current.get(id)
    if (controller) {
      controller.abort()
      abortControllersRef.current.delete(id)
    }

    setAttachments((prev) => {
      const target = prev.find((a) => a.id === id)
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl)
      }
      return prev.filter((a) => a.id !== id)
    })
  }, [])

  const clearAttachments = useCallback(() => {
    abortControllersRef.current.forEach((controller) => controller.abort())
    abortControllersRef.current.clear()

    setAttachments((prev) => {
      prev.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl)
      })
      return []
    })
  }, [])

  const retryUpload = useCallback(
    async (id: string) => {
      const attachment = attachments.find((a) => a.id === id)
      if (!attachment || attachment.status !== 'error') return
      if (attachment.retryCount >= MAX_RETRY) return

      setAttachments((prev) =>
        prev.map((a) =>
          a.id === id ? { ...a, retryCount: a.retryCount + 1, status: 'uploading' as const } : a
        )
      )

      await doUpload({ ...attachment, retryCount: attachment.retryCount + 1 })
    },
    [attachments, doUpload]
  )

  return {
    attachments,
    addFiles,
    removeAttachment,
    clearAttachments,
    retryUpload,
    uploadedIds,
    isUploading,
  }
}
