import { useCallback, useEffect, useState } from 'react'

export interface PendingAttachment {
  id: string
  file: File
  previewUrl: string
}

const MAX_FILE_SIZE = 10 * 1024 * 1024
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
): Promise<{ attachment_id: string }> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`/api/sessions/${sessionId}/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(error.detail || '上传失败')
  }

  return response.json()
}

export function useImageUpload(sessionId: string | null) {
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])

  // 切换会话时清空待上传附件，避免在 A 会话暂存的图片残留并误传到 B 会话。
  // 同时释放预览用的 object URL，防止内存泄漏。
  useEffect(() => {
    return () => {
      setAttachments((prev) => {
        prev.forEach((attachment) => {
          if (attachment.previewUrl) {
            URL.revokeObjectURL(attachment.previewUrl)
          }
        })
        return []
      })
    }
  }, [sessionId])

  const addFiles = useCallback((files: File[]) => {
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
    }))

    setAttachments((prev) => [...prev, ...newAttachments])
  }, [])

  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => {
      const target = prev.find((a) => a.id === id)
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl)
      }
      return prev.filter((a) => a.id !== id)
    })
  }, [])

  const clearAttachments = useCallback(() => {
    setAttachments((prev) => {
      prev.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl)
      })
      return []
    })
  }, [])

  const uploadAll = useCallback(async (): Promise<string[]> => {
    if (!sessionId || attachments.length === 0) return []

    const uploadedIds: string[] = []

    for (const attachment of attachments) {
      try {
        const compressed = await compressImage(attachment.file)
        const result = await uploadFile(sessionId, compressed)
        uploadedIds.push(result.attachment_id)
      } catch (err) {
        const msg = err instanceof Error ? err.message : '上传失败'
        throw new Error(`图片 ${attachment.file.name} 上传失败: ${msg}`)
      }
    }

    return uploadedIds
  }, [sessionId, attachments])

  return {
    attachments,
    addFiles,
    removeAttachment,
    clearAttachments,
    uploadAll,
    hasAttachments: attachments.length > 0,
  }
}
